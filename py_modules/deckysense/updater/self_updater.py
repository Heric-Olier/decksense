"""DeckySense self-updater.

Pulls new releases from the project's GitHub repo and installs them
through Decky's plugin loader. Pattern adapted from Panel de Control.

Design rules
------------
- Public functions never raise; they return a status dict that the
  frontend renders uniformly, including the error state.
- ``check()`` is session-cached so multiple consumers (the panel and
  the eventual AlertDot on the tab icon) share state without
  re-fetching.
- The ``systemctl restart plugin_loader`` call strips
  ``LD_LIBRARY_PATH`` so Decky's bundled libcrypto does not leak into
  the subprocess and break systemctl.
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import decky

# Plugin identity, read from package.json once at import time.
_PKG_JSON_PATH = Path(decky.DECKY_PLUGIN_DIR) / "package.json"
with _PKG_JSON_PATH.open(encoding="utf-8") as _f:
    _PKG = json.load(_f)

PLUGIN_NAME: str = _PKG["name"]
CURRENT_VERSION: str = _PKG.get("version", "0.0.0")

GITHUB_OWNER: str = "Heric-Olier"
# Match the GitHub repo's actual name (PascalCase) — the API does not
# follow case-insensitive redirects reliably.
GITHUB_REPO: str = "DeckySense"
RELEASES_URL: str = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)

# Session-level cache for ``check()``. Cleared after a successful install.
_cache: dict[str, Any] = {}


@dataclass
class UpdateStatus:
    """Status surface returned to the frontend.

    ``state`` is the only field the UI needs to switch on; the rest is
    payload depending on the state.
    """

    state: str  # idle | checking | available | up_to_date | installing | done | error
    current_version: str
    latest_version: Optional[str] = None
    release_notes: Optional[str] = None
    asset_url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context that trusts the host system's CA bundle.

    The plugin_loader process on SteamOS sometimes runs with an
    ``SSL_CERT_FILE`` that points to a non-existent or partial bundle,
    which makes ``urllib.request.urlopen`` fail with
    ``CERTIFICATE_VERIFY_FAILED``. We construct a default context and
    explicitly load the system CA files (Debian/Arch use
    ``/etc/ssl/certs/ca-certificates.crt``; Fedora/RHEL use
    ``/etc/pki/tls/certs/ca-bundle.crt``) so verification works
    regardless of the inherited environment.
    """
    try:
        ctx = ssl.create_default_context()
    except ssl.SSLError:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
    for cafile in (
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
    ):
        try:
            ctx.load_verify_locations(cafile=cafile)
        except (FileNotFoundError, ssl.SSLError):
            continue
    return ctx


_SSL_CONTEXT = _build_ssl_context()


def _build_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": PLUGIN_NAME,
        },
    )


def check(force: bool = False) -> dict[str, Any]:
    """Query GitHub for the latest release. Cached per session.

    Pass ``force=True`` to bypass the cache (used by the manual
    "Check for updates" button).
    """
    if not force and _cache:
        return _cache["status"]

    status = UpdateStatus(state="checking", current_version=CURRENT_VERSION)
    try:
        with urllib.request.urlopen(_build_request(RELEASES_URL), timeout=15, context=_SSL_CONTEXT) as resp:
            data = json.load(resp)

        tag = (data.get("tag_name") or "").lstrip("v")
        status.latest_version = tag
        status.release_notes = data.get("body") or ""

        asset_url: Optional[str] = None
        for asset in data.get("assets") or []:
            if (asset.get("name") or "").endswith(".zip"):
                asset_url = asset.get("browser_download_url")
                break
        status.asset_url = asset_url

        status.state = "available" if tag and tag != CURRENT_VERSION else "up_to_date"

    except Exception as exc:  # noqa: BLE001 — surface as status, never raise.
        decky.logger.exception("update check failed")
        status.state = "error"
        status.error = f"{type(exc).__name__}: {exc}"

    result = status.to_dict()
    _cache["status"] = result
    return result


def install() -> dict[str, Any]:
    """Download and install the latest release into the plugin dir.

    Assumes ``check()`` has run. If no asset URL is cached, runs a
    forced check first.
    """
    cached = _cache.get("status") or check(force=True)
    asset_url = cached.get("asset_url")
    if not asset_url:
        return UpdateStatus(
            state="error",
            current_version=CURRENT_VERSION,
            error="no asset URL available",
        ).to_dict()

    status = UpdateStatus(
        state="installing",
        current_version=CURRENT_VERSION,
        latest_version=cached.get("latest_version"),
        asset_url=asset_url,
    )

    try:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "release.zip"
            # urlretrieve doesn't accept an SSL context; use urlopen + write.
            with urllib.request.urlopen(asset_url, timeout=30, context=_SSL_CONTEXT) as r, \
                 zip_path.open("wb") as out:
                shutil.copyfileobj(r, out)

            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)

            staged: Optional[Path] = next(
                (
                    child
                    for child in Path(tmp).iterdir()
                    if (child / "plugin.json").exists()
                ),
                None,
            )
            if staged is None:
                raise RuntimeError("plugin folder not found in zip")

            plugin_dir = Path(decky.DECKY_PLUGIN_DIR)
            shutil.copytree(staged, plugin_dir, dirs_exist_ok=True)

        # The on-disk version may have changed; let the next check()
        # re-read package.json at module reload after restart_loader().
        _cache.clear()
        status.state = "done"

    except Exception as exc:  # noqa: BLE001
        decky.logger.exception("update install failed")
        status.state = "error"
        status.error = f"{type(exc).__name__}: {exc}"

    return status.to_dict()


def restart_loader() -> dict[str, Any]:
    """Restart Decky's plugin loader so the new code takes effect."""
    env = dict(os.environ)
    env.pop("LD_LIBRARY_PATH", None)  # don't leak Decky's libcrypto
    try:
        subprocess.Popen(
            ["/usr/bin/systemctl", "restart", "plugin_loader"],
            env=env,
            start_new_session=True,
        )
        return {"state": "restarting"}
    except Exception as exc:  # noqa: BLE001
        decky.logger.exception("restart_loader failed")
        return {"state": "error", "error": f"{type(exc).__name__}: {exc}"}
