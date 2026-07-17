"""Haptic Studio module.

Owns the rumble backend abstraction. Future layout:
- ``adapters/``     — HapticBackend interface + per-device implementations
                      (sysfs / hidraw / InputPlumber).
- ``services/``     — gain, response curve, envelope shaping.
- ``calibrations/`` — per-device motor profiles (dead-zone, saturation).
- ``domain.py``     — HapticParams model.

The actual backend path (kernel sysfs vs InputPlumber) is undecided
until Phase 0 validation confirms what the Lenovo Legion Go S exposes.
"""
