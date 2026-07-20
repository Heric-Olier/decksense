"""Evdev force-feedback adapter for the Lenovo Legion Go S.

Uses ``EVIOCSFF`` + ``EV_FF`` ioctls directly on the native gamepad event
device. This bypasses polkit and D-Bus entirely.
"""

from __future__ import annotations

import fcntl
import os
import struct

from . import HapticBackend

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

    def rumble(self, intensity: float, balance: float = 0.5) -> None:
        self._ensure_open()
        clamped = max(0.0, min(1.0, intensity))
        bal = max(0.0, min(1.0, balance))
        strong = round(0xFFFF * clamped * min(1.0, bal * 2.0))
        weak = round(0xFFFF * clamped * min(1.0, (1.0 - bal) * 2.0))
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


# ── Module-level evdev singleton ─────────────────────────────────────

_evdev = _EvdevFF()


# ── Public adapter ─────────────────────────────────────────────────


class InputPlumberAdapter(HapticBackend):
    """Sends rumble via evdev (no D-Bus dependency)."""

    def rumble(self, intensity: float, balance: float = 0.5) -> None:
        clamped = max(0.0, min(float(intensity), 1.0))
        _evdev.rumble(clamped, balance)

    def stop(self) -> None:
        _evdev.stop()
