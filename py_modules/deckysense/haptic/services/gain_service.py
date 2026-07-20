"""Gain service.

Owns the current ``HapticParams`` and the active backend.  Exposes
operations the frontend needs: read/write gain, read/write balance,
trigger a preview pulse, and — new — list available backends / hot-
swap the active backend.

Persistence uses ``decky.set_setting`` / ``decky.get_setting``.
"""

from __future__ import annotations

from typing import Any, Optional

import decky

from ..adapters import HapticBackend
from ..adapters.registry import create_backend, list_backends
from ..domain import DEFAULT_BALANCE, DEFAULT_GAIN, HapticParams

SETTING_KEY_GAIN      = "haptic.gain"
SETTING_KEY_BALANCE   = "haptic.balance"
SETTING_KEY_BACKEND   = "haptic.backend_id"


# ── helpers ────────────────────────────────────────────────────────


def _read_setting(key: str, default: Any) -> Any:
    getter = getattr(decky, "get_setting", None)
    if callable(getter):
        try:
            return getter(key, default)
        except Exception:  # noqa: BLE001
            decky.logger.exception("decky.get_setting raised; falling back to default")
    return default


def _write_setting(key: str, value: Any) -> None:
    setter = getattr(decky, "set_setting", None)
    if callable(setter):
        try:
            setter(key, value)
        except Exception:  # noqa: BLE001
            decky.logger.exception("decky.set_setting raised; setting not persisted")


# ── service ────────────────────────────────────────────────────────


class GainService:
    """Single-instance service that owns haptic params + active backend."""

    def __init__(self) -> None:
        self._backend: HapticBackend | None = None
        self._params: HapticParams = HapticParams(
            gain=DEFAULT_GAIN, balance=DEFAULT_BALANCE
        )

    # ── backend management ─────────────────────────────────────────

    @property
    def active_backend_id(self) -> str:
        if self._backend is None:
            return ""
        return self._backend.id

    def list_backends(self) -> list[dict[str, Any]]:
        return list_backends()

    def get_backend_info(self) -> dict[str, Any]:
        """Return metadata about the currently active backend."""
        if self._backend is None:
            return {"id": "", "name": "None", "description": "No backend active", "features": []}
        return {
            "id": self._backend.id,
            "name": self._backend.name,
            "description": self._backend.description,
            "features": sorted(self._backend.features),
        }

    def switch_backend(self, backend_id: str) -> dict[str, Any]:
        """Hot-swap the active backend.  Persists the choice.

        If the new backend fails to initialise, the old backend is kept
        and the error is returned in the response.
        """
        if self._backend is not None and self._backend.id == backend_id:
            return self.get_backend_info()
        try:
            new = create_backend(backend_id)
        except (KeyError, RuntimeError) as exc:
            decky.logger.error("switch_backend(%s) failed: %s", backend_id, exc)
            info = self.get_backend_info()
            info["error"] = f"Failed: {exc}"
            return info
        old = self._backend
        self._backend = new
        if old is not None:
            try:
                old.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._backend.set_kernel_gain(min(1.0, self._params.gain))
        except Exception:  # noqa: BLE001
            pass
        try:
            self._backend.set_balance(self._params.balance)
        except Exception:  # noqa: BLE001
            pass
        _write_setting(SETTING_KEY_BACKEND, backend_id)
        decky.logger.info("switched haptic backend to %s", backend_id)
        return self.get_backend_info()

    def load_from_settings(self) -> None:
        """Load persisted params and start the last-used backend."""
        stored_gain = _read_setting(SETTING_KEY_GAIN, DEFAULT_GAIN)
        stored_balance = _read_setting(SETTING_KEY_BALANCE, DEFAULT_BALANCE)
        stored_backend = _read_setting(SETTING_KEY_BACKEND, "inputplumber")
        try:
            gain = float(stored_gain)
        except (TypeError, ValueError):
            gain = DEFAULT_GAIN
        try:
            balance = float(stored_balance)
        except (TypeError, ValueError):
            balance = DEFAULT_BALANCE
        self._params = HapticParams(gain=gain, balance=balance).clamped()
        # Start the selected backend (fall back to inputplumber on error)
        try:
            self._backend = create_backend(str(stored_backend))
        except Exception:  # noqa: BLE001
            decky.logger.warning(
                "failed to create backend '%s', falling back to inputplumber",
                stored_backend,
                exc_info=True,
            )
            try:
                self._backend = create_backend("inputplumber")
            except Exception:  # noqa: BLE001
                decky.logger.exception("inputplumber backend also failed; no haptic available")
                return
        try:
            self._backend.set_kernel_gain(min(1.0, self._params.gain))
        except Exception:  # noqa: BLE001
            pass
        try:
            self._backend.set_balance(self._params.balance)
        except Exception:  # noqa: BLE001
            pass

    # ── params ─────────────────────────────────────────────────────

    def get_params(self) -> dict[str, Any]:
        return {"gain": self._params.gain, "balance": self._params.balance}

    def set_gain(self, value: float) -> dict[str, Any]:
        self._params = HapticParams(
            gain=float(value), balance=self._params.balance
        ).clamped()
        _write_setting(SETTING_KEY_GAIN, self._params.gain)
        if self._backend is not None:
            try:
                self._backend.set_kernel_gain(min(1.0, self._params.gain))
            except Exception:  # noqa: BLE001
                pass
        return self.get_params()

    def set_balance(self, value: float) -> dict[str, Any]:
        self._params = HapticParams(
            gain=self._params.gain, balance=float(value)
        ).clamped()
        _write_setting(SETTING_KEY_BALANCE, self._params.balance)
        if self._backend is not None:
            try:
                self._backend.set_balance(self._params.balance)
            except Exception:  # noqa: BLE001
                pass
        return self.get_params()

    # ── preview ────────────────────────────────────────────────────

    def preview(self, raw_intensity: float = 0.5) -> dict[str, Any]:
        """Trigger a rumble at ``raw_intensity * gain``, clamped to 1.0."""
        if self._backend is None:
            return {"state": "error", "error": "No active backend"}
        try:
            amplified = min(1.0, float(raw_intensity) * self._params.gain)
            self._backend.rumble(amplified, self._params.balance)
            return {
                "state": "playing",
                "intensity": amplified,
                "gain": self._params.gain,
                "balance": self._params.balance,
            }
        except Exception as exc:  # noqa: BLE001
            decky.logger.exception("haptic preview failed")
            return {"state": "error", "error": f"{type(exc).__name__}: {exc}"}

    def close_backend(self) -> None:
        """Close the active backend (called on plugin unload)."""
        if self._backend is not None:
            try:
                self._backend.close()
            except Exception:  # noqa: BLE001
                pass
            self._backend = None

    def stop(self) -> dict[str, Any]:
        if self._backend is None:
            return {"state": "stopped"}
        try:
            self._backend.stop()
            return {"state": "stopped"}
        except Exception as exc:  # noqa: BLE001
            decky.logger.exception("haptic stop failed")
            return {"state": "error", "error": f"{type(exc).__name__}: {exc}"}


# ── module-level singleton ─────────────────────────────────────────

_instance: Optional[GainService] = None


def get_gain_service() -> GainService:
    global _instance
    if _instance is None:
        _instance = GainService()
    return _instance
