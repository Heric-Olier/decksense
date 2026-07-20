"""Gain service.

Owns the current ``HapticParams`` and exposes the operations the
frontend needs: read/write gain, and a preview pulse so the user can
feel the effect of their settings.

Gain is the simplest transform: multiply the requested intensity by
the configured gain, clamp to [0.0, 1.0] (the hardware ceiling).

Persistence uses ``decky.set_setting`` / ``decky.get_setting`` if
available; if those are missing (the API surface has shifted between
Decky Loader versions), the service silently degrades to in-memory
only and logs the issue.
"""

from __future__ import annotations

from typing import Any, Optional

import decky

from ..adapters import HapticBackend
from ..adapters.inputplumber_adapter import InputPlumberAdapter
from ..domain import DEFAULT_BALANCE, DEFAULT_GAIN, HapticParams

SETTING_KEY_GAIN = "haptic.gain"
SETTING_KEY_BALANCE = "haptic.balance"


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


class GainService:
    """Single-instance service that owns haptic params."""

    def __init__(self, backend: Optional[HapticBackend] = None) -> None:
        self._backend: HapticBackend = backend or InputPlumberAdapter()
        self._params: HapticParams = HapticParams(
            gain=DEFAULT_GAIN, balance=DEFAULT_BALANCE
        )

    def load_from_settings(self) -> None:
        stored_gain = _read_setting(SETTING_KEY_GAIN, DEFAULT_GAIN)
        stored_balance = _read_setting(SETTING_KEY_BALANCE, DEFAULT_BALANCE)
        try:
            gain = float(stored_gain)
        except (TypeError, ValueError):
            gain = DEFAULT_GAIN
        try:
            balance = float(stored_balance)
        except (TypeError, ValueError):
            balance = DEFAULT_BALANCE
        self._params = HapticParams(gain=gain, balance=balance).clamped()

    def get_params(self) -> dict[str, Any]:
        return {"gain": self._params.gain, "balance": self._params.balance}

    def set_gain(self, value: float) -> dict[str, Any]:
        self._params = HapticParams(
            gain=float(value), balance=self._params.balance
        ).clamped()
        _write_setting(SETTING_KEY_GAIN, self._params.gain)
        return self.get_params()

    def set_balance(self, value: float) -> dict[str, Any]:
        self._params = HapticParams(
            gain=self._params.gain, balance=float(value)
        ).clamped()
        _write_setting(SETTING_KEY_BALANCE, self._params.balance)
        return self.get_params()

    def preview(self, raw_intensity: float = 0.5) -> dict[str, Any]:
        """Trigger a rumble at ``raw_intensity * gain``, clamped to 1.0."""
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

    def stop(self) -> dict[str, Any]:
        try:
            self._backend.stop()
            return {"state": "stopped"}
        except Exception as exc:  # noqa: BLE001
            decky.logger.exception("haptic stop failed")
            return {"state": "error", "error": f"{type(exc).__name__}: {exc}"}


# Module-level singleton so RPC handlers in main.py share state.
_instance: Optional[GainService] = None


def get_gain_service() -> GainService:
    global _instance
    if _instance is None:
        _instance = GainService()
    return _instance
