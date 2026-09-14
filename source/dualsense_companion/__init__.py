"""DualSense Companion — audio-driven rumble and touchpad mouse for PC."""

import ctypes
import logging
import os
import sys

__version__ = "1.0.0"

# When frozen by PyInstaller, hidapi.dll is bundled at the extraction root.
# cffi looks it up by name, which won't search that folder, so preload it by
# full path first — Windows then reuses that handle for the by-name lookup.
if getattr(sys, "frozen", False):
    _dll = os.path.join(getattr(sys, "_MEIPASS", ""), "hidapi.dll")
    if os.path.exists(_dll):
        try:
            ctypes.CDLL(_dll)
        except OSError as exc:
            # PyInstaller can still resolve the DLL by its bundled path.
            logging.getLogger(__name__).debug("optional hidapi preload failed: %s", exc)
