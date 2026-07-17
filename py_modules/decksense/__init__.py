"""DeckSense backend package.

Subpackages:
- ``display``   — gamescope filter wrapper (Display Studio).
- ``haptic``    — rumble backend abstraction + per-device calibrations
                  (Haptic Studio).
- ``profiles``  — appId detection + preset orchestration (Game Profiles).
- ``updater``   — self-update from GitHub releases.

The entrypoint lives in ``main.py`` at the project root; Decky Loader
adds this directory to ``sys.path`` at runtime so plugins can import
their own modules as ``from decksense import ...``.
"""

__version__ = "0.0.1"
