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
    adaptive_trigger_output_reports: bool = False
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
    contact_id: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


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
    intensity: Number = Field(default=1.0, ge=0, le=1)
    effect: str = "steady"


class PlayerLedResponse(StrictModel):
    enabled: StrictBool
    intensity: Number = Field(ge=0, le=1)


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


class StickCalibrationSample(StrictModel):
    left_x: Number = Field(ge=-1, le=1)
    left_y: Number = Field(ge=-1, le=1)
    right_x: Number = Field(ge=-1, le=1)
    right_y: Number = Field(ge=-1, le=1)


class StickCalibrationEstimateRequest(StrictModel):
    samples: list[StickCalibrationSample] = Field(min_length=12, max_length=512)


class StickDriftAnalysisResponse(StrictModel):
    center_x: Number = Field(ge=-1, le=1)
    center_y: Number = Field(ge=-1, le=1)
    drift_radius: Number = Field(ge=0, le=2)
    jitter_radius: Number = Field(ge=0, le=2)
    recommended_deadzone: Number = Field(ge=0, le=1)
    samples_used: StrictInt = Field(ge=0, le=512)
    rejected_samples: StrictInt = Field(ge=0, le=512)


class StickCalibrationEstimateResponse(StrictModel):
    samples: StrictInt = Field(ge=0, le=512)
    left: StickDriftAnalysisResponse
    right: StickDriftAnalysisResponse
    recommended_calibration: StickCalibrationResponse


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


class ForegroundApplicationResponse(StrictModel):
    available: bool
    pid: int | None
    executable_name: str | None
    executable_path: str | None
    title: str | None
    observed_at: float
    process_alive: bool
    diagnostic: str | None


class GameDefinitionRequest(StrictModel):
    id: StrictStr
    name: StrictStr
    executables: list[StrictStr] = Field(min_length=1, max_length=16)
    executable_path: StrictStr | None = None
    profile: StrictStr = "Default"
    compatibility_mode: Literal["native", "remap", "virtual"] = "native"
    adaptive_trigger_mode: Literal["native", "reactive", "off"] = "native"
    adaptive_trigger_strength: StrictInt = Field(default=45, ge=10, le=100)
    enabled: StrictBool = True


class GameDefinitionResponse(GameDefinitionRequest):
    pass


class GamesResponse(StrictModel):
    games: list[GameDefinitionResponse]


class GameCandidateResponse(StrictModel):
    executable_name: str
    executable_path: str | None
    pid: int | None
    title: str | None
    source: Literal["running", "recent"] | str
    observed_at: float


class GameCandidatesResponse(StrictModel):
    candidates: list[GameCandidateResponse]


class RuleEvaluationResponse(StrictModel):
    game_id: str
    game_name: str
    matched: bool
    reason: str
    action: str
    profile: str | None
    compatibility_mode: Literal["native", "remap", "virtual"] | None


class GameMatchResponse(StrictModel):
    matched: bool
    game_id: str | None
    game_name: str | None
    reason: str
    foreground: ForegroundApplicationResponse
    evaluations: list[RuleEvaluationResponse]


class GameMatchStateResponse(StrictModel):
    matched: bool
    game_id: str | None
    game_name: str | None
    reason: str
    foreground: ForegroundApplicationResponse


class ActiveGameResponse(StrictModel):
    game: GameDefinitionResponse | None
    automation: dict[str, Any]


class AutomationUpdateRequest(PatchModel):
    enabled: StrictBool | None = None
    exit_policy: Literal["restore_previous", "apply_default", "keep_current"] | None = None
    default_profile: StrictStr | None = None


class AutomationResponse(StrictModel):
    enabled: bool
    exit_policy: Literal["restore_previous", "apply_default", "keep_current"]
    default_profile: str
    active_game_id: str | None
    active_game_name: str | None
    active_profile: str
    profile_origin: Literal["manual", "automatic"]
    manual_override: bool
    last_match: GameMatchStateResponse | None
    rule_evaluations: list[RuleEvaluationResponse]
    previous_profile: str | None
    previous_compatibility_mode: Literal["native", "remap", "virtual"] | None
    transition: int
    last_transition_at: float
    status: str
    diagnostic: str | None
    foreground: ForegroundApplicationResponse | None = None
    active_game: GameDefinitionResponse | None = None


