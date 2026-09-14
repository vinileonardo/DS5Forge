"""FastAPI presentation layer for the local core facade."""

import asyncio
from queue import Empty
from typing import Any

from ..core.facade import CoreFacade
from ..diagnostics.logging import get_logger
from ..domain.errors import DS5ForgeError, ErrorCode
from ..domain.models import AdaptiveTriggerEffect, LightbarState, StickCalibration, TriggerState
from .origins import DEFAULT_ALLOWED_ORIGINS, validate_allowed_origins
from .schemas import (
    API_PREFIX,
    ConfigPatchRequest,
    ConfigReplaceRequest,
    ConfigResponse,
    ControllerTelemetryResponse,
    DeleteProfileResponse,
    FullControllerProfile,
    FullProfileSaveRequest,
    GestureConfigRequest,
    GestureConfigResponse,
    HapticsTestRequest,
    HapticsTestRunResponse,
    HealthResponse,
    LightbarApplyRequest,
    LightbarResponse,
    ProfileImportRequest,
    ProfileLoadResponse,
    ProfileSaveResponse,
    ProfilesResponse,
    RumbleConfigPatch,
    RumbleTestCommand,
    RumbleTestResponse,
    RuntimeStateResponse,
    StickCalibrationRequest,
    StickCalibrationResponse,
    ToggleCommand,
    TriggerEffectRequest,
    TriggerPairRequest,
    TriggerPreviewRequest,
    TriggerPreviewResponse,
    TriggerStateResponse,
)

LOGGER = get_logger(__name__)


