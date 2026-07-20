"""DeckySense backend entrypoint.

Decky Loader instantiates the ``Plugin`` class below once per plugin
lifecycle and invokes the underscore-prefixed hooks at the right
moments. Any other ``async def`` method on this class becomes an RPC
callable from the TypeScript frontend via ``@decky/api``'s
``callable("method_name")``.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os as _os
import struct
from typing import Any

import decky

from deckysense.haptic.services.gain_service import get_gain_service
from deckysense.updater import self_updater


class Plugin:
    """Lifecycle handler for the DeckySense backend."""

    loop: asyncio.AbstractEventLoop

    async def _main(self) -> None:
        self.loop = asyncio.get_event_loop()
        decky.logger.info(
            "DeckySense backend started (v%s)", self_updater.CURRENT_VERSION
        )
        # Discover what settings API the running Decky Loader exposes.
        # Across versions the names have moved around; this log helps
        # diagnose persistence failures without crashing _main().
        api_surface = sorted(
            n for n in dir(decky) if not n.startswith("_") and "set" in n.lower() or "get" in n.lower()
        )
        decky.logger.info("decky api surface (get/set): %s", api_surface)
        try:
            get_gain_service().load_from_settings()
        except Exception:  # noqa: BLE001
            decky.logger.exception("gain_service.load_from_settings failed; using defaults")

    async def _unload(self) -> None:
        decky.logger.info("DeckySense backend stopping")
        try:
            get_gain_service().close_backend()
        except Exception:  # noqa: BLE001
            pass

    async def _uninstall(self) -> None:
        decky.logger.info("DeckySense uninstalled")

    async def _migration(self) -> None:
        decky.logger.info("DeckySense migration check (no-op)")

    # --- RPC: updater ----------------------------------------------------

    async def get_current_version(self) -> str:
        return self_updater.CURRENT_VERSION

    async def check_for_update(self, force: bool = False) -> dict[str, Any]:
        return await self.loop.run_in_executor(None, self_updater.check, force)

    async def install_update(self) -> dict[str, Any]:
        return await self.loop.run_in_executor(None, self_updater.install)

    async def restart_loader(self) -> dict[str, Any]:
        return await self.loop.run_in_executor(None, self_updater.restart_loader)

    # --- RPC: haptic ------------------------------------------------------

    async def get_haptic_params(self) -> dict[str, Any]:
        return get_gain_service().get_params()

    async def set_haptic_gain(self, value: float) -> dict[str, Any]:
        return await self.loop.run_in_executor(
            None, get_gain_service().set_gain, value
        )

    async def set_haptic_balance(self, value: float) -> dict[str, Any]:
        return await self.loop.run_in_executor(
            None, get_gain_service().set_balance, value
        )

    async def preview_rumble(self, raw_intensity: float = 0.5) -> dict[str, Any]:
        return await self.loop.run_in_executor(
            None, get_gain_service().preview, raw_intensity
        )

    async def stop_rumble(self) -> dict[str, Any]:
        return await self.loop.run_in_executor(None, get_gain_service().stop)

    # --- RPC: haptic backend management -----------------------------------

    async def list_haptic_backends(self) -> list[dict[str, Any]]:
        return get_gain_service().list_backends()

    async def get_haptic_backend_info(self) -> dict[str, Any]:
        return get_gain_service().get_backend_info()

    async def switch_haptic_backend(self, backend_id: str) -> dict[str, Any]:
        return await self.loop.run_in_executor(
            None, get_gain_service().switch_backend, backend_id
        )

    # --- RPC: debug ------------------------------------------------------

    async def debug_haptic_test(self) -> dict[str, Any]:
        """Run the exact gdbus call from this plugin's context."""
        from deckysense.haptic.adapters.inputplumber_adapter import InputPlumberAdapter

        info: dict[str, Any] = {
            "pid": _os.getpid(),
            "uid": _os.getuid(),
            "gid": _os.getgid(),
            "env_keys": sorted(_os.environ.keys()),
        }
        try:
            InputPlumberAdapter().rumble(0.3)
            info["state"] = "ok"
        except Exception as exc:
            info["state"] = "error"
            info["error"] = f"{type(exc).__name__}: {exc}"
        try:
            with open("/tmp/deckysense-haptic-debug.json", "w") as _f:
                json.dump(info, _f, indent=2)
        except Exception:
            pass
        return info

    async def debug_haptic_dump(self) -> dict[str, Any]:
        """Comprehensive diagnostic dump for haptic subsystem.

        Returns backend info, params, device scan, and environment.
        Also writes to /tmp/deckysense-haptic-dump.json for SSH retrieval.
        """
        import glob as _glob

        svc = get_gain_service()
        backend_info = svc.get_backend_info()
        params = svc.get_params()
        backends = svc.list_backends()
        version = self_updater.CURRENT_VERSION

        # Scan /dev/input/event* for FF-capable devices
        devices: list[dict[str, Any]] = []
        for path in sorted(
            _glob.glob("/dev/input/event*"),
            key=lambda p: int(p.replace("/dev/input/event", "")),
        ):
            try:
                fd = os.open(path, os.O_RDWR)
            except OSError:
                continue
            try:
                name = self._query_evdev_name(fd)
                vid = self._query_evdev_vid(fd)
                has_ff = self._probe_ff(fd)
                devices.append({"path": path, "name": name, "vendor": f"0x{vid:04x}", "has_ff": has_ff})
            finally:
                os.close(fd)

        dump: dict[str, Any] = {
            "version": version,
            "backend": backend_info,
            "params": params,
            "backends": backends,
            "devices": devices,
            "pid": _os.getpid(),
            "uid": _os.getuid(),
        }
        try:
            with open("/tmp/deckysense-haptic-dump.json", "w") as _f:
                json.dump(dump, _f, indent=2)
        except Exception:
            pass
        return dump

    @staticmethod
    def _query_evdev_name(fd: int) -> str:
        EVIOCGNAME = 0x82004506
        buf = bytearray(256)
        try:
            fcntl.ioctl(fd, EVIOCGNAME, buf, True)
            return buf.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
        except OSError:
            return ""

    @staticmethod
    def _query_evdev_vid(fd: int) -> int:
        EVIOCGID = 0x80084502
        buf = bytearray(8)
        try:
            fcntl.ioctl(fd, EVIOCGID, buf, True)
            return struct.unpack_from("<H", buf, 2)[0]
        except OSError:
            return 0

    @staticmethod
    def _probe_ff(fd: int) -> bool:
        buf = bytearray(struct.pack("<HhHHHHHxxHH28x", 0x50, -1, 0, 0, 0, 10, 0, 1, 1))
        try:
            fcntl.ioctl(fd, 0x40304580, buf, True)
            eid = struct.unpack_from("<h", buf, 2)[0]
            ev = struct.pack("<llHHi", 0, 0, 0x15, eid, 0)
            os.write(fd, ev)
            return True
        except OSError:
            return False
