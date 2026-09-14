"""Strict, versioned HTTP contracts for the local API v1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

Number = StrictInt | StrictFloat

API_VERSION = 1
API_PREFIX = "/api/v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PatchModel(StrictModel):
    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} may not be null")
        return self


class RumbleConfig(StrictModel):
    # Bounds mirror core.config.RUMBLE_RANGES so the OpenAPI contract and the
    # core validator accept exactly the same values.
    heavy_cutoff_hz: Number = Field(ge=1, le=20_000)
    texture_center_hz: Number = Field(ge=1, le=20_000)
    fast_attack_ms: Number = Field(ge=0.1, le=10_000)
    fast_release_ms: Number = Field(ge=0.1, le=10_000)
    baseline_attack_ms: Number = Field(ge=0.1, le=10_000)
    baseline_release_ms: Number = Field(ge=0.1, le=20_000)
    gate: Number = Field(ge=0, le=1)
    impact_level: Number = Field(ge=0.001, le=1)
    gamma: Number = Field(ge=0.01, le=10)
    transient_min_level: Number = Field(ge=0, le=1)
    transient_gain: Number = Field(ge=0, le=20)
    transient_weight: Number = Field(ge=0, le=1)
    drive_gate: Number = Field(ge=0, le=1)
    texture_gate_mult: Number = Field(ge=0, le=10)
    min_rumble: Number = Field(ge=0, le=255)
    max_rumble: Number = Field(ge=0, le=255)


class RumbleConfigPatch(PatchModel):
    heavy_cutoff_hz: Number | None = Field(default=None, ge=1, le=20_000)
    texture_center_hz: Number | None = Field(default=None, ge=1, le=20_000)
    fast_attack_ms: Number | None = Field(default=None, ge=0.1, le=10_000)
    fast_release_ms: Number | None = Field(default=None, ge=0.1, le=10_000)
    baseline_attack_ms: Number | None = Field(default=None, ge=0.1, le=10_000)
    baseline_release_ms: Number | None = Field(default=None, ge=0.1, le=20_000)
    gate: Number | None = Field(default=None, ge=0, le=1)
    impact_level: Number | None = Field(default=None, ge=0.001, le=1)
    gamma: Number | None = Field(default=None, ge=0.01, le=10)
    transient_min_level: Number | None = Field(default=None, ge=0, le=1)
    transient_gain: Number | None = Field(default=None, ge=0, le=20)
    transient_weight: Number | None = Field(default=None, ge=0, le=1)
    drive_gate: Number | None = Field(default=None, ge=0, le=1)
    texture_gate_mult: Number | None = Field(default=None, ge=0, le=10)
    min_rumble: Number | None = Field(default=None, ge=0, le=255)
    max_rumble: Number | None = Field(default=None, ge=0, le=255)


class TrackpadConfig(StrictModel):
    trackpad_enabled_on_start: StrictBool
    pointer_speed: Number = Field(ge=0.01, le=10)
    acceleration: Number = Field(ge=0, le=1)
    accel_cap: Number = Field(ge=0, le=10)
    scroll_speed: Number = Field(ge=0.01, le=10)
    tap_to_click: StrictBool
    gestures_enabled: StrictBool
    two_finger_scroll: StrictBool
    swipe_enabled: StrictBool
    swipe_threshold: Number = Field(ge=1, le=500)


class TrackpadConfigPatch(PatchModel):
    trackpad_enabled_on_start: StrictBool | None = None
    pointer_speed: Number | None = Field(default=None, ge=0.01, le=10)
    acceleration: Number | None = Field(default=None, ge=0, le=1)
    accel_cap: Number | None = Field(default=None, ge=0, le=10)
    scroll_speed: Number | None = Field(default=None, ge=0.01, le=10)
    tap_to_click: StrictBool | None = None
    gestures_enabled: StrictBool | None = None
    two_finger_scroll: StrictBool | None = None
    swipe_enabled: StrictBool | None = None
    swipe_threshold: Number | None = Field(default=None, ge=1, le=500)


class ConfigResponse(StrictModel):
    schema_version: Literal[1]
    theme: Literal["Light", "Dark", "Liquid Glass"]
    mic_button: Literal["master", "rumble", "trackpad"]
    rumble: RumbleConfig
    trackpad: TrackpadConfig


class ConfigReplaceRequest(ConfigResponse):
    pass


class ConfigPatchRequest(PatchModel):
    schema_version: Literal[1] | None = None
    theme: Literal["Light", "Dark", "Liquid Glass"] | None = None
    mic_button: Literal["master", "rumble", "trackpad"] | None = None
    rumble: RumbleConfigPatch | None = None
    trackpad: TrackpadConfigPatch | None = None


class ToggleCommand(StrictModel):
    enabled: StrictBool


class RumbleTestCommand(StrictModel):
    left: StrictInt = Field(default=200, ge=0, le=255)
    right: StrictInt = Field(default=160, ge=0, le=255)
    duration_ms: StrictInt = Field(default=350, ge=10, le=5_000)


class ControllerIdentityResponse(StrictModel):
    model: str
    serial: str | None
    vendor_id: int | None
    product_id: int | None
    transport: str


class CapabilityAvailabilityResponse(StrictModel):
    supported: bool
    available: bool
    reason: str | None


class ControllerCapabilitiesResponse(StrictModel):
    usb: bool
    rumble: bool
    touchpad: bool
    microphone_button: bool
    lightbar: bool
    adaptive_triggers: bool
    availability: dict[str, CapabilityAvailabilityResponse]


class BatteryResponse(StrictModel):
    level: int = Field(ge=0, le=100)
    charging: bool | None


class MotorResponse(StrictModel):
    left: int = Field(ge=0, le=255)
    right: int = Field(ge=0, le=255)


class TouchPointResponse(StrictModel):
    active: bool
    x: float
    y: float


class StickTelemetryResponse(StrictModel):
    left_x: float = Field(ge=-1, le=1)
    left_y: float = Field(ge=-1, le=1)
    right_x: float = Field(ge=-1, le=1)
    right_y: float = Field(ge=-1, le=1)


class ControllerInputResponse(StrictModel):
    square: bool
    triangle: bool
    circle: bool
    cross: bool
    dpad_up: bool
    dpad_down: bool
    dpad_left: bool
    dpad_right: bool
    l1: bool
    r1: bool
    l2_button: bool
    r2_button: bool
    l3: bool
    r3: bool
    options: bool
    share: bool
    ps: bool
    mic_button: bool
    touchpad_button: bool
    l2: float = Field(ge=0, le=1)
    r2: float = Field(ge=0, le=1)
    sticks: StickTelemetryResponse
    touch0: TouchPointResponse
    touch1: TouchPointResponse
    buttons: dict[str, bool]


class ControllerTelemetryResponse(StrictModel):
    input: ControllerInputResponse
    sequence: int = Field(ge=0)
    timestamp: float
    sample_rate_hz: float = Field(ge=0)


class LightbarResponse(StrictModel):
    r: StrictInt = Field(ge=0, le=255)
    g: StrictInt = Field(ge=0, le=255)
    b: StrictInt = Field(ge=0, le=255)
    enabled: StrictBool
    brightness: StrictInt = Field(ge=0, le=2)
    pulse: Literal["off", "slow", "fast"]


class AdaptiveTriggerEffectResponse(StrictModel):
    mode: Literal["off", "resistance", "pulse", "rigid"]
    start_position: StrictInt = Field(ge=0, le=255)
    end_position: StrictInt = Field(ge=0, le=255)
    force: StrictInt = Field(ge=0, le=255)
    frequency: StrictInt = Field(ge=0, le=255)
    amplitude: StrictInt = Field(ge=0, le=255)


class TriggerPreviewResponse(StrictModel):
    id: str
    status: str
    started_at: float
    expires_at: float
    error: ErrorResponse | None = None


class TriggerStateResponse(StrictModel):
    left: AdaptiveTriggerEffectResponse
    right: AdaptiveTriggerEffectResponse
    preview: TriggerPreviewResponse | None


class StickCalibrationResponse(StrictModel):
    # This model is also embedded in the schema-v2 profile write request.
    # Keep the fields strict there as well as in the runtime response.
    left_deadzone: Number = Field(ge=0, le=1)
    right_deadzone: Number = Field(ge=0, le=1)
    left_center_x: Number = Field(ge=-1, le=1)
    left_center_y: Number = Field(ge=-1, le=1)
    right_center_x: Number = Field(ge=-1, le=1)
    right_center_y: Number = Field(ge=-1, le=1)


class StickCalibrationRequest(StrictModel):
    left_deadzone: Number = Field(ge=0, le=1)
    right_deadzone: Number = Field(ge=0, le=1)
    left_center_x: Number = Field(ge=-1, le=1)
    left_center_y: Number = Field(ge=-1, le=1)
    right_center_x: Number = Field(ge=-1, le=1)
    right_center_y: Number = Field(ge=-1, le=1)


class GestureConfigResponse(StrictModel):
    enabled: StrictBool
    two_finger_scroll: StrictBool
    tap_to_click: StrictBool
    swipe_enabled: StrictBool
    swipe_threshold: Number = Field(ge=1, le=500)


class AudioResponse(StrictModel):
    status: str
    device: str | None
    error: str | None


class ErrorResponse(StrictModel):
    code: str
    message: str
    detail: str | None
    recoverable: bool
    fields: dict[str, Any]


class HealthStateResponse(StrictModel):
    process_alive: bool
    controller_available: bool
    subsystems: dict[str, str]
    degraded: list[str]


class HealthResponse(HealthStateResponse):
    status: str


class RuntimeStateResponse(StrictModel):
    connection: str
    identity: ControllerIdentityResponse | None
    capabilities: ControllerCapabilitiesResponse
    battery: BatteryResponse
    motors: MotorResponse
    input: ControllerInputResponse
    telemetry: ControllerTelemetryResponse
    lightbar: LightbarResponse
    triggers: TriggerStateResponse
    haptics_test: HapticsTestRunResponse | None = None
    stick_calibration: StickCalibrationResponse
    gesture_config: GestureConfigResponse
    rumble_enabled: bool
    touchpad_enabled: bool
    active_profile: str
    config_version: int
    audio: AudioResponse
    last_error: ErrorResponse | None
    health: HealthStateResponse
    sequence: int
    updated_at: float


class ProfileSummary(StrictModel):
    name: str
    source: Literal["bundled", "user"]
    editable: bool


class ProfilesResponse(StrictModel):
    profiles: list[ProfileSummary]


class LightbarApplyRequest(StrictModel):
    r: StrictInt = Field(ge=0, le=255)
    g: StrictInt = Field(ge=0, le=255)
    b: StrictInt = Field(ge=0, le=255)
    enabled: StrictBool = True
    brightness: StrictInt = Field(default=2, ge=0, le=2)
    pulse: Literal["off", "slow", "fast"] = "off"


class TriggerEffectRequest(StrictModel):
    mode: Literal["off", "resistance", "pulse", "rigid"] = "off"
    start_position: StrictInt = Field(default=0, ge=0, le=255)
    end_position: StrictInt = Field(default=255, ge=0, le=255)
    force: StrictInt = Field(default=0, ge=0, le=255)
    frequency: StrictInt = Field(default=0, ge=0, le=255)
    amplitude: StrictInt = Field(default=0, ge=0, le=255)

    @model_validator(mode="after")
    def validate_positions(self):
        if self.start_position > self.end_position:
            raise ValueError("start_position may not exceed end_position")
        return self


class TriggerPairRequest(StrictModel):
    left: TriggerEffectRequest
    right: TriggerEffectRequest


class TriggerPreviewRequest(TriggerPairRequest):
    duration_ms: StrictInt = Field(default=1_000, ge=10, le=5_000)


class HapticsTestRequest(StrictModel):
    left: StrictInt = Field(default=200, ge=0, le=255)
    right: StrictInt = Field(default=160, ge=0, le=255)
    duration_ms: StrictInt = Field(default=350, ge=10, le=5_000)


class HapticsTestRunResponse(StrictModel):
    id: str
    status: str
    left: int = Field(ge=0, le=255)
    right: int = Field(ge=0, le=255)
    duration_ms: int = Field(ge=10, le=5_000)
    started_at: float
    expires_at: float
    error: ErrorResponse | None


class FullControllerProfile(StrictModel):
    schema_version: Literal[2]
    name: StrictStr
    rumble: RumbleConfig
    lightbar: LightbarResponse
    triggers: TriggerPairRequest
    sticks: StickCalibrationResponse
    touchpad: GestureConfigResponse


class FullProfileSaveRequest(FullControllerProfile):
    confirm_overwrite: StrictBool = False


class ProfileLoadResponse(StrictModel):
    profile: str
    config: ConfigResponse
    unsupported_sections: list[str] = Field(default_factory=list)
    state: RuntimeStateResponse | None = None


class ProfileSaveResponse(StrictModel):
    profile: str
    rumble: RumbleConfig | None = None
    full_profile: FullControllerProfile | None = None


class DeleteProfileResponse(StrictModel):
    deleted: str


class RumbleTestResponse(StrictModel):
    accepted: bool


class GestureConfigRequest(PatchModel):
    enabled: StrictBool | None = None
    two_finger_scroll: StrictBool | None = None
    tap_to_click: StrictBool | None = None
    swipe_enabled: StrictBool | None = None
    swipe_threshold: Number | None = Field(default=None, ge=1, le=500)


class ProfileImportRequest(StrictModel):
    content: StrictStr
    name: StrictStr | None = None
    confirm_overwrite: StrictBool = False


def event_envelope(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "version": API_VERSION, "payload": dict(payload)}