def create_app(facade: CoreFacade, *, allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS) -> Any:
    """Build the loopback API without starting a server.

    FastAPI is imported here, rather than at package import time, so the
    controller core and unit tests do not need web dependencies installed.
    """

    try:
        from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
        from fastapi.exceptions import RequestValidationError
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Install the 'api' dependencies to use the HTTP API: fastapi and uvicorn.") from exc

    validated_origins = validate_allowed_origins(allowed_origins)
    app = FastAPI(title="DS5Forge Local API", version="1.0.0", docs_url=f"{API_PREFIX}/docs")
    if validated_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(validated_origins),
            allow_credentials=False,
            allow_methods=["GET", "PUT", "PATCH", "POST", "DELETE"],
            allow_headers=["Content-Type"],
        )

    @app.middleware("http")
    async def enforce_browser_origin(request: Request, call_next: Any) -> Any:
        # CORS controls which responses browser JavaScript may read, but it is
        # not CSRF protection: a cross-origin browser can still send some
        # requests to a loopback service. Reject any browser request that
        # explicitly carries an unapproved Origin before a command reaches the
        # core. Origin-less native/local clients remain supported.
        origin = request.headers.get("origin")
        if origin is not None and origin not in validated_origins:
            LOGGER.warning("http origin rejected", extra={"event": "http.origin_rejected", "origin": origin})
            return _json_response(
                403,
                {
                    "code": "api.origin_rejected",
                    "message": "The browser origin is not allowed to access the local DS5Forge core.",
                    "detail": None,
                    "recoverable": False,
                    "fields": {},
                },
            )
        return await call_next(request)

    @app.exception_handler(DS5ForgeError)
    async def handle_domain_error(_request: Any, exc: DS5ForgeError) -> Any:
        status = 404 if exc.code.value == "profile.not_found" else 422
        return _json_response(status, exc.to_snapshot().to_dict())

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(_request: Request, exc: RequestValidationError) -> Any:
        fields: dict[str, Any] = {}
        for item in exc.errors():
            location = [str(part) for part in item.get("loc", ()) if part not in {"body", "query", "path"}]
            if location and location[-1] in {"int", "float"}:
                # Pydantic reports both branches of Number = StrictInt |
                # StrictFloat. The public contract exposes the actual field,
                # not implementation details of that union.
                location.pop()
            key = ".".join(location) or "request"
            fields.setdefault(key, item.get("msg", "invalid value"))
        return _json_response(
            422,
            {
                "code": "api.validation",
                "message": "The request payload is invalid.",
                "detail": None,
                "recoverable": True,
                "fields": fields,
            },
        )

    @app.get(f"{API_PREFIX}/health", response_model=HealthResponse)
    async def health() -> dict[str, Any]:
        return facade.health_dict()

    @app.get(f"{API_PREFIX}/state", response_model=RuntimeStateResponse)
    async def state() -> dict[str, Any]:
        return facade.state_dict()

    @app.get(f"{API_PREFIX}/config", response_model=ConfigResponse)
    async def config() -> dict[str, Any]:
        return facade.config()

    @app.put(f"{API_PREFIX}/config", response_model=ConfigResponse)
    async def put_config(payload: ConfigReplaceRequest) -> dict[str, Any]:
        return facade.update_config(payload.model_dump(), replace_all=True)

    @app.patch(f"{API_PREFIX}/config", response_model=ConfigResponse)
    async def patch_config(payload: ConfigPatchRequest) -> dict[str, Any]:
        return facade.update_config(payload.model_dump(exclude_unset=True, exclude_none=True))

    @app.get(f"{API_PREFIX}/profiles", response_model=ProfilesResponse)
    async def profiles() -> dict[str, Any]:
        return {"profiles": facade.profiles()}

    @app.post(f"{API_PREFIX}/profiles/{{name}}/load", response_model=ProfileLoadResponse)
    async def load_profile(name: str) -> dict[str, Any]:
        result = facade.load_profile_result(name)
        return {
            "profile": result["profile"],
            "config": result["config"],
            "unsupported_sections": result["unsupported_sections"],
            "state": result["state"],
        }

    @app.get(f"{API_PREFIX}/profiles/{{name}}", response_model=FullControllerProfile)
    async def export_profile(name: str) -> dict[str, Any]:
        return facade.export_profile(name)

    @app.get(f"{API_PREFIX}/profiles/{{name}}/export", response_model=FullControllerProfile)
    async def export_profile_document(name: str) -> dict[str, Any]:
        return facade.export_profile(name)

    @app.put(f"{API_PREFIX}/profiles/{{name}}", response_model=ProfileSaveResponse)
    async def save_profile(name: str, payload: FullProfileSaveRequest | RumbleConfigPatch) -> dict[str, Any]:
        if isinstance(payload, FullProfileSaveRequest):
            profile = payload.model_dump(exclude={"confirm_overwrite"})
            saved = facade.save_controller_profile(name, profile, confirm_overwrite=payload.confirm_overwrite)
            return {"profile": name, "full_profile": saved}
        return {
            "profile": name,
            "rumble": facade.save_profile(name, payload.model_dump(exclude_unset=True, exclude_none=True)),
        }

    @app.post(f"{API_PREFIX}/profiles/import", response_model=FullControllerProfile)
    async def import_profile(payload: ProfileImportRequest) -> dict[str, Any]:
        return facade.import_profile(
            payload.content,
            name=payload.name,
            confirm_overwrite=payload.confirm_overwrite,
        )

    @app.delete(f"{API_PREFIX}/profiles/{{name}}", response_model=DeleteProfileResponse)
    async def delete_profile(name: str) -> dict[str, Any]:
        facade.delete_profile(name)
        return {"deleted": name}

    @app.post(f"{API_PREFIX}/commands/rumble", response_model=RuntimeStateResponse)
    async def set_rumble(payload: ToggleCommand) -> dict[str, Any]:
        return facade.set_rumble_enabled(payload.enabled).to_dict()

    @app.post(f"{API_PREFIX}/commands/touchpad", response_model=RuntimeStateResponse)
    async def set_touchpad(payload: ToggleCommand) -> dict[str, Any]:
        return facade.set_touchpad_enabled(payload.enabled).to_dict()

    @app.post(f"{API_PREFIX}/commands/rumble/test", response_model=RumbleTestResponse)
    async def test_rumble(payload: RumbleTestCommand | None = None) -> dict[str, Any]:
        command = payload or RumbleTestCommand()
        accepted = facade.test_rumble(left=command.left, right=command.right, duration_ms=command.duration_ms)
        return {"accepted": accepted}

    @app.get(f"{API_PREFIX}/controller/input", response_model=ControllerTelemetryResponse)
    async def controller_input() -> dict[str, Any]:
        return facade.input_telemetry().to_dict()

    @app.get(f"{API_PREFIX}/controller/telemetry", response_model=ControllerTelemetryResponse)
    async def controller_telemetry() -> dict[str, Any]:
        return facade.input_telemetry().to_dict()

    @app.get(f"{API_PREFIX}/controller/lightbar", response_model=LightbarResponse)
    async def controller_lightbar() -> dict[str, Any]:
        return facade.lightbar_state().to_dict()

    @app.put(f"{API_PREFIX}/controller/lightbar", response_model=LightbarResponse)
    async def apply_lightbar(payload: LightbarApplyRequest) -> dict[str, Any]:
        facade.apply_lightbar(LightbarState(**payload.model_dump()))
        return facade.state_dict()["lightbar"]

    @app.post(f"{API_PREFIX}/controller/lightbar/reset", response_model=LightbarResponse)
    async def reset_lightbar() -> dict[str, Any]:
        facade.reset_lightbar()
        return facade.state_dict()["lightbar"]

    @app.get(f"{API_PREFIX}/controller/triggers", response_model=TriggerStateResponse)
    async def controller_triggers() -> dict[str, Any]:
        return facade.state_dict()["triggers"]

    @app.put(f"{API_PREFIX}/controller/triggers", response_model=TriggerStateResponse)
    async def configure_trigger_pair(payload: TriggerPairRequest) -> dict[str, Any]:
        state = TriggerState(
            left=AdaptiveTriggerEffect(**payload.left.model_dump()),
            right=AdaptiveTriggerEffect(**payload.right.model_dump()),
        )
        facade.configure_triggers(state)
        return facade.state_dict()["triggers"]

    @app.put(f"{API_PREFIX}/controller/triggers/{{trigger}}", response_model=TriggerStateResponse)
    async def configure_trigger(trigger: str, payload: TriggerEffectRequest) -> dict[str, Any]:
        current = facade.trigger_state()
        effect = AdaptiveTriggerEffect(**payload.model_dump())
        if trigger == "left":
            state = TriggerState(left=effect, right=current.right)
        elif trigger == "right":
            state = TriggerState(left=current.left, right=effect)
        else:
            raise DS5ForgeError(
                code=ErrorCode.API_VALIDATION,
                message="Trigger must be left or right.",
                fields={"trigger": "must be left or right"},
            )
        facade.configure_triggers(state)
        return facade.state_dict()["triggers"]

    @app.post(f"{API_PREFIX}/controller/triggers/preview", response_model=TriggerPreviewResponse)
    async def preview_triggers(payload: TriggerPreviewRequest) -> dict[str, Any]:
        state = TriggerState(
            left=AdaptiveTriggerEffect(**payload.left.model_dump()),
            right=AdaptiveTriggerEffect(**payload.right.model_dump()),
        )
        preview = facade.preview_triggers(state, duration_ms=payload.duration_ms)
        return preview.to_dict() if hasattr(preview, "to_dict") else facade.state_dict()["triggers"]["preview"]

    @app.delete(f"{API_PREFIX}/controller/triggers/preview", response_model=TriggerPreviewResponse | None)
    async def cancel_trigger_preview() -> dict[str, Any] | None:
        preview = facade.cancel_trigger_preview()
        return (
            preview.to_dict()
            if preview is not None and hasattr(preview, "to_dict")
            else facade.state_dict()["triggers"]["preview"]
        )

    @app.post(f"{API_PREFIX}/controller/triggers/reset", response_model=TriggerStateResponse)
    async def reset_triggers() -> dict[str, Any]:
        facade.reset_triggers()
        return facade.state_dict()["triggers"]

    @app.post(f"{API_PREFIX}/controller/haptics/test", response_model=HapticsTestRunResponse)
    async def controller_haptics_test(payload: HapticsTestRequest | None = None) -> dict[str, Any]:
        command = payload or HapticsTestRequest()
        return facade.start_haptics_test(
            left=command.left,
            right=command.right,
            duration_ms=command.duration_ms,
        ).to_dict()

    @app.delete(f"{API_PREFIX}/controller/haptics/test", response_model=HapticsTestRunResponse | None)
    async def cancel_haptics_test() -> dict[str, Any] | None:
        run = facade.cancel_haptics_test()
        return run.to_dict() if run is not None and hasattr(run, "to_dict") else None

    @app.get(f"{API_PREFIX}/controller/sticks/calibration", response_model=StickCalibrationResponse)
    async def get_stick_calibration() -> dict[str, Any]:
        return facade.state_dict()["stick_calibration"]

    @app.put(f"{API_PREFIX}/controller/sticks/calibration", response_model=StickCalibrationResponse)
    async def update_stick_calibration(payload: StickCalibrationRequest) -> dict[str, Any]:
        facade.update_stick_calibration(StickCalibration(**payload.model_dump()))
        return facade.state_dict()["stick_calibration"]

    @app.get(f"{API_PREFIX}/controller/gestures", response_model=GestureConfigResponse)
    async def get_gesture_config() -> dict[str, Any]:
        return facade.state_dict()["gesture_config"]

    @app.patch(f"{API_PREFIX}/controller/gestures", response_model=GestureConfigResponse)
    async def update_gesture_config(payload: GestureConfigRequest) -> dict[str, Any]:
        facade.update_gesture_config(payload.model_dump(exclude_unset=True, exclude_none=True))
        return facade.state_dict()["gesture_config"]

    @app.websocket(f"{API_PREFIX}/ws")
    async def websocket(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in validated_origins:
            LOGGER.warning("websocket origin rejected", extra={"event": "websocket.origin_rejected"})
            await websocket.close(code=1008)
            return
        await websocket.accept()
        LOGGER.info("websocket connected", extra={"event": "websocket.connect"})
        subscription = facade.subscribe(maxsize=64)
        try:
            await websocket.send_json(
                {
                    "type": "state.snapshot",
                    "version": 1,
                    "payload": {"state": facade.state_dict()},
                }
            )
            while True:
                event_task = asyncio.create_task(_next_event(subscription))
                receive_task = asyncio.create_task(websocket.receive_text())
                done, pending = await asyncio.wait(
                    {event_task, receive_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                if receive_task in done:
                    # Clients may send a keepalive or command hint. Commands
                    # remain HTTP-only in P0; ignore the frame after validating
                    # that the socket is still open.
                    try:
                        receive_task.result()
                    except WebSocketDisconnect:
                        raise
                    except Exception:
                        # A malformed/unsupported client frame is not a
                        # controller command; keep the socket alive.
                        continue
                    continue
                try:
                    event = event_task.result()
                except Empty:
                    continue
                await websocket.send_json(event.to_dict())
        except WebSocketDisconnect:
            return
        finally:
            facade.unsubscribe(subscription)
            LOGGER.info("websocket disconnected", extra={"event": "websocket.disconnect"})

    return app


async def _next_event(subscription: Any) -> Any:
    while True:
        try:
            return subscription.get_nowait()
        except Empty:
            await asyncio.sleep(0.1)


def _json_response(status: int, payload: dict[str, Any]) -> Any:
    try:
        from fastapi.responses import JSONResponse
    except ImportError:  # pragma: no cover
        return payload
    return JSONResponse(status_code=status, content={"error": payload})
