"""Virtual-controller boundary and deterministic fake used by tests.

P3 intentionally ships no Windows virtual gamepad provider. The fake makes
compatibility gating and teardown testable without installing a driver.
"""

from __future__ import annotations

from ..domain.games import VirtualControllerCapability


class FakeVirtualControllerProvider:
    def __init__(
        self,
        *,
        installed: bool = True,
        available: bool = True,
        physical_suppression_supported: bool = True,
        provider: str = "fake",
    ) -> None:
        self._capability = VirtualControllerCapability(
            installed=installed,
            available=available,
            physical_suppression_supported=physical_suppression_supported,
            provider=provider,
            reason=None
            if installed and available and physical_suppression_supported
            else "The provider is unavailable or cannot suppress physical input safely.",
        )
        self.started = False
        self.events: list[tuple[str, str, bool]] = []

    def capability(self) -> VirtualControllerCapability:
        return self._capability

    def start(self) -> None:
        if not self._capability.operational:
            raise RuntimeError("fake virtual controller is not operational")
        self.started = True

    def send_button(self, code: str, down: bool) -> None:
        if not self.started:
            raise RuntimeError("fake virtual controller is not started")
        self.events.append(("button", str(code), bool(down)))

    def release_all(self) -> None:
        self.events.append(("release_all", "", False))

    def close(self) -> None:
        self.started = False


def virtual_capability(provider: object | None) -> VirtualControllerCapability:
    if provider is None:
        return VirtualControllerCapability()
    capability = getattr(provider, "capability", None)
    if not callable(capability):
        return VirtualControllerCapability(reason="Configured virtual-controller provider has no capability probe.")
    try:
        value = capability()
    except Exception as exc:
        return VirtualControllerCapability(reason=f"Virtual-controller capability probe failed: {exc}")
    return (
        value
        if isinstance(value, VirtualControllerCapability)
        else VirtualControllerCapability(reason="Virtual-controller provider returned an invalid capability value.")
    )


def ensure_virtual_provider(provider: object | None) -> VirtualControllerCapability:
    return virtual_capability(provider)
