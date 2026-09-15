"""PyInstaller entry point for the headless DS5Forge core sidecar."""

from dualsense_companion.app import main

if __name__ == "__main__":
    main(["--headless"])
