"""DeckSense backend entrypoint.

Decky Loader instantiates the ``Plugin`` class below once per plugin
lifecycle and invokes the underscore-prefixed hooks at the right
moments. Any other ``async def`` method on this class becomes an RPC
callable from the TypeScript frontend via ``@decky/api``'s
``callable("method_name")``.

For now this is a thin skeleton: the real per-module backends live in
``py_modules/decksense/`` and will be wired in as each module lands.
"""

import asyncio

import decky


class Plugin:
    """Lifecycle handler for the DeckSense backend."""

    loop: asyncio.AbstractEventLoop

    async def _main(self) -> None:
        self.loop = asyncio.get_event_loop()
        decky.logger.info("DeckSense backend started")

    async def _unload(self) -> None:
        decky.logger.info("DeckSense backend stopping")

    async def _uninstall(self) -> None:
        decky.logger.info("DeckSense uninstalled")

    async def _migration(self) -> None:
        decky.logger.info("DeckSense migration check (no-op for now)")
