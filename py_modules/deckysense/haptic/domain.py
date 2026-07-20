"""Haptic domain models.

Pure dataclasses, no I/O. The services layer composes and validates
these; the adapter layer applies them to the hardware.
"""

from __future__ import annotations

from dataclasses import dataclass

# Conservative defaults for the Lenovo Legion Go S, derived from the
# Phase 0 rumble sweep (gradual response across 0.05–1.0, no obvious
# dead-zone or saturation knee).
DEFAULT_GAIN = 1.0
GAIN_MIN = 0.0
GAIN_MAX = 2.0

# Strong/weak motor balance: 0.0 = all weak, 0.5 = equal, 1.0 = all strong
DEFAULT_BALANCE = 0.5
BALANCE_MIN = 0.0
BALANCE_MAX = 1.0


@dataclass(frozen=True)
class HapticParams:
    """User-tunable haptic parameters.

    ``gain``: global intensity multiplier [0.0–2.0].
    ``balance``: strong/weak motor split [0.0–1.0]; 0.5 = equal.
    """

    gain: float = DEFAULT_GAIN
    balance: float = DEFAULT_BALANCE

    def clamped(self) -> "HapticParams":
        return HapticParams(
            gain=max(GAIN_MIN, min(self.gain, GAIN_MAX)),
            balance=max(BALANCE_MIN, min(self.balance, BALANCE_MAX)),
        )
