"""Kernel FF_GAIN backend.

Switches InputPlumber to the ``xb360`` target so games see a standard
evdev force-feedback device.  We then try every available API to set a
global gain:

- ``EV_FF`` / ``FF_GAIN`` event  (modern kernel API)
- ``EVIOCSGAIN`` ioctl           (legacy kernel API — same effect)

**Known limitation.**  InputPlumber's xb360 target reads the original
(unscaled) effect magnitudes during the uinput upload callback, *before*
the kernel applies ``ff->gain``.  This means the gain value is stored in
the kernel but does **not** propagate to what InputPlumber forwards to
the hardware.  The slider *does* affect the plugin's own preview (which
goes through ``EVIOCSFF`` directly).

We keep this backend because on some devices the xb360 target itself
handles rumble differently from ``deck-uhid``, and future InputPlumber
versions *might* read ``ff->gain`` upstream.

When switching away from this backend, ``close()`` resets the
InputPlumber target back to the original ``deck-uhid`` controller.
"""

from __future__ import annotations

import fcntl
import os
import struct
import subprocess
import threading
import time
from typing import final

import decky

from . import HapticBackend

# ── evdev constants ────────────────────────────────────────────────
EV_FF       = 0x15
FF_RUMBLE   = 0x50
FF_GAIN     = 0x60
EVIOCSFF    = 0x40304580
EVIOCRMFF   = 0x40044581
EVIOCSGAIN  = 0x40024582
_FF_EFFECT_FMT = "<HhHHHHHxxHH28x"
_EVENT_FMT  = "<llHHi"

_VENDOR_MICROSOFT = 0x045e
_TARGET_DECK_UHID = "['deck-uhid']"
_TARGET_XB360     = "['xb360']"
_DBUS_CALL_BASE = [
    "gdbus", "call", "--system",
    "--dest", "org.shadowblip.InputPlumber",
    "--object-path", "/org/shadowblip/InputPlumber/CompositeDevice0",
]


