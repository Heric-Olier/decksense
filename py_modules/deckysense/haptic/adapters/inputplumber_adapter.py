"""InputPlumber D-Bus adapter for the Lenovo Legion Go S.

Speaks to ``org.shadowblip.Output.ForceFeedback`` on the composite
device that InputPlumber creates for the Go S. We shell out to
``gdbus`` instead of pulling in a D-Bus Python dependency — gdbus is
always present on SteamOS and the rumble path is not latency-critical
enough to justify a native binding.

The subprocess environment has ``LD_LIBRARY_PATH`` stripped because
plugin_loader sets it to Decky's bundled library directory, which
breaks ``gdbus`` (it loads a different libgio/libglib and exits 1
silently). Same pattern as ``restart_loader()``.
"""

from __future__ import annotations

import os
import subprocess

from . import HapticBackend

DBUS_SERVICE = "org.shadowblip.InputPlumber"
DBUS_PATH = "/org/shadowblip/InputPlumber/CompositeDevice0"
DBUS_INTERFACE = "org.shadowblip.Output.ForceFeedback"


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("LD_LIBRARY_PATH", None)
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
                env=_clean_env(),
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"gdbus binary not found at /usr/bin/gdbus: {exc}") from exc
        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"gdbus exit {result.returncode}: {err}")
