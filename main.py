"""DeckySense backend entrypoint.

Decky Loader instantiates the ``Plugin`` class below once per plugin
lifecycle and invokes the underscore-prefixed hooks at the right
moments. Any other ``async def`` method on this class becomes an RPC
callable from the TypeScript frontend via ``@decky/api``'s
``callable("method_name")``.
"""

from __future__ import annotations

import asyncio
import json
import os as _os
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

    # --- RPC: debug ------------------------------------------------------

    async def debug_haptic_test(self) -> dict[str, Any]:
        """Run the exact gdbus call from this plugin's context.

        Returns the call's outcome plus the plugin's PID/UID/env so we
        can diagnose why an authorised polkit rule is being refused.
        Also dumps the full info to /tmp/deckysense-haptic-debug.json for
        easy retrieval from SSH/desktop mode.
        """
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
