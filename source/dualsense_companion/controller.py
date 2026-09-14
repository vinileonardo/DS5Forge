"""Compatibility name for the P0 controller lifecycle service."""

from .core.controller_service import ControllerService


class ControllerManager(ControllerService):
    """Deprecated adapter retained for imports from the upstream baseline.

    New application code constructs ``CoreFacade`` and injects a controller
    factory. This class intentionally does not expose a shared ``ds`` object.
    """

    def __init__(self, state, *args, **kwargs):
        facade = getattr(state, "facade", None)
        if facade is None:
            raise TypeError("ControllerManager now requires a CoreFacade-backed state")
        super().__init__(facade.controller.factory, *args, **kwargs)


__all__ = ["ControllerManager", "ControllerService"]
