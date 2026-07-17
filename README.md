# DeckSense

> Display, haptic and per-game profile studio for PC handhelds on SteamOS.

DeckSense is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader)
plugin suite that brings display calibration, software-enhanced haptics
and automatic per-game profiles to PC handhelds. It is being built with
the **Lenovo Legion Go S** as the reference device, and is designed so
that other handhelds can be added as their hardware support is verified.

## Modules

- **Display Studio** — visual filters via gamescope (Sharp, Pixel Art,
  OLED-like, plus per-game profiles).
- **Haptic Studio** — software-side haptic enhancement (gain, response
  curve, envelope shaping) for handhelds with limited rumble motors.
- **Game Profiles** — applies the right Display + Haptic preset for the
  running game automatically.

## Status

Early development. See [`ROADMAP.md`](./ROADMAP.md) for the current
status per phase and [`DEVLOG.md`](./DEVLOG.md) for the chronological
record of technical decisions.

## Compatibility

Compatibility is reported **honestly**. Cells are not filled in until
they are confirmed on the actual hardware.

| Device                  | Display      | Haptic         | Profiles     |
| ----------------------- | ------------ | -------------- | ------------ |
| Lenovo Legion Go S      | Planned      | Investigating  | Planned      |
| Steam Deck OLED / LCD   | Planned      | N/A            | Planned      |
| ASUS ROG Ally / Ally X  | Investigating| Investigating  | Investigating|
| Other handhelds         | Investigating| Investigating  | Investigating|

- **Planned** — designed, not yet implemented.
- **Investigating** — pending hardware verification.
- **N/A** — not applicable (e.g. the Steam Deck already exposes HD
  haptics through Steam Input; DeckSense would not add value there).

## Installing

Not yet available in the Decky plugin store. Until the first tagged
release is published, the plugin can only be built from source (see
`DEVLOG.md`).

## Development

Requires Node.js v16.14+ and `pnpm` v9. Backend features that need
hardware access are validated on the device itself.

```bash
pnpm install
pnpm run build
```

## License

GPL-3.0. See [`LICENSE`](./LICENSE).
