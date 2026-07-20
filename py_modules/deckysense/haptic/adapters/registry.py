"""Backend registry — single source of truth for available backends.

Every backend class is registered here.  The service layer uses this
module to list backends (for the frontend) and to instantiate them
by id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import HapticBackend

# ── imports ────────────────────────────────────────────────────────

# Lazy — we only import the concrete backends when needed so that a
# failing init in one backend doesn't prevent others from working.

_BACKEND_CLASSES: dict[str, type[HapticBackend]] = {}


def _ensure_loaded() -> None:
    if _BACKEND_CLASSES:
        return
    from .inputplumber_adapter import InputPlumberAdapter  # noqa: PLC0415
    from .ff_gain import FFGainBackend                     # noqa: PLC0415
    from .uinput_proxy import UinputProxy                   # noqa: PLC0415

    _BACKEND_CLASSES["inputplumber"] = InputPlumberAdapter
    _BACKEND_CLASSES["ff_gain"] = FFGainBackend
    _BACKEND_CLASSES["uinput_proxy"] = UinputProxy


# ── public API ─────────────────────────────────────────────────────


def list_backends() -> list[dict[str, Any]]:
    """Return metadata for every registered backend."""
    _ensure_loaded()
    result: list[dict[str, Any]] = []
    for bid, cls in _BACKEND_CLASSES.items():
        result.append({
            "id": bid,
            "name": cls.name,
            "description": cls.description,
            "features": sorted(cls.features),
        })
    return result


def create_backend(backend_id: str) -> HapticBackend:
    """Instantiate a backend by id.

    Raises ``KeyError`` if the id is unknown, or ``RuntimeError`` with
    the original exception chain if construction fails.
    """
    _ensure_loaded()
    cls = _BACKEND_CLASSES[backend_id]
    try:
        return cls()
    except Exception as exc:
        raise RuntimeError(
            f"Failed to create backend '{backend_id}': {exc}"
        ) from exc
