"""FastAPI presentation layer for the local core facade."""

import asyncio
from queue import Empty
from typing import Any

from ..core.facade import CoreFacade
from ..core.product import ProductService
from ..core.remote import is_loopback_host, validate_remote_origin
from ..diagnostics.logging import get_logger
from ..domain.errors import DS5ForgeError, ErrorCode
from ..domain.models import (
    AdaptiveTriggerEffect,
    LightbarState,
    PlayerLedState,
    StickCalibration,
    StickTelemetry,
    TriggerState,
)
from .origins import DEFAULT_ALLOWED_ORIGINS, validate_allowed_origins
from .schemas import (
    API_PREFIX,
    ActiveGameResponse,
    AppInfoResponse,
    AutomationResponse,
    AutomationUpdateRequest,
    ChordsResponse,
    ChordsUpdateRequest,
    CompatibilityStateResponse,
    CompatibilityUpdateRequest,
    ConfigPatchRequest,
    ConfigReplaceRequest,
    ConfigResponse,
    ConflictDiagnosticsResponse,
    ControllerTelemetryResponse,
    DeleteProfileResponse,
    DuplicateInputDiagnosticResponse,
    ExclusiveCapabilityResponse,
    ExclusiveStatusResponse,
    ForegroundApplicationResponse,
    FullControllerProfile,
    FullProfileSaveRequest,
    GameCandidatesResponse,
    GameDefinitionRequest,
    GameDefinitionResponse,
    GameMatchResponse,
    GamesResponse,
    GestureConfigRequest,
    GestureConfigResponse,
    GuidedDiagnosticsResponse,
    HapticsTestRequest,
    HapticsTestRunResponse,
    HealthResponse,
    InputIsolationCapabilityResponse,
    InputIsolationStatusResponse,
    LifecycleResponse,
    LightbarApplyRequest,
    LightbarResponse,
    MappingsResponse,
    MappingsUpdateRequest,
    PlayerLedApplyRequest,
    PlayerLedResponse,
    ProfileImportRequest,
    ProfileLoadResponse,
    ProfileSaveResponse,
    ProfilesResponse,
    RemotePairingCompleteRequest,
    RemotePairingStartRequest,
    RemotePairingStartResponse,
    RemoteRevokeResponse,
    RemoteSessionResponse,
    RemoteStatusResponse,
    RumbleConfigPatch,
    RumbleTestCommand,
    RumbleTestResponse,
    RuntimeStateResponse,
    StickCalibrationEstimateRequest,
    StickCalibrationEstimateResponse,
    StickCalibrationRequest,
    StickCalibrationResponse,
    ToggleCommand,
    TriggerEffectRequest,
    TriggerPairRequest,
    TriggerPreviewRequest,
    TriggerPreviewResponse,
    TriggerStateResponse,
    TunnelConfigureRequest,
    TunnelStatusResponse,
    UpdateCheckRequest,
    UpdateCheckResponse,
)

LOGGER = get_logger(__name__)
MAX_JSON_BODY_BYTES = 256 * 1024