@final
class FFGainBackend(HapticBackend):
    """Switch to xb360 target and attempt kernel-level gain for game rumble.

    **Gain may not affect games** — InputPlumber reads original effect
    magnitudes before the kernel applies ``ff->gain``.  Preview always
    respects the gain slider.
    """

    id = "ff_gain"
    name = "FF_GAIN"
    description = (
        "Switches to Xbox 360 controller emulation. "
        "Gain affects the plugin preview. "
        "Game gain is best-effort — InputPlumber reads effect magnitudes "
        "before the kernel applies FF_GAIN, so the slider may not "
        "change game rumble. Switch away to restore the default controller."
    )
    features = frozenset({"gain", "game_gain"})

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fd: int | None = None
        self._effect_id: int | None = None
        self._gain: float = 1.0
        self._switch_target(_TARGET_XB360)
        self._find_device()

    # ── public API ──────────────────────────────────────────────────

    def rumble(self, intensity: float, balance: float = 0.5) -> None:
        if self._fd is None:
            raise RuntimeError("FFGainBackend: no device fd")
        clamped = max(0.0, min(1.0, intensity))
        bal = max(0.0, min(1.0, balance))
        strong = round(0xFFFF * clamped * min(1.0, bal * 2.0))
        weak   = round(0xFFFF * clamped * min(1.0, (1.0 - bal) * 2.0))
        if self._effect_id is not None:
            try:
                fcntl.ioctl(self._fd, EVIOCRMFF, self._effect_id)
            except OSError:
                pass
            self._effect_id = None
        buf = bytearray(struct.pack(
            _FF_EFFECT_FMT, FF_RUMBLE, -1, 0, 0, 0, 500, 0, strong, weak,
        ))
        try:
            fcntl.ioctl(self._fd, EVIOCSFF, buf, True)
            self._effect_id = struct.unpack_from("<h", buf, 2)[0]
            ev = struct.pack(_EVENT_FMT, 0, 0, EV_FF, self._effect_id, 1)
            os.write(self._fd, ev)
        except OSError as exc:
            raise RuntimeError(f"FFGainBackend: rumble failed: {exc}") from exc

    def stop(self) -> None:
        if self._fd is not None and self._effect_id is not None:
            ev = struct.pack(_EVENT_FMT, 0, 0, EV_FF, self._effect_id, 0)
            try:
                os.write(self._fd, ev)
            except OSError:
                pass

    def set_kernel_gain(self, gain: float) -> None:
        clamped = max(0.0, min(1.0, float(gain)))
        with self._lock:
            self._gain = clamped
        self._write_gain(clamped)

    def set_balance(self, balance: float) -> None:
        pass  # Kernel FF_GAIN is global — no per-effect split.

    def close(self) -> None:
        """Reset gain, close fd, and restore deck-uhid target."""
        fd = self._fd
        if fd is not None:
            try:
                self._write_gain(1.0)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass
            self._fd = None
        self._switch_target(_TARGET_DECK_UHID)

    # ── target switching ────────────────────────────────────────────

    def _switch_target(self, target_list: str) -> None:
        """Tell InputPlumber which target device type to emit."""
        try:
            subprocess.run(
                [*_DBUS_CALL_BASE,
                 "--method",
                 "org.shadowblip.Input.CompositeDevice.SetTargetDevices",
                 target_list],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except FileNotFoundError:
            decky.logger.warning("FFGainBackend: gdbus not found; cannot switch target")
        except Exception as exc:
            decky.logger.warning("FFGainBackend: target switch failed: %s", exc)

    # ── device discovery ────────────────────────────────────────────

    def _find_device(self) -> None:
        """Scan /dev/input/event* for the xb360 virtual device."""
        time.sleep(0.5)
        import glob
        for path in sorted(
            glob.glob("/dev/input/event*"),
            key=lambda p: int(p.replace("/dev/input/event", "")),
        ):
            try:
                fd = os.open(path, os.O_RDWR)
            except OSError:
                continue
            name = self._query_name(fd)
            vid  = self._query_vendor(fd)
            if vid == _VENDOR_MICROSOFT or "xbox" in name.lower() or "xpad" in name.lower():
                self._fd = fd
                decky.logger.info("FFGainBackend: found device %s (%s)", path, name)
                self._write_gain(self._gain)
                return
            os.close(fd)
        decky.logger.warning("FFGainBackend: no xb360 device; scanning any FF device")
        for path in sorted(
            glob.glob("/dev/input/event*"),
            key=lambda p: int(p.replace("/dev/input/event", "")),
        ):
            try:
                fd = os.open(path, os.O_RDWR)
            except OSError:
                continue
            if self._probe_ff(fd):
                self._fd = fd
                name = self._query_name(fd)
                decky.logger.info("FFGainBackend: fallback device %s (%s)", path, name)
                self._write_gain(self._gain)
                return
            os.close(fd)
        decky.logger.error("FFGainBackend: no FF-capable device found")

    # ── gain writer (belt + suspenders) ─────────────────────────────

    def _write_gain(self, gain: float) -> None:
        """Write gain via EV_FF event AND EVIOCSGAIN ioctl."""
        if self._fd is None:
            return
        raw = round(0xFFFF * max(0.0, min(1.0, gain)))
        # Modern path: EV_FF / FF_GAIN event
        try:
            ev = struct.pack(_EVENT_FMT, 0, 0, EV_FF, FF_GAIN, raw)
            os.write(self._fd, bytes(ev))
        except OSError as exc:
            decky.logger.warning("FFGainBackend: EV_FF/FF_GAIN failed: %s", exc)
        # Legacy path: EVIOCSGAIN ioctl
        try:
            fcntl.ioctl(self._fd, EVIOCSGAIN, struct.pack("<H", raw))
        except OSError as exc:
            decky.logger.warning("FFGainBackend: EVIOCSGAIN failed: %s", exc)

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _query_name(fd: int) -> str:
        EVIOCGNAME = 0x82004506
        buf = bytearray(256)
        try:
            fcntl.ioctl(fd, EVIOCGNAME, buf, True)
            return buf.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        except OSError:
            return ""

    @staticmethod
    def _query_vendor(fd: int) -> int:
        EVIOCGID = 0x80084502
        buf = bytearray(8)
        try:
            fcntl.ioctl(fd, EVIOCGID, buf, True)
            return struct.unpack_from("<H", buf, 2)[0]
        except OSError:
            return 0

    @staticmethod
    def _probe_ff(fd: int) -> bool:
        buf = bytearray(struct.pack(
            _FF_EFFECT_FMT, FF_RUMBLE, -1, 0, 0, 0, 10, 0, 1, 1,
        ))
        try:
            fcntl.ioctl(fd, EVIOCSFF, buf, True)
            eid = struct.unpack_from("<h", buf, 2)[0]
            ev = struct.pack(_EVENT_FMT, 0, 0, EV_FF, eid, 0)
            os.write(fd, ev)
            return True
        except OSError:
            return False