class VirtualControllerCapabilityResponse(StrictModel):
    installed: bool
    available: bool
    physical_suppression_supported: bool
    provider: str | None
    reason: str | None


class ProviderProvenanceResponse(StrictModel):
    provider: str
    version: str | None
    executable: str | None
    sha256: str | None
    signature_verified: bool
    provenance_verified: bool
    integrity_verified: bool
    windows_validated: bool
    evidence: list[str]


class ExclusiveCapabilityResponse(StrictModel):
    provider_available: bool
    provider_installed: bool
    virtual_output_reports: bool
    physical_output_passthrough: bool
    physical_suppression_available: bool
    physical_suppression_verified: bool
    provenance: ProviderProvenanceResponse
    reason: str


class ExclusiveStatusResponse(StrictModel):
    mode: Literal["off", "starting", "active", "stopping", "error"]
    enabled: bool
    generation: int
    ownership_acquired: bool
    heartbeat_at: float
    heartbeat_timeout_ms: int
    stale: bool
    physical_input_visible: bool
    virtual_input_active: bool
    physical_suppression_active: bool
    double_input_risk: bool
    capability: ExclusiveCapabilityResponse
    reason: str | None
    last_error: str | None
    mirrored_sequence: int
    updated_at: float


class DuplicateInputDiagnosticResponse(StrictModel):
    risk: bool
    physical_visible: bool
    virtual_active: bool
    suppression_verified: bool
    exclusive_enabled: bool
    severity: str
    message: str
    evidence: list[str]
    checked_at: float


class InputIsolationCapabilityResponse(StrictModel):
    provider: str
    installed: bool
    available: bool
    version: str | None
    executable: str | None
    application_path: str | None
    device_detected: bool
    device_instance_path: str | None
    reason: str | None


class InputIsolationStatusResponse(StrictModel):
    active: bool
    owned: bool
    cloak_enabled: bool
    application_registered: bool
    device_hidden: bool
    physical_input_visible: bool
    double_input_risk: bool
    device_instance_path: str | None
    capability: InputIsolationCapabilityResponse
    reason: str | None
    last_error: str | None
    updated_at: float


class CompatibilityStateResponse(StrictModel):
    mode: Literal["native", "remap", "virtual"]
    available: bool
    virtual_capability: VirtualControllerCapabilityResponse
    physical_input_visible: bool
    virtual_input_active: bool
    physical_suppression_active: bool
    double_input_risk: bool
    reason: str | None
    changed_at: float


class CompatibilityUpdateRequest(StrictModel):
    mode: Literal["native", "remap", "virtual"]


class MappingResponse(StrictModel):
    id: StrictStr
    input: StrictStr
    output_kind: Literal["keyboard", "mouse"]
    output_code: StrictStr
    game_id: StrictStr | None = None
    enabled: StrictBool = True
    debounce_ms: StrictInt = Field(default=25, ge=1, le=500)


class MappingsResponse(StrictModel):
    mappings: list[MappingResponse]


class MappingsUpdateRequest(StrictModel):
    mappings: list[MappingResponse]


class ChordResponse(StrictModel):
    id: StrictStr
    inputs: list[StrictStr]
    output_kind: Literal["keyboard", "mouse"]
    output_code: StrictStr
    game_id: StrictStr | None = None
    enabled: StrictBool = True
    window_ms: StrictInt = Field(default=250, ge=25, le=1_000)
    debounce_ms: StrictInt = Field(default=25, ge=1, le=500)


class ChordsResponse(StrictModel):
    chords: list[ChordResponse]


class ChordsUpdateRequest(StrictModel):
    chords: list[ChordResponse]


class SyntheticOutputResponse(StrictModel):
    kind: Literal["keyboard", "mouse", "logical"]
    code: str


