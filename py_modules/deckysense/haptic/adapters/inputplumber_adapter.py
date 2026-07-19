"""InputPlumber D-Bus adapter for the Lenovo Legion Go S.

Speaks to ``org.shadowblip.Output.ForceFeedback`` on the composite
device that InputPlumber creates for the Go S. We shell out to
``gdbus`` instead of pulling in a D-Bus Python dependency — gdbus is
always present on SteamOS and the rumble path is not latency-critical
enough to justify a native binding.

Environment strategy:
- Inherit the parent env (gdbus needs D-Bus auth context from it)
- Strip ``LD_LIBRARY_PATH`` (Decky's bundled libgio breaks system gdbus)
- Strip ``_PYI_*`` vars (PyInstaller artifacts can interfere with D-Bus)
- Override ``USER``/``HOME`` so polkit identifies the correct user
- Add ``INSECURE_DISABLE_POLKIT=1`` as belt-and-suspenders
"""

from __future__ import annotations

import os
import subprocess

from . import HapticBackend

DBUS_SERVICE = "org.shadowblip.InputPlumber"
DBUS_PATH = "/org/shadowblip/InputPlumber/CompositeDevice0"
DBUS_INTERFACE = "org.shadowblip.Output.ForceFeedback"


def _build_env() -> dict[str, str]:
    """Build the gdbus subprocess env: inherit parent, strip problem vars."""
    env = dict(os.environ)
    env.pop("LD_LIBRARY_PATH", None)
    # Strip PyInstaller artifacts that interfere with D-Bus auth.
    for key in list(env):
        if key.startswith("_PYI_"):
            del env[key]
    # Ensure polkit sees the right user regardless of parent env quirks.
    env["USER"] = "deck"
    env["HOME"] = "/home/deck"
    env["INSECURE_DISABLE_POLKIT"] = "1"
    return env


class InputPlumberAdapter(HapticBackend):
    """Talks to InputPlumber via the ``gdbus`` CLI."""

    def rumble(self, intensity: float) -> None:
        clamped = max(0.0, min(float(intensity), 1.0))
        self._call("Rumble", str(clamped))

    def stop(self) -> None:
        self._call("Stop")

    @staticmethod
    def _call(method: str, *args: str) -> None:
        cmd = [
            "/usr/bin/gdbus",
            "call",
            "--system",
            "--dest",
            DBUS_SERVICE,
            "--object-path",
            DBUS_PATH,
            "--method",
            f"{DBUS_INTERFACE}.{method}",
            *args,
        ]
        try:
            result = subprocess.run(
                cmd,
                env=_build_env(),
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"gdbus binary not found at /usr/bin/gdbus: {exc}"
            ) from exc
        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"gdbus exit {result.returncode}: {err}")
