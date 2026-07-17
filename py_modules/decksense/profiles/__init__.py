"""Game Profiles module.

Orchestrates Display + Haptic presets per running game. Future layout:
- ``adapters/``  — appId detection (whatever mechanism SteamOS exposes).
- ``services/``  — apply profile on appId change, CRUD for stored profiles.
- ``domain.py``  — Profile model mapping appId -> {display, haptic} preset.
"""