class ReleaseReportResponse(StrictModel):
    reason: str
    released: list[SyntheticOutputResponse]
    failures: list[str]
    completed: bool


class SyntheticOutputStateResponse(StrictModel):
    held: list[SyntheticOutputResponse]
    last_release: ReleaseReportResponse | None
    release_status: str


class ConflictDiagnosticResponse(StrictModel):
    process: str
    running: bool
    severity: str
    message: str
    evidence: str | None
    checked_at: float


class ConflictDiagnosticsResponse(StrictModel):
    conflicts: list[ConflictDiagnosticResponse]


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
    player_leds: PlayerLedResponse = PlayerLedResponse(enabled=True, intensity=1.0)
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
    foreground: ForegroundApplicationResponse | None = None
    automation: AutomationResponse | None = None
    compatibility: CompatibilityStateResponse | None = None
    synthetic_outputs: SyntheticOutputStateResponse | None = None
    conflicts: list[ConflictDiagnosticResponse] = Field(default_factory=list)
    exclusive: ExclusiveStatusResponse | None = None


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
    intensity: Number = Field(default=1.0, ge=0, le=1)
    effect: str = Field(default="steady", max_length=32)


class PlayerLedApplyRequest(StrictModel):
    enabled: StrictBool = True
    intensity: Number = Field(default=1.0, ge=0, le=1)


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


# P4 productization contracts.  They intentionally live beside the existing
# v1 contracts so the SPA, shell and support tooling share one versioned wire
# boundary.
class AppInfoResponse(StrictModel):
    name: str
    version: str
    api_version: int
    transport_scope: Literal["usb_wired_only"]
    platform: str
    python: str
    release_channel: str
    features: dict[str, bool]


class LifecycleResponse(StrictModel):
    state: str
    core: str
    pid: StrictInt | None
    message: str | None


class DiagnosticCheckResponse(StrictModel):
    key: str
    status: Literal["healthy", "warning", "unavailable", "failed", "not_applicable"]
    summary: str
    action: str | None
    detail: str | None


class GuidedDiagnosticsResponse(StrictModel):
    status: Literal["healthy", "warning", "unavailable", "failed", "not_applicable"]
    checks: list[DiagnosticCheckResponse]
    counts: dict[str, int]


class UpdateCheckRequest(StrictModel):
    version: StrictStr = Field(max_length=64)
    notes: StrictStr = Field(default="", max_length=8_192)
    pub_date: StrictStr | None = None
    signature: StrictStr = Field(max_length=16_384)
    installer_url: StrictStr = Field(max_length=2_048)
    target: StrictStr = Field(default="windows-x86_64", max_length=64)


class UpdateCheckResponse(StrictModel):
    available: StrictBool
    status: str
    version: str | None = None
    notes: str | None = None
    message: str | None = None


class RemotePairingStartRequest(StrictModel):
    origin_hint: StrictStr | None = Field(default=None, max_length=2_048)


class RemotePairingStartResponse(StrictModel):
    pairing_id: str
    code: str
    expires_at: float
    origin_hint: str | None


class RemotePairingCompleteRequest(StrictModel):
    pairing_id: StrictStr = Field(max_length=128)
    code: StrictStr = Field(min_length=6, max_length=6)
    origin: StrictStr = Field(max_length=2_048)


class RemoteSessionResponse(StrictModel):
    session_id: str
    origin: str
    created_at: float
    expires_at: float
    expired: StrictBool
    revoked: StrictBool


class RemoteStatusResponse(StrictModel):
    enabled: StrictBool
    status: str
    origins: list[str]
    sessions: list[RemoteSessionResponse]
    pairing_active: StrictBool


class RemoteRevokeResponse(StrictModel):
    revoked: StrictBool


class TunnelConfigureRequest(StrictModel):
    executable: StrictStr | None = Field(default=None, max_length=512)
    config_path: StrictStr | None = Field(default=None, max_length=512)


class TunnelStatusResponse(StrictModel):
    status: str
    executable: str | None
    config: str | None
    message: str | None
