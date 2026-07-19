"""DeckySense self-updater.

Pulls new releases from the project's GitHub repo and installs them
through Decky's plugin loader. Pattern adapted from Panel de Control.

Design rules
------------
- Public functions never raise; they return a status dict that the
  frontend renders uniformly, including the error state.
- ``check()`` is session-cached so multiple consumers (the panel and
  the AlertDot on the tab icon) share state without re-fetching.
- The ``systemctl restart plugin_loader`` call hides Decky's bundled
  libcrypto so systemctl can load the system OpenSSL.
- Plugin root is derived from ``__file__``, not ``decky.DECKY_PLUGIN_DIR``,
  because the latter can be unreliable depending on how Decky initialises
  the Python environment.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import decky

# ── Plugin identity ────────────────────────────────────────────────
# Derived from __file__ so the updater works even when decky.DECKY_PLUGIN_DIR
# is unreliable (e.g. PyInstaller builds, certain Decky versions).
# Layout:  py_modules/deckysense/updater/self_updater.py
#            ▲         ▲       ▲
#            3         2       1  ← .parent calls to reach plugin root


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_PLUGIN_ROOT = _plugin_root()
_PKG = _read_json(_PLUGIN_ROOT / "package.json")
_PLUGIN_JSON = _read_json(_PLUGIN_ROOT / "plugin.json")

PLUGIN_NAME: str = _PKG.get("name", "deckysense")
CURRENT_VERSION: str = _PKG.get("version", "0.0.0")

GITHUB_OWNER: str = "Heric-Olier"
GITHUB_REPO: str = "DeckySense"
RELEASES_URL: str = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)

# Session cache: only hit GitHub once per plugin process (force=True bypasses it).
_cache: dict[str, Any] = {}


# ── Version helpers ────────────────────────────────────────────────

_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _extract_semver(tag: str) -> str:
    """Pull the X.Y.Z out of a tag string (copes with release-please prefixes)."""
    m = _SEMVER.search(tag or "")
    return m.group(0) if m else ""


def _norm(v: str) -> tuple[int, int, int]:
    m = _SEMVER.search(v or "")
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _is_newer(latest: str, current: str) -> bool:
    return _norm(latest) > _norm(current)


# ── SSL context (same approach as Panel de Control) ────────────────

_CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ssl/cert.pem",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
)


def _build_ssl_context() -> ssl.SSLContext:
    """Load the system CA bundle explicitly.

    Decky's PyInstaller environment can ship without a usable CA bundle
    or set ``SSL_CERT_FILE`` to a broken path, which makes
    ``ssl.create_default_context()`` produce a context that can't verify
    GitHub's cert. Walk known CA paths and load whichever exists.
    """
    ctx = ssl.create_default_context()
    for path in _CA_BUNDLES:
        if os.path.exists(path):
            try:
                ctx.load_verify_locations(path)
            except Exception:
                continue
            break
    return ctx


_SSL_CONTEXT = _build_ssl_context()

_UA = "decky-self-updater"


def _http_get(url: str, accept: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": accept}
    )
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
        return resp.read()


# ── Status shape ───────────────────────────────────────────────────


@dataclass
class UpdateStatus:
    """Status surface returned to the frontend."""

    state: str  # idle | checking | available | up_to_date | installing | done | error
    current_version: str
    latest_version: Optional[str] = None
    release_notes: Optional[str] = None
    asset_url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Public API ─────────────────────────────────────────────────────


def check(force: bool = False) -> dict[str, Any]:
    """Query GitHub for the latest release. Cached per session.

    Pass ``force=True`` to bypass the cache (used by the manual
    "Check for updates" button).
    """
    global _cache
    if _cache and not force:
        return _cache

    status = UpdateStatus(state="checking", current_version=CURRENT_VERSION)
    try:
        data = json.loads(_http_get(RELEASES_URL, "application/vnd.github+json"))

        latest = _extract_semver(str(data.get("tag_name", "")))
        status.latest_version = latest or CURRENT_VERSION
        status.release_notes = str(data.get("body", "") or "")

        # Asset naming in the release workflow: out/<name>-v<version>.zip
        # e.g. "deckysense-v0.0.15.zip". Match any zip whose name contains
        # the plugin name and the latest semver tag.
        name_candidate = _PLUGIN_JSON.get("name", PLUGIN_NAME).lower()
        tag_version = latest  # e.g. "0.0.15"
        asset_url: Optional[str] = None
        for asset in data.get("assets") or []:
            aname = (asset.get("name") or "").lower()
            if aname.endswith(".zip") and name_candidate in aname and tag_version in aname:
                asset_url = asset.get("browser_download_url")
                break
        status.asset_url = asset_url

        status.state = (
            "available"
            if latest and asset_url and _is_newer(latest, CURRENT_VERSION)
            else "up_to_date"
        )

    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            decky.logger.info("[updater] no published release yet")
            status.state = "up_to_date"
        else:
            decky.logger.warning(f"[updater] check failed: {exc}")
            status.state = "error"
            status.error = "network"
    except Exception as exc:  # noqa: BLE001 — surface as status, never raise.
        decky.logger.warning(f"[updater] check failed: {exc}")
        status.state = "error"
        status.error = "network"

    result = status.to_dict()
    _cache = result
    return result


def install() -> dict[str, Any]:
    """Download the latest release zip and overwrite the plugin dir.

    Never raises: returns a status dict with error codes on failure.
    """
    info = check()
    url = str(info.get("asset_url") or "")
    if not url:
        return UpdateStatus(
            state="error",
            current_version=CURRENT_VERSION,
            error="no_asset",
        ).to_dict()

    status = UpdateStatus(
        state="installing",
        current_version=CURRENT_VERSION,
        latest_version=str(info.get("latest_version", "")),
        asset_url=url,
    )

    try:
        blob = _http_get(url, "application/octet-stream")

        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)
            zpath = tmpd / "update.zip"
            zpath.write_bytes(blob)

            extract = tmpd / "x"
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(extract)

            # Zip top-level dir matches package.json "name" (lowercase),
            # not plugin.json "name" (which may be capitalized for display).
            src = extract / PLUGIN_NAME
            if not src.is_dir():
                src = extract / _PLUGIN_JSON.get("name", "")
            if not src.is_dir():
                subdirs = [p for p in extract.iterdir() if p.is_dir()]
                if len(subdirs) == 1:
                    src = subdirs[0]
            if not src.is_dir():
                raise RuntimeError("bad_zip: no plugin folder found")

            # Purge existing files so we don't trip over root-owned files
            # left by a manual sudo install.  Removing/unlinking a file only
            # requires w+x on the *parent directory* (which deck owns), not
            # on the file itself — so this works even when individual file
            # inodes are owned by root.
            for existing in list(_PLUGIN_ROOT.iterdir()):
                if existing.name in (".", ".."):
                    continue
                if existing.is_dir():
                    shutil.rmtree(existing)
                else:
                    existing.unlink()

            for item in src.iterdir():
                dest = _PLUGIN_ROOT / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

        _mark_installed()
        status.state = "done"

    except Exception as exc:  # noqa: BLE001
        decky.logger.error(f"[updater] install failed: {exc}")
        status.state = "error"
        status.error = f"install_failed: {exc}"

    return status.to_dict()


def restart_loader() -> dict[str, Any]:
    """Restart Decky's plugin loader so the new code takes effect."""
    env = dict(os.environ)
    # Decky's PyInstaller build points LD_LIBRARY_PATH at its bundled libs,
    # which makes systemctl fail with "OPENSSL_x not found". Restore the
    # pre-bundle path if available, otherwise drop LD_LIBRARY_PATH.
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig is not None:
        env["LD_LIBRARY_PATH"] = orig
    else:
        env.pop("LD_LIBRARY_PATH", None)
    try:
        subprocess.Popen(
            ["/usr/bin/systemctl", "restart", "plugin_loader"],
            env=env,
            start_new_session=True,
        )
        return {"state": "restarting"}
    except Exception as exc:  # noqa: BLE001
        decky.logger.error(f"[updater] restart failed: {exc}")
        return {"state": "error", "error": f"{type(exc).__name__}: {exc}"}


def _mark_installed() -> None:
    global _cache
    if _cache:
        _cache = {
            **_cache,
            "current_version": _cache.get("latest_version", _cache.get("current_version")),
            "state": "done",
        }
    else:
        _cache = {"state": "done", "current_version": CURRENT_VERSION}