def create_app(
    facade: CoreFacade,
    *,
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS,
    product: ProductService | None = None,
) -> Any:
    """Build the loopback API without starting a server.

    FastAPI is imported here, rather than at package import time, so the
    controller core and unit tests do not need web dependencies installed.
    """

    try:
        from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
        from fastapi.exceptions import RequestValidationError
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Install the 'api' dependencies to use the HTTP API: fastapi and uvicorn.") from exc

    validated_origins = validate_allowed_origins(allowed_origins)
    product = product or ProductService(facade)
    app = FastAPI(title="DS5Forge Local API", version="1.0.0", docs_url=f"{API_PREFIX}/docs")
    if validated_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(validated_origins),
            allow_credentials=True,
            allow_methods=["GET", "PUT", "PATCH", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    def add_remote_cors(response: Any, origin: str | None) -> Any:
        if origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, PUT, PATCH, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Vary"] = "Origin"
        return response

    @app.middleware("http")
    async def enforce_browser_origin(request: Request, call_next: Any) -> Any:
        # CORS controls which responses browser JavaScript may read, but it is
        # not CSRF protection: a cross-origin browser can still send some
        # requests to a loopback service. Reject any browser request that
        # explicitly carries an unapproved Origin before a command reaches the
        # core. Origin-less native/local clients remain supported.
        origin = request.headers.get("origin")
        pairing_complete = request.url.path == f"{API_PREFIX}/remote/pairing/complete"
        host_header = request.headers.get("host")
        remote_origin = product.remote.origin_allowed(origin)
        host_origin = product.remote.origin_for_host(host_header)
        # With remote access enabled, an origin-less request is only trusted as
        # local when its Host is loopback. A forwarded Host that is neither
        # loopback nor a registered origin must authenticate instead of falling
        # through to unauthenticated local access.
        unknown_remote_host = product.remote.enabled and not is_loopback_host(host_header)
        remote_request = remote_origin or host_origin is not None or unknown_remote_host
        pairing_origin = False
        if pairing_complete and origin is not None:
            try:
                validate_remote_origin(origin)
                pairing_origin = True
            except ValueError:
                pairing_origin = False
        trusted_remote = remote_request or pairing_origin
        if origin is not None and origin not in validated_origins and not trusted_remote:
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
        raw_length = request.headers.get("content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                return _json_response(
                    400,
                    {
                        "code": "api.invalid_content_length",
                        "message": "The request Content-Length is invalid.",
                        "detail": None,
                        "recoverable": True,
                        "fields": {},
                    },
                )
            if content_length > MAX_JSON_BODY_BYTES:
                response = _json_response(
                    413,
                    {
                        "code": "api.payload_too_large",
                        "message": "The request payload exceeds the bounded API limit.",
                        "detail": None,
                        "recoverable": True,
                        "fields": {"body": f"maximum {MAX_JSON_BODY_BYTES} bytes"},
                    },
                )
                return add_remote_cors(response, origin) if trusted_remote else response
        if remote_request and origin is not None and not remote_origin and not pairing_complete:
            response = _json_response(
                403,
                {
                    "code": "api.origin_rejected",
                    "message": "The browser origin does not match the registered remote origin.",
                    "detail": None,
                    "recoverable": False,
                    "fields": {},
                },
            )
            return add_remote_cors(response, origin) if trusted_remote else response
        if remote_request and request.method != "OPTIONS" and not pairing_complete:
            token = product.remote.token_from_cookie(request.headers.get("cookie"))
            authentication_origin = origin if remote_origin else host_origin
            if not product.remote.authenticate(token, authentication_origin):
                response = _json_response(
                    401,
                    {
                        "code": "remote.authentication_required",
                        "message": "This remote origin requires an authenticated DS5Forge session.",
                        "detail": None,
                        "recoverable": True,
                        "fields": {},
                    },
                )
                return add_remote_cors(response, origin)
        if trusted_remote and request.method == "OPTIONS":
            response = Response(status_code=204)
        else:
            response = await call_next(request)
        return add_remote_cors(response, origin) if trusted_remote else response

    @app.exception_handler(DS5ForgeError)
    async def handle_domain_error(_request: Any, exc: DS5ForgeError) -> Any:
        status = 404 if exc.code in {ErrorCode.PROFILE_NOT_FOUND, ErrorCode.GAME_NOT_FOUND} else 422
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

    @app.get(f"{API_PREFIX}/app/info", response_model=AppInfoResponse)
    async def app_info() -> dict[str, Any]:
        return product.app_info()

    @app.get(f"{API_PREFIX}/lifecycle", response_model=LifecycleResponse)
    async def lifecycle() -> dict[str, Any]:
        return product.lifecycle()

    @app.post(f"{API_PREFIX}/lifecycle/restart", response_model=LifecycleResponse)
    async def restart_core() -> dict[str, Any]:
        return product.restart_core()

    @app.post(f"{API_PREFIX}/lifecycle/stop", response_model=LifecycleResponse)
    async def stop_core() -> dict[str, Any]:
        return product.stop_core()

    @app.get(f"{API_PREFIX}/diagnostics/guided", response_model=GuidedDiagnosticsResponse)
    async def guided_diagnostics() -> dict[str, Any]:
        return product.guided_diagnostics()

    @app.post(f"{API_PREFIX}/diagnostics/support-bundle")
    async def support_bundle() -> Any:
        from fastapi.responses import Response as FastApiResponse

        return FastApiResponse(
            content=product.support_bundle(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="ds5forge-support-bundle.zip"'},
        )

    @app.post(f"{API_PREFIX}/updates/check", response_model=UpdateCheckResponse)
    async def check_update(payload: UpdateCheckRequest) -> dict[str, Any]:
        return product.check_update(payload.model_dump())

    @app.get(f"{API_PREFIX}/remote/status", response_model=RemoteStatusResponse)
    async def remote_status() -> dict[str, Any]:
        return product.remote_status()

    @app.post(f"{API_PREFIX}/remote/pairing/start", response_model=RemotePairingStartResponse)
    async def start_remote_pairing(payload: RemotePairingStartRequest | None = None) -> dict[str, Any]:
        challenge = product.remote.start_pairing(origin_hint=payload.origin_hint if payload else None)
        return challenge.public_dict()

    @app.post(f"{API_PREFIX}/remote/pairing/complete", response_model=RemoteSessionResponse)
    async def complete_remote_pairing(payload: RemotePairingCompleteRequest, response: Response) -> dict[str, Any]:
        try:
            session, token = product.remote.complete_pairing(payload.pairing_id, payload.code, payload.origin)
        except ValueError as exc:
            raise DS5ForgeError(
                code=ErrorCode.API_VALIDATION,
                message="Remote pairing could not be completed.",
                detail=str(exc),
                fields={"pairing_id": "invalid or expired"},
            ) from exc
        response.headers["Set-Cookie"] = product.remote.cookie_header(token)
        return session.public_dict(product.remote.now())

    @app.post(f"{API_PREFIX}/remote/disable", response_model=RemoteStatusResponse)
    async def disable_remote() -> dict[str, Any]:
        return product.disable_remote()

    @app.post(f"{API_PREFIX}/remote/sessions/{{session_id}}/revoke", response_model=RemoteRevokeResponse)
    async def revoke_remote_session(session_id: str) -> dict[str, Any]:
        return {"revoked": product.remote.revoke(session_id)}

    @app.get(f"{API_PREFIX}/tunnel/status", response_model=TunnelStatusResponse)
    async def tunnel_status() -> dict[str, Any]:
        return product.tunnel_status()

    @app.put(f"{API_PREFIX}/tunnel/configure", response_model=TunnelStatusResponse)
    async def configure_tunnel(payload: TunnelConfigureRequest) -> dict[str, Any]:
        try:
            return product.configure_tunnel(payload.executable, payload.config_path)
        except ValueError as exc:
            raise DS5ForgeError(
                code=ErrorCode.API_VALIDATION,
                message="Tunnel configuration is invalid.",
                detail=str(exc),
                fields={},
            ) from exc

    @app.post(f"{API_PREFIX}/tunnel/start", response_model=TunnelStatusResponse)
    async def start_tunnel() -> dict[str, Any]:
        return product.start_tunnel()

    @app.post(f"{API_PREFIX}/tunnel/stop", response_model=TunnelStatusResponse)
    async def stop_tunnel() -> dict[str, Any]:
        return product.stop_tunnel()

    @app.get(f"{API_PREFIX}/state", response_model=RuntimeStateResponse)
    async def state() -> dict[str, Any]:
        return facade.state_dict()

    @app.get(f"{API_PREFIX}/games", response_model=GamesResponse)
    async def games() -> dict[str, Any]:
        return {"games": facade.games()}

    @app.get(f"{API_PREFIX}/games/candidates", response_model=GameCandidatesResponse)
    async def game_candidates() -> dict[str, Any]:
        return {"candidates": facade.game_candidates()}

    @app.post(f"{API_PREFIX}/games", response_model=GameDefinitionResponse)
    async def add_game(payload: GameDefinitionRequest) -> dict[str, Any]:
        return facade.add_game(payload.model_dump())

    @app.get(f"{API_PREFIX}/games/active", response_model=ActiveGameResponse)
    async def active_game() -> dict[str, Any]:
        return facade.active_game()

    @app.get(f"{API_PREFIX}/games/{{game_id}}", response_model=GameDefinitionResponse)
    async def get_game(game_id: str) -> dict[str, Any]:
        return facade.get_game(game_id)

    @app.put(f"{API_PREFIX}/games/{{game_id}}", response_model=GameDefinitionResponse)
    async def update_game(game_id: str, payload: GameDefinitionRequest) -> dict[str, Any]:
        return facade.update_game(game_id, payload.model_dump())

    @app.delete(f"{API_PREFIX}/games/{{game_id}}")
    async def delete_game(game_id: str) -> dict[str, Any]:
        facade.delete_game(game_id)
        return {"deleted": game_id}

    @app.post(f"{API_PREFIX}/games/{{game_id}}/test-match", response_model=GameMatchResponse)
    async def test_game_match(game_id: str) -> dict[str, Any]:
        return facade.test_game_match(game_id)

    @app.get(f"{API_PREFIX}/foreground", response_model=ForegroundApplicationResponse)
    async def foreground() -> dict[str, Any]:
        return facade.foreground_state()

    @app.get(f"{API_PREFIX}/automation", response_model=AutomationResponse)
    async def automation() -> dict[str, Any]:
        return facade.automation()

    @app.put(f"{API_PREFIX}/automation", response_model=AutomationResponse)
    async def update_automation(payload: AutomationUpdateRequest) -> dict[str, Any]:
        return facade.update_automation(payload.model_dump(exclude_unset=True, exclude_none=True))

    @app.get(f"{API_PREFIX}/compatibility", response_model=CompatibilityStateResponse)
    async def compatibility() -> dict[str, Any]:
        return facade.compatibility()

    @app.put(f"{API_PREFIX}/compatibility", response_model=CompatibilityStateResponse)
    async def update_compatibility(payload: CompatibilityUpdateRequest) -> dict[str, Any]:
        return facade.update_compatibility(payload.mode)

    @app.get(f"{API_PREFIX}/mappings", response_model=MappingsResponse)
    async def mappings() -> dict[str, Any]:
        return {"mappings": facade.mappings()}

    @app.put(f"{API_PREFIX}/mappings", response_model=MappingsResponse)
    async def update_mappings(payload: MappingsUpdateRequest) -> dict[str, Any]:
        return {"mappings": facade.update_mappings([item.model_dump() for item in payload.mappings])}

    @app.get(f"{API_PREFIX}/chords", response_model=ChordsResponse)
    async def chords() -> dict[str, Any]:
        return {"chords": facade.chords()}

    @app.put(f"{API_PREFIX}/chords", response_model=ChordsResponse)
    async def update_chords(payload: ChordsUpdateRequest) -> dict[str, Any]:
        return {"chords": facade.update_chords([item.model_dump() for item in payload.chords])}

    @app.get(f"{API_PREFIX}/diagnostics/conflicts", response_model=ConflictDiagnosticsResponse)
    async def conflict_diagnostics() -> dict[str, Any]:
        return {"conflicts": facade.conflict_diagnostics()}

    @app.get(f"{API_PREFIX}/diagnostics/duplicate-input", response_model=DuplicateInputDiagnosticResponse)
    async def duplicate_input_diagnostics() -> dict[str, Any]:
        return facade.duplicate_input_diagnostics()

    @app.get(f"{API_PREFIX}/input-isolation/capabilities", response_model=InputIsolationCapabilityResponse)
    async def input_isolation_capabilities() -> dict[str, Any]:
        return facade.input_isolation_capability()

    @app.get(f"{API_PREFIX}/input-isolation/status", response_model=InputIsolationStatusResponse)
    async def input_isolation_status() -> dict[str, Any]:
        return facade.input_isolation_status()

    @app.post(f"{API_PREFIX}/input-isolation/enable", response_model=InputIsolationStatusResponse)
    async def enable_input_isolation() -> dict[str, Any]:
        return facade.enable_input_isolation()

    @app.post(f"{API_PREFIX}/input-isolation/disable", response_model=InputIsolationStatusResponse)
    async def disable_input_isolation() -> dict[str, Any]:
        return facade.disable_input_isolation()

    @app.get(f"{API_PREFIX}/exclusive/capabilities", response_model=ExclusiveCapabilityResponse)
    async def exclusive_capabilities() -> dict[str, Any]:
        return facade.exclusive_capability()

    @app.get(f"{API_PREFIX}/exclusive/status", response_model=ExclusiveStatusResponse)
    async def exclusive_status() -> dict[str, Any]:
        return facade.exclusive_status()

    @app.post(f"{API_PREFIX}/exclusive/enable", response_model=ExclusiveStatusResponse)
    async def enable_exclusive() -> dict[str, Any]:
        return facade.enable_exclusive()

    @app.post(f"{API_PREFIX}/exclusive/disable", response_model=ExclusiveStatusResponse)
    async def disable_exclusive() -> dict[str, Any]:
        return facade.disable_exclusive()

    @app.post(f"{API_PREFIX}/exclusive/heartbeat", response_model=ExclusiveStatusResponse)
    async def exclusive_heartbeat() -> dict[str, Any]:
        return facade.exclusive_heartbeat()

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

    @app.get(f"{API_PREFIX}/controller/player-leds", response_model=PlayerLedResponse)
    async def controller_player_leds() -> dict[str, Any]:
        return facade.player_led_state().to_dict()

    @app.put(f"{API_PREFIX}/controller/player-leds", response_model=PlayerLedResponse)
    async def apply_player_leds(payload: PlayerLedApplyRequest) -> dict[str, Any]:
        facade.apply_player_leds(PlayerLedState(**payload.model_dump()))
        return facade.state_dict()["player_leds"]

    @app.post(f"{API_PREFIX}/controller/player-leds/reset", response_model=PlayerLedResponse)
    async def reset_player_leds() -> dict[str, Any]:
        facade.reset_player_leds()
        return facade.state_dict()["player_leds"]

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

    @app.post(
        f"{API_PREFIX}/controller/sticks/calibration/estimate",
        response_model=StickCalibrationEstimateResponse,
    )
    async def estimate_stick_calibration(payload: StickCalibrationEstimateRequest) -> dict[str, Any]:
        samples = [StickTelemetry(**sample.model_dump()) for sample in payload.samples]
        return facade.estimate_stick_calibration(samples)

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
        host_header = websocket.headers.get("host")
        remote_origin = product.remote.origin_allowed(origin)
        host_origin = product.remote.origin_for_host(host_header)
        unknown_remote_host = product.remote.enabled and not is_loopback_host(host_header)
        remote_request = remote_origin or host_origin is not None or unknown_remote_host
        if origin is not None and origin not in validated_origins and not remote_origin:
            LOGGER.warning("websocket origin rejected", extra={"event": "websocket.origin_rejected"})
            await websocket.close(code=1008)
            return
        if remote_request and origin is not None and not remote_origin:
            await websocket.close(code=1008)
            return
        if remote_request and not product.remote.authenticate(
            product.remote.token_from_cookie(websocket.headers.get("cookie")),
            origin if remote_origin else host_origin,
        ):
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
                        frame = receive_task.result()
                    except WebSocketDisconnect:
                        raise
                    except Exception:
                        # A malformed/unsupported client frame is not a
                        # controller command; keep the socket alive.
                        continue
                    if len(frame) > 8_192:
                        await websocket.close(code=1009)
                        return
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
