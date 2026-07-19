"""InputPlumber D-Bus + evdev force-feedback adapter for the Lenovo Legion Go S.

Primary path: D-Bus via ``gdbus`` talking to InputPlumber's
``org.shadowblip.Output.ForceFeedback.Rumble(double)`` on the composite device.

Fallback path: evdev ``EVIOCSFF`` + ``EV_FF`` ioctls directly on the native
gamepad event device. This bypasses polkit entirely.
"""

from __future__ import annotations

import fcntl
import os
import struct
import subprocess

from . import HapticBackend

# ── D-Bus constants ────────────────────────────────────────────────

DBUS_SERVICE = "org.shadowblip.InputPlumber"
DBUS_PATH = "/org/shadowblip/InputPlumber/CompositeDevice0"
DBUS_INTERFACE = "org.shadowblip.Output.ForceFeedback"

# ── evdev constants ────────────────────────────────────────────────

EV_FF = 0x15
FF_RUMBLE = 0x50
# sizeof(struct ff_effect) = 48 on x86_64 Linux
# EVIOCSFF = _IOW('E', 0x80, struct ff_effect)
EVIOCSFF = 0x40304580  # (1 << 30) | (48 << 16) | (ord('E') << 8) | 0x80


def _pack_ff_effect(strong: int, weak: int, length_ms: int = 500) -> bytes:
    """Pack a ``struct ff_effect`` for EVIOCSFF (48 bytes, x86_64 layout)."""
    return struct.pack(
        "<HhHHHHHxxHH28x",
        FF_RUMBLE,       # type    (offset  0)
        -1,              # id      (offset  2, -1 = auto-assign)
        0,               # dir     (offset  4)
        0,               # trig b  (offset  6)
        0,               # trig i  (offset  8)
        length_ms & 0xFFFF,  # replay.length (offset 10)
        0,               # replay.delay   (offset 12)
        # 2 bytes padding (offset 14)
        strong & 0xFFFF, # u.rumble.strong_magnitude (offset 16)
        weak & 0xFFFF,   # u.rumble.weak_magnitude   (offset 18)
        # 28 bytes padding (offset 20-47)
    )


def _evdev_find() -> int | None:
    """Scan /dev/input/event*, return first fd where EVIOCSFF succeeds."""
    import glob
    for path in sorted(glob.glob("/dev/input/event*"), key=lambda p: int(p.replace("/dev/input/event", ""))):
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError:
            continue
        try:
            buf = bytearray(_pack_ff_effect(1, 1, 10))
            fcntl.ioctl(fd, EVIOCSFF, buf, True)
            effect_id = struct.unpack_from("<h", buf, 2)[0]
            ev = struct.pack("<qqHHi", 0, 0, EV_FF, effect_id, 0)
            os.write(fd, ev)
            return fd
        except OSError:
            os.close(fd)
            continue
    return None



# ── Evdev force-feedback wrapper (stateful, keeps fd open) ─────────


class _EvdevFF:
    """Upload and play rumble via evdev ioctls (no D-Bus, no polkit)."""

    def __init__(self) -> None:
        self._fd: int | None = None
        self._effect_id: int | None = None

    def _ensure_open(self) -> None:
        if self._fd is not None:
            return
        fd = _evdev_find()
        if fd is None:
            raise RuntimeError(
                "evdev: no /dev/input/event* device supports force-feedback"
            )
        self._fd = fd

    def rumble(self, intensity: float) -> None:
        self._ensure_open()
        strong = round(0xFFFF * max(0.0, min(1.0, intensity)))
        weak = strong
        buf = bytearray(_pack_ff_effect(strong, weak))
        fcntl.ioctl(self._fd, EVIOCSFF, buf, True)
        self._effect_id = struct.unpack_from("<h", buf, 2)[0]
        play = struct.pack("<qqHHi", 0, 0, EV_FF, self._effect_id, 1)
        os.write(self._fd, play)

    def stop(self) -> None:
        if self._fd is None:
            return
        if self._effect_id is not None:
            ev = struct.pack("<qqHHi", 0, 0, EV_FF, self._effect_id, 0)
            try:
                os.write(self._fd, ev)
            except OSError:
                pass

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self._effect_id = None


# ── D-Bus helper (tried first) ────────────────────────────────────


def _build_env() -> dict[str, str]:
    """Build the gdbus subprocess env: inherit parent, strip problem vars."""
    env = dict(os.environ)
    env.pop("LD_LIBRARY_PATH", None)
    for key in list(env):
        if key.startswith("_PYI_"):
            del env[key]
    env["USER"] = "deck"
    env["HOME"] = "/home/deck"
    env["INSECURE_DISABLE_POLKIT"] = "1"
    return env


def _run_gdbus(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run gdbus and return the result. Never raises."""
    try:
        return subprocess.run(
            cmd,
            env=_build_env(),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        result = subprocess.CompletedProcess(cmd, -1, "", "gdbus not found")
        return result


# ── Module-level evdev fallback ─────────────────────────────────────

_evdev = _EvdevFF()


# ── Public adapter ─────────────────────────────────────────────────


class InputPlumberAdapter(HapticBackend):
    """Sends rumble to the Legion Go S via gdbus D-Bus or evdev fallback."""

    def rumble(self, intensity: float) -> None:
        clamped = max(0.0, min(float(intensity), 1.0))
        self._call(clamped)

    def stop(self) -> None:
        _evdev.stop()

    @staticmethod
    def _call(intensity: float) -> None:
        cmd = [
            "/usr/bin/gdbus",
            "call",
            "--system",
            "--dest",
            DBUS_SERVICE,
            "--object-path",
            DBUS_PATH,
            "--method",
            f"{DBUS_INTERFACE}.Rumble",
            str(intensity),
        ]
        result = _run_gdbus(cmd)
        if result.returncode == 0:
            return

        err = (result.stderr or result.stdout or "").lower()
        if "not authorized" in err:
            _evdev.rumble(intensity)
            return

        raise RuntimeError(f"gdbus exit {result.returncode}: {result.stderr.strip()}")
