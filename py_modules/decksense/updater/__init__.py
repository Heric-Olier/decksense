"""Self-updater module.

Pulls new releases from the project's GitHub repo and installs them
through Decky's "install from ZIP" flow with UI-visible progress. Mirrors
the pattern used by other ecosystem plugins (e.g. Panel de Control).

Future layout:
- ``adapters/``  — GitHub releases API client.
- ``services/``  — version comparison, download + verify + install.
"""
