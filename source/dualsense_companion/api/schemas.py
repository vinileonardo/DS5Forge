"""Typed HTTP contracts for the local API v1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, model_validator

Number = StrictInt | StrictFloat

API_VERSION = 1
API_PREFIX = "/api/v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatchModel(StrictModel):
    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} may not be null")
        return self


class RumbleConfig(StrictModel):
    heavy_cutoff_hz: Number = Field(ge=1, le=20_000)
    texture_center_hz: Number = Field(ge=1, le=20_000)
    fast_attack_ms: Number = Field(gt=0, le=10_000)
    fast_release_ms: Number = Field(gt=0, le=10_000)
    baseline_attack_ms: Number = Field(gt=0, le=10_000)
    baseline_release_ms: Number = Field(gt=0, le=20_000)
    gate: Number = Field(ge=0, le=1)
    impact_level: Number = Field(gt=0, le=1)
    gamma: Number = Field(gt=0, le=10)
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
    fast_attack_ms: Number | None = Field(default=None, gt=0, le=10_000)
    fast_release_ms: Number | None = Field(default=None, gt=0, le=10_000)
    baseline_attack_ms: Number | None = Field(default=None, gt=0, le=10_000)
    baseline_release_ms: Number | None = Field(default=None, gt=0, le=20_000)
    gate: Number | None = Field(default=None, ge=0, le=1)
    impact_level: Number | None = Field(default=None, gt=0, le=1)
    gamma: Number | None = Field(default=None, gt=0, le=10)
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


class TrackpadConfigPatch(PatchModel):
    trackpad_enabled_on_start: StrictBool | None = None
    pointer_speed: Number | None = Field(default=None, ge=0.01, le=10)
    acceleration: Number | None = Field(default=None, ge=0, le=1)
    accel_cap: Number | None = Field(default=None, ge=0, le=10)
    scroll_speed: Number | None = Field(default=None, ge=0.01, le=10)
    tap_to_click: StrictBool | None = None


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


class ControllerCapabilitiesResponse(StrictModel):
    usb: bool
    rumble: bool
    touchpad: bool
    microphone_button: bool
    lightbar: bool
    adaptive_triggers: bool


class BatteryResponse(StrictModel):
    level: int = Field(ge=0, le=100)
    charging: bool | None


class MotorResponse(StrictModel):
    left: int = Field(ge=0, le=255)
    right: int = Field(ge=0, le=255)


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


class ProfileLoadResponse(StrictModel):
    profile: str
    config: ConfigResponse


class ProfileSaveResponse(StrictModel):
    profile: str
    rumble: RumbleConfig


class DeleteProfileResponse(StrictModel):
    deleted: str


class RumbleTestResponse(StrictModel):
    accepted: bool


def event_envelope(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "version": API_VERSION, "payload": dict(payload)}
