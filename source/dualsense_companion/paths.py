"""Resolve bundled resources and the writable user config directory."""

import glob
import os
import shutil
import sys

APP_NAME = "DualSense Companion"


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def config_dir():
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, APP_NAME)


def profiles_dir():
    return os.path.join(config_dir(), "profiles")


def config_file():
    return os.path.join(config_dir(), "config.json")


def ensure_seeded():
    """Copy bundled defaults into the user config dir on first run."""
    os.makedirs(config_dir(), exist_ok=True)
    os.makedirs(profiles_dir(), exist_ok=True)
    if not os.path.exists(config_file()):
        shutil.copy(resource_path(os.path.join("resources", "default_config.json")), config_file())
    seed_profiles = glob.glob(resource_path(os.path.join("resources", "profiles", "*.json")))
    for src in seed_profiles:
        dst = os.path.join(profiles_dir(), os.path.basename(src))
        if not os.path.exists(dst):
            shutil.copy(src, dst)
