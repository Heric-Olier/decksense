# Dev Log

A chronological log of technical decisions and progress. Newest entries
appear at the top.

The intent of this file is to be the source of truth for "why is the
code like this" — every non-trivial decision should be findable here.

---

## 2026-07-20 — v0.0.43: focus ring, UinputProxy fix, debug dump, FF_GAIN test

**Focus ring.** Steam stamps ``gpfocus`` on the focused ``Focusable``,
but Decky doesn't style it.  We now inject a stylesheet (inspired by
Panel de Control's ``ensureFocusStyles``) that draws a visible accent
glow — 4px white ring + soft halo — so gamepad navigation shows where
you are.  Injected once on plugin mount, scoped to the whole app.

**UinputProxy exception fixed.** ``_find_gamepad()`` raises
``RuntimeError`` when no device supports FF.  Now caught in
``create_backend()`` → ``switch_backend()`` preserves the old backend
and returns the error to the frontend instead of crashing.

**Debug dump.** New RPC ``debug_haptic_dump`` scans
``/dev/input/event*`` and returns every device's name, vendor and
FF capability alongside current backend info + params.  Written to
``/tmp/deckysense-haptic-dump.json`` for SSH retrieval.  Frontend
"Export debug log" button shows the dump inline.

**FF_GAIN test.** When the active backend supports ``game_gain``, two
buttons appear: "Gain 0 (mute)" and "Gain 1 (full)".  Lets the user
feel if kernel FF_GAIN actually affects game rumble.

**Files changed.** ``focus.ts`` (new), ``index.tsx``, ``registry.py``,
``gain_service.py``, ``main.py``, ``api.ts``, ``GainPanel.tsx``.

---

## 2026-07-20 — v0.0.42: fix FF_GAIN backend — reset target on close + docs

**Problem discovered.** Kernel ``FF_GAIN`` does not propagate to game
rumble because InputPlumber's xb360 target reads the original effect
magnitudes during the uinput upload callback, *before* the kernel
applies ``ff->gain``.  The gain value gets stored in the kernel but
never reaches what InputPlumber forwards to the hardware.

**Fixes in this release.**

- ``FFGainBackend.close()`` now calls ``SetTargetDevices(['deck-uhid'])``
  to restore the original controller when switching away from FF_GAIN
  mode (or on plugin unload).
- ``_write_gain()`` tries both ``EV_FF``/``FF_GAIN`` and ``EVIOCSGAIN``
  ioctl (belt and suspenders).
- Description in the UI updated to be honest: "Game gain is best-effort
  — InputPlumber reads effect magnitudes before the kernel applies
  FF_GAIN, so the slider may not change game rumble."
- UI redesigned: chip-based backend selector (like Panel de Control's
  ``FirmwareModes``) instead of stretched cards.

**Files changed.** ``ff_gain.py``, ``BackendCard.tsx``, ``GainPanel.tsx``.

---

## 2026-07-20 — v0.0.41: three backends + hot-swap UX

**Problem.** The uinput proxy (v0.0.40) creates a virtual device that no
game connects to — games send force-feedback through the `deck-uhid`
device managed by InputPlumber, not through the proxy. Gain/balance
still didn't reach games.

**Architecture: 3 backends, hot-swappable at runtime.**

The `HapticBackend` Protocol was enriched with identity metadata (`id`,
`name`, `description`, `features`) so the frontend can enumerate and
describe every backend without knowing its internals.

A `registry.py` module provides the single source of truth:

| Backend | id | Approach | Game gain |
|---------|----|----------|:---------:|
| D-Bus / Deck-UHID | `inputplumber` | evdev directly on real device | NO |
| Kernel FF_GAIN | `ff_gain` | Switch InputPlumber to xb360 target, write `EVIOCSGAIN` + `EV_FF`/`FF_GAIN` | **YES** |
| Uinput Proxy | `uinput_proxy` | Grab + proxy, per-effect intercept (original) | NO |

**Key files changed (v0.0.41).**

- `py_modules/deckysense/haptic/adapters/__init__.py` — Protocol now
  requires `id`, `name`, `description`, `features`.
- `py_modules/deckysense/haptic/adapters/registry.py` — **new.** Lazy
  registry + factory so failing backends don't block others.
- `py_modules/deckysense/haptic/adapters/ff_gain.py` — **new.** Switches
  InputPlumber target to `xb360` via D-Bus `SetTargetDevices`, then
  writes kernel `FF_GAIN` on the virtual Xbox 360 device. This is the
  first backend that can actually scale game rumble.
- `py_modules/deckysense/haptic/adapters/inputplumber_adapter.py` —
  Updated metadata.
- `py_modules/deckysense/haptic/adapters/uinput_proxy.py` — Updated
  metadata, marked experimental.
- `py_modules/deckysense/haptic/services/gain_service.py` — Refactored
  to support `switch_backend(id)` hot-swap. Persists `haptic.backend_id`
  in settings. Added `close_backend()` called on plugin unload.
- `main.py` — 3 new RPCs: `list_haptic_backends`, `get_haptic_backend_info`,
  `switch_haptic_backend`. Backend cleanup on `_unload`.
- `src/api.ts` — `BackendInfo` type + 3 callables for backend management.
- `src/haptic/BackendCard.tsx` — **new.** Selectable card for each
  backend with name, description, feature tags.
- `src/haptic/GainPanel.tsx` — Refactored: shows 3 backend cards, then
  gain/balance sliders that adapt to the active backend's features, plus
  a feature-summary table.

**Release workflow reminder.** After completing a feature:
1. Bump version in `package.json`.
2. Write `DEVLOG.md` entry at the top.
3. Commit all changes.
4. Tag with `v<version>`.
5. Push — the `release.yml` GitHub Action normally builds and uploads
   the zip automatically.
6. On the Legion Go S, open Settings → "Check for updates".

> **Note (2026-07-20).** GitHub Actions was having issues today, so
> v0.0.41 was published manually: commit + tag + push, then the release
> zip is available under GitHub Releases. The normal flow is fully
> automated via `.github/workflows/release.yml` — only do manual
> publishing when CI is unavailable.

---

## 2026-07-19 — v0.0.40: uinput proxy — gain/balance affects game rumble

**Problem.** `EVIOCSGAIN` (v0.0.39) looked like it would make gain/balance
work for all rumble on the device, but the `hid-lenovo-go-s` driver does
not implement `set_gain`. Games' force-feedback effects completely
ignored our settings — only the plugin's own preview was affected.

**Solution: uinput proxy device.** Instead of writing to the real
evdev device directly, `UinputProxy` (`adapters/uinput_proxy.py`):

1. Opens the real gamepad (`EVIOCGRAB` to get exclusive access).
2. Queries its capabilities (name, vendor/product IDs, supported keys/
   rel/abs axes, abs min/max/fuzz/flat ranges).
3. Creates a virtual `/dev/input/event*` device via uinput, mirroring
   the real device's capabilities (including proper ABS ranges so
   analog sticks work).
4. Spawns a reader thread that polls both fds — forwards input events
   from real → virtual, and intercepts force-feedback upload/erase
   requests from virtual ← kernel.
5. On `EVIOCSFF` (FF upload): parses `struct uinput_ff_upload`, applies
   gain + balance multipliers to `strong_magnitude`/`weak_magnitude`,
   forwards the modified effect to the real device, and returns the
   real effect id to the game.

**Key design decisions.**

- **Grab is required.** Without `EVIOCGRAB` the kernel delivers events
  to both the real device (consumed by Steam Input) and the proxy,
  causing double-input. Grab routes everything through the proxy.
  Danger: if the proxy crashes, the gamepad is stuck until a reboot or
  manual `EVIOCGRAB 0`. The `close()` method issues an ungrab.
- **Size-based FF detection.** The kernel writes raw `uinput_ff_upload`
  (104 bytes) or `uinput_ff_erase` (12 bytes) structs to the uinput fd.
  We distinguish them by read size, not by a bit-31 flag (which was
  incorrect in the draft).
- **Preview uses real fd directly.** Plugin preview bypasses the proxy
  and writes directly to the real fd (`_play_effect`), reusing the same
  effect-slot-freeing pattern from v0.0.38 to avoid `ENOSPC`.
- **Fallback.** If uinput init fails (no `/dev/uinput`, no gamepad), the
  service falls back to the plain evdev `InputPlumberAdapter`.

**Files changed (v0.0.35–v0.0.40).**

- `py_modules/deckysense/haptic/adapters/uinput_proxy.py` — new, ~545
  lines. The entire proxy device.
- `py_modules/deckysense/haptic/adapters/__init__.py` — added
  `set_balance` to `HapticBackend` protocol.
- `py_modules/deckysense/haptic/adapters/inputplumber_adapter.py` —
  added `set_balance()` as no-op.
- `py_modules/deckysense/haptic/services/gain_service.py` — default
  backend changed from `InputPlumberAdapter` to `UinputProxy` (with
  fallback); `set_balance` now propagates to backend.
- `py_modules/deckysense/haptic/domain.py` — added `balance` field to
  `HapticParams` (v0.0.37).
- `main.py` — RPC methods `set_haptic_gain`, `set_haptic_balance`,
  `preview_rumble`, `stop_rumble`.
- `src/haptic/GainPanel.tsx` — UI for gain + balance sliders with live
  preview (v0.0.37).

**What's still missing.**

- If `EVIOCGRAB` breaks Steam Input (e.g. Steam loses track of the
  original device), we may need a mode that *forwards* the hidraw
  instead of grabbing.
- `set_kernel_gain` is kept for backward compat but is a no-op on the
  proxy backend (gain is applied per-effect now).

---

## 2026-07-17 — v0.0.3: shoulder nav, marquee/alert, gain slider with live preview

Closes Phase 4 (auto-update + core UX shell) and lands the first
working Haptic Studio control.

**Plugin rename.** Before any of this, the project was renamed
DeckSense → DeckySense. Convention: `deckysense` (lowercase) for the
npm package name and the Python package directory; `DeckySense`
(PascalCase) for the visible plugin name in `plugin.json`, the docs,
and the GitHub repo (whose REST API does not follow
case-insensitive redirects, so `GITHUB_REPO` in `self_updater.py`
must use the actual name).

**UX shell.**

- `src/components/MarqueeText.tsx` — ping-pong scroll that only
  animates when text overflows its container by more than 2px. Uses
  the Web Animations API on a single transform property so all the
  work stays on the compositor thread. Adapted from Panel de
  Control's pattern.
- `src/components/AlertDot.tsx` — small coloured badge for tab
  icons. Wired in `index.tsx` so the Settings tab shows a dot when
  an update is available, regardless of which tab is active.
- `src/sections/nav.ts` — pure `cycleTab(ids, active, direction)`
  with wrap-around, separated from React for unit testing.
- `src/sections/useShoulderNav.ts` — registers
  `SteamClient.Input.RegisterForControllerInputMessages` once on
  mount, filters button ids 30 (L1) and 31 (R1) to cycle tabs via
  `cycleTab`. Refs keep `ids`/`active`/`onSelect` fresh without
  re-registering. Degrades silently when the API is missing.
- `TabBar.tsx` updated to use `MarqueeText` for the active tab label
  and to render `AlertDot` per tab from an `alerts` prop.

**Haptic backend.**

- `py_modules/deckysense/haptic/domain.py` — `HapticParams` dataclass
  with conservative defaults for the Legion Go S (gain 1.0, range
  0.0–2.0).
- `py_modules/deckysense/haptic/adapters/__init__.py` — `HapticBackend`
  Protocol (`rumble(double)`, `stop()`) so services stay
  hardware-agnostic and mockable.
- `py_modules/deckysense/haptic/adapters/inputplumber_adapter.py` —
  shelling out to `gdbus call` against
  `org.shadowblip.Output.ForceFeedback.Rumble(double)` on
  `CompositeDevice0`. Using the CLI instead of pulling in a D-Bus
  Python binding keeps the install surface tiny; if a low-latency
  path is needed later (synthetic patterns, real-time envelope), we
  can migrate to `dbus-python` or `jeepney` without touching the
  service layer.
- `py_modules/deckysense/haptic/services/gain_service.py` — owns the
  current `HapticParams`, persists gain via `decky.set_setting`, and
  exposes `preview(raw_intensity)` which fires
  `min(1.0, raw * gain)` so the user can feel their setting. Module-
  level singleton via `get_gain_service()`.
- `main.py` exposes four async RPCs (`get_haptic_params`,
  `set_haptic_gain`, `preview_rumble`, `stop_rumble`) running the
  sync service in `run_in_executor`. Loads persisted settings in
  `_main`.

**Frontend haptic.**

- `src/haptic/GainPanel.tsx` — `SliderField` 0–2 step 0.05 for gain,
  persisted on change. Preview button fires a rumble at
  `0.5 * gain` and auto-stops after 1.2s so it can't run forever.
  Stop button cancels an ongoing rumble immediately. Error state
  surfaced as small inline text.
- `src/sections/HapticTab.tsx` mounts `GainPanel`.
- `src/api.ts` extended with `HapticParams` / `PreviewResult` types
  and the four callables.

**Deferred to v0.0.4**

- Display Studio MVP: gamescope adapter + Sharp / OLED-like presets
  + confirmation timer.
- Haptic Studio response curve editor (start with simple linear
  remap, no per-game profile yet).

---

## 2026-07-17 — v0.0.2: auto-update + tabbed UI shell

First release that ships the auto-update loop end-to-end. With this
version installed, every future release is offered through the
plugin UI without manual zip transfers.

**Backend**

- `py_modules/deckysense/updater/self_updater.py`:
  - `check(force)` queries GitHub's `releases/latest` endpoint,
    session-cached, slug and current version derived from
    `package.json`. Returns an `UpdateStatus` dataclass; never raises.
  - `install()` downloads the zip, extracts to a temp dir, finds the
    staged plugin folder (the one with `plugin.json`), and uses
    `shutil.copytree(dirs_exist_ok=True)` to overlay it on
    `DECKY_PLUGIN_DIR`. Settings live in `DECKY_PLUGIN_SETTINGS_DIR`
    and are not touched.
  - `restart_loader()` calls `systemctl restart plugin_loader` via
    `subprocess.Popen` with `start_new_session=True` and
    `LD_LIBRARY_PATH` stripped from the environment. The strip is
    non-obvious — without it, Decky's bundled libcrypto leaks into
    the systemctl subprocess and breaks it. Copied from Panel de
    Control.
- `main.py` exposes four async RPCs that wrap the sync functions in
  `run_in_executor` so the asyncio loop never blocks on network I/O.

**Frontend**

- `src/api.ts` centralises the callables and the `UpdateStatus` /
  `UpdateState` types.
- `src/updater/useUpdate.ts` is a hook with module-level session
  guards (`sessionChecked`) so multiple consumers share state. Auto-
  checks on first mount.
- `src/updater/UpdatePanel.tsx` renders the inline "Check for updates"
  button whose label reflects the current state; opens `UpdateModal`
  when an update is available.
- `src/updater/UpdateModal.tsx` shows the release notes (rendered as
  `<pre>` for now; markdown rendering is a later polish) and the
  install → restart flow.
- `src/sections/registry.tsx` is the single source of truth for tabs;
  `TabBar.tsx` uses `Focusable` so the gamepad can navigate between
  tabs. The active tab grows and shows its label; inactive tabs are
  icon-only to stay compact in the narrow QAM width.
- Four placeholder tabs (Display, Haptic, Profiles, Settings). Settings
  hosts the UpdatePanel.

**Deferred to v0.0.3**

- L1/R1 shoulder navigation (`SteamClient.Input.RegisterForControllerInputMessages`).
- `MarqueeText` and `AlertDot` utilities.
- First lab control (haptic gain slider with live preview is the
  candidate).

**Pipeline validation**

- CI: passed on push (build + python smoke + artifact upload).
- Release workflow: triggered by the `v0.0.2` tag, ran for ~24s,
  published `deckysense-v0.0.2.zip` (28 KB) to the GitHub release with
  auto-generated release notes. The whole "commit → tag → release"
  loop is now hands-off.

**One manual hop remaining**

The Go S currently runs v0.0.1, which predates the auto-updater. The
first update to v0.0.2 must be done manually (Decky Loader → Install
from ZIP URL). From v0.0.2 onward, every future release is reachable
from inside the plugin.

---

## 2026-07-17 — Roadmap reshuffle: Phase 4 first, lab second

**Decision:** reorder the execution sequence after Phase 0 close.
Phase 4 (auto-update) is pulled forward ahead of Phase 1/2, and
Phase 1 (Display) + Phase 2 (Haptic) become a **parallel incremental
lab** instead of two sequential slogs.

**Why:**

- Auto-update unblocks the only workflow that matters at this stage:
  commit → push → "check for updates" on the device → feel the change.
  Until that's in place, every deploy is a manual zip transfer.
- Doing Display and Haptic as one big module each is slower to
  validate than shipping small visible increments (two display
  presets + a gain slider in v0.0.3 is more useful than nothing
  for three months).
- UX/UI is treated as a cross-cutting concern from day one, not a
  polish phase at the end. Tab navigation with L1/R1, marquee text,
  live-preview sliders, status indicators — all land alongside the
  features they belong to.

**Reference pattern:** `Hooandee/panel-de-control` (cloned and read).
Key takeaways filed for the auto-update implementation:

- Backend `self_updater.py` shape: `check(force)`, `install()`,
  `restart_loader()`. Never raises; returns status dicts.
  `LD_LIBRARY_PATH` is stripped before `systemctl restart
  plugin_loader` so Decky's bundled libcrypto does not leak into the
  systemctl call. Non-obvious; would have bitten us.
- Frontend: module-level session guards (`sessionChecked`,
  `sessionToasted`) so multiple `useUpdate` consumers share state
  without re-fetching. Coarse progress states
  (`idle|checking|installing|done|error`), no progress bar.
- Tab navigation: `SteamClient.Input.RegisterForControllerInputMessages`
  filtering button ids **30/31** (LSHOULDER/RSHOULDER). Note: in
  SteamOS the "shoulders" are the bumpers (L1/R1), not the triggers.
  Pure `cycleTab()` function with wrap-around; listener registered
  once with refs; degrades silently if the API is missing.
- UX detail to copy: `MarqueeText` (ping-pong scroll only when
  overflow > 2px, replaces QAM's "Pot…" truncation), and `AlertDot`
  on tab icons so update state is visible from any tab.

**Done in this commit**

- Reorganized `ROADMAP.md` to reflect the new order.
- Added `.github/workflows/ci.yml` — install + build + Python smoke
  check on every push and PR, plus dist artifact upload.
- Added `.github/workflows/release.yml` — on `v*` tag, build + package
  via `scripts/package.sh` + upload the zip to the GitHub release
  with auto-generated release notes.
- Added `.github/dependabot.yml` — npm and github-actions ecosystems,
  weekly, limit 5 open PRs, conservative commit prefix `chore(deps)`.
- Pinned `packageManager: pnpm@11.13.1` in `package.json` so CI and
  local dev use the same pnpm.
- Removed the obsolete `pnpm.peerDependencyRules` field — pnpm 11
  ignores it and the install builds clean without it.

**Next**

Implement Phase 4 (auto-update + tab shell + shoulder navigation),
then deploy as `v0.0.2` to validate the whole pipeline on the device.

---

## 2026-07-17 — Phase 0 close: rumble sweep results

A rumble sweep was driven through D-Bus at intensities
`0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 1.0` (1s each, 0.5s gap), then
stopped. Outcome:

- All values produced a perceptible, **gradual** response. No abrupt
  on/off threshold was reported at the low end, and no obvious
  saturation knee at the high end.
- This contradicts the SDD's working assumption that handheld rumble
  motors typically show a hard dead-zone at the bottom and early
  saturation at the top. On the Legion Go S the motor is more
  obedient than the SDD assumed.

**Implications for Haptic Studio**

- The default response curve can start **linear** — no aggressive
  dead-zone compensation is required.
- The ceiling for what Haptic Studio can do on this device is higher
  than the SDD expected. Fine intensity adjustments will translate to
  a real perceptual difference; we are not limited to gain +
  envelope shaping alone.
- The remaining calibration (subjective "punch" shaping, exact curve
  preference) is **deferred into Haptic Studio itself**, where the
  user will have a live intensity slider and curve editor. The
  initial `DeviceProfile` for the Legion Go S will ship conservative
  defaults: `gain = 1.0`, linear curve, no dead-zone, no saturation
  cap.

**Phase 0 status**

| Phase 0 item | Result |
| --- | --- |
| Kernel + driver (`hid_lenovo_go_s`) | Confirmed — ships with SteamOS 3.8.23 |
| Gamepad topology (hidraw/event nodes) | Confirmed — gamepad is `hidraw5` / `event2`, owned by InputPlumber |
| Steam Input mediation | Partially answered — Steam only sees the virtual `deck-uhid` gamepad; out of scope for MVP |
| Motor profiling | Confirmed gradual response; fine calibration deferred into Haptic Studio |

Phase 0 is **closed**. Haptic backend path is locked to InputPlumber
D-Bus `org.shadowblip.Output.ForceFeedback.Rumble(double)` on
`CompositeDevice0`.

---

## 2026-07-17 — Phase 0 hardware validation: findings

Validation ran on a real Lenovo Legion Go S over SSH. Probe scripts
`scripts/probe{,2,3}.sh` capture the raw evidence; archived under
`docs/phase0/`.

**Setup**

- SteamOS 3.8.23 (BUILD 20260715.2), kernel
  `6.16.12-drmexec7-valve24.5-1-neptune-616-drm-exec-gf253f5da553e`
  (Valve neptune base — same codebase as the Steam Deck).
- `VARIANT_ID=steamdeck` in `/etc/os-release`: Valve ships the Go S
  SteamOS as a `steamdeck` variant overlay, not a separate codename.

**Items confirmed**

1. **Kernel + driver.** `hid_lenovo_go_s` ships with this SteamOS
   kernel — already loaded at boot, no need for a 7.x kernel. Two
   modules present on disk: `hid-lenovo-go.ko` (original Legion Go)
   and `hid-lenovo-go-s.ko` (Go S). Author: Derek J. Clark, GPL.
   The SDD assumption that this driver was pending mainline in
   Linux 7.1+ is outdated: it is already backported here.
2. **Gamepad topology.** The internal MCU presents as a compound USB
   device `1a86:e310` (QinHeng bridge) with **6 HID interfaces**,
   each backed by one hidraw device. InputPlumber maps them by
   `interface_num` (see `/usr/share/inputplumber/devices/50-legion_go_s.yaml`):
   - iface 2 → `/dev/hidraw1` (mouse + touchpad, blocked)
   - iface 5 → `/dev/hidraw4` (IMU)
   - iface 6 → `/dev/hidraw5` (**gamepad** — buttons, sticks, triggers)
   - iface 0/3/4 → also bound by `hid-lenovo-go-s` (auxiliary)
   The gamepad is also exposed as `/dev/input/event2` (joystick
   `js0`, name `"Legion Go S"`) with FF capabilities
   (`B: FF=107030000`).
3. **InputPlumber composite device.** InputPlumber is the input
   manager on this SteamOS build. It captures the native gamepad and
   re-emits a **virtual Steam Deck gamepad** ("Valve Steam Deck
   Controller") via `deck-uhid`, surfaced as `/dev/input/event18`
   (`"Microsoft X-Box 360 pad 0"`, vendor `28de`). Steam and games
   see only the virtual device.
4. **D-Bus rumble API.** The composite device at
   `/org/shadowblip/InputPlumber/CompositeDevice0` exposes the
   `org.shadowblip.Output.ForceFeedback` interface:
   - `Rumble(double value)` — set rumble intensity, 0.0–1.0.
   - `Stop()` — stop rumble.
   - `Enabled` (readwrite bool, default true).
   `OutputCapabilities` confirms `ForceFeedback`,
   `ForceFeedbackUpload`, `ForceFeedbackErase` are supported. This
   is the clean integration point for Haptic Studio.

**Items partially confirmed**

5. **Steam Input mediation.** Not directly tested. The gamepad the
   games see is the virtual `deck-uhid` device, so Steam Input
   applies its own processing on top of that. Intercepting rumble
   between Steam and the kernel would require going below
   InputPlumber — out of scope for the MVP.

**Items still open**

6. **Motor profiling.** Dead-zone, saturation point and latency still
   need to be measured by driving `Rumble(d)` with a sweep of values
   and observing the physical response. This requires a write test,
   pending explicit user confirmation (the only Phase 0 step that is
   not read-only).

**Architectural decision**

For Haptic Studio on the Legion Go S, the **primary rumble path is
the InputPlumber D-Bus `ForceFeedback.Rumble(double)` method on
`CompositeDevice0`**.

- It is the officially supported integration surface.
- It avoids conflicts with InputPlumber's exclusive ownership of
  `/dev/hidraw5` and `/dev/input/event2`.
- The `d` argument is already a 0.0–1.0 float — gain is essentially
  free.
- It supports per-effect upload/erase for advanced patterns later.

Going below InputPlumber (writing to `hidraw5` directly) would break
its input translation. Going above InputPlumber (intercepting Steam
Input output) is not feasible from a Decky plugin. D-Bus is the
sweet spot.

What D-Bus does **not** give us directly is per-event gain on rumble
coming from games — `Rumble()` is fire-and-feel, not a transform on
the FF stream. Global gain as "set baseline intensity" works;
"amplify whatever the game sends" is not exposed and would need
either the CompositeDevice's `InterceptMode` /
`SetInterceptActivation` methods (worth investigating in Phase 2)
or a path below the kernel. Filed as Phase 2 stretch.

---

## 2026-07-17 — Repository, build pipeline, first release

**Done**

- Created `scripts/package.sh` — a small bash script that bundles the
  plugin into the zip layout Decky Loader expects (top-level directory
  named after the plugin, with `dist/`, `package.json`, `plugin.json`,
  `main.py`, `defaults/`, `py_modules/`, `LICENSE`, `README`). Source
  maps are excluded to keep the artifact small. The script reads name
  and version from `package.json` so it stays correct as we tag
  releases. It will be reused by the release GitHub Action later.
- Bootstrapped the toolchain on the dev machine:
  - `pnpm 11.13.1` installed via `npm i -g pnpm` (corepack not
    available on this image).
  - `pnpm install` brings in `@decky/ui 4.12.0`, `@decky/api 1.1.3`,
    `@decky/rollup 1.0.2`, `react-icons`, `rollup`, `typescript`.
    No `docker` (no decky CLI) — handled by the manual packaging
    script instead.
- `pnpm run build` produces `dist/index.js` (~7 KB) plus a sourcemap.
- Packaged `out/deckysense-v0.0.1.zip` (21 entries, ~25 KB).
- Created the GitHub repository at `Heric-Olier/deckysense` as
  **private** until the MVP is ready, and pushed `main`.
- Tagged `v0.0.1` and published the first GitHub Release with the zip
  as a release asset.

**Notes**

- pnpm 11 warns that the `pnpm.peerDependencyRules` field in
  `package.json` is no longer read. The install and build still work,
  so the field can be removed (or migrated to `.npmrc`) in a follow-up
  cleanup commit.
- The release is only reachable from a GitHub account that has access
  to the private repo. Installing from the device needs either a
  public repo or a GitHub token configured in Decky Loader. This is
  expected for the "private until MVP" decision and will revisit when
  Display Studio lands.

**Next**

- Decide install path on the Lenovo Legion Go S (make the repo public
  for this skeleton, or pass the zip manually).
- Phase 0 — hardware validation. First task: confirm the SteamOS
  kernel version on the device and whether the rumble path goes
  through the mainline `hid-lenovo-go-s` driver or through
  InputPlumber.

---

## 2026-07-17 — Bootstrap

**Decisions**

- **License: GPL-3.0.** Coherent with the Decky Loader ecosystem
  (GPL-2.0) and protects downstream contributions.
- **No native daemon at launch.** Backend access to hardware lives
  entirely in the Python backend, talking to sysfs / hidraw /
  InputPlumber. A native daemon is deferred to Phase 5 and only if
  latency / resolution requirements demand it. This matches the
  architecture used by other ecosystem plugins and keeps the build
  surface small.
- **Plugin runs with the `_root` flag.** Hardware access (sysfs,
  hidraw) requires elevated privileges. The flag is declared in
  `plugin.json` so the user knows up front what the plugin needs.
- **Module layout under `py_modules/deckysense/`** with one subpackage
  per module (`display`, `haptic`, `profiles`, `updater`). Each
  subpackage will own its own `adapters`, `services` and `domain`
  types. This keeps module boundaries explicit so each module can grow
  independently and so tests can mock at the adapter boundary.
- **Layered backend.** Conventions within each module:
  - `adapters/` — hardware I/O (the only place that touches sysfs /
    hidraw / subprocesses).
  - `services/` — business logic, agnostic of the hardware path.
  - `domain.py` — pure data models (Pydantic once dependencies land).
  The `main.py` entrypoint exposes thin RPC methods that delegate to
  services. This lets us swap the kernel-sysfs path for InputPlumber
  without touching business logic, and mock hardware in tests.
- **Conventional Commits** as the commit message convention
  (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`).
- **Repository language: English** for code, docs and commits, so the
  plugin is approachable for the wider Decky community.

**Done**

- Initialized the repository with the structure of the official
  `decky-plugin-template` as a base.
- Skeleton `plugin.json`, `package.json`, `rollup.config.js`,
  `tsconfig.json`, `main.py`, plus empty module subpackages.
- Frontend skeleton (`src/index.tsx`) with three empty panel sections
  for Display Studio, Haptic Studio and Game Profiles.
- Initial settings schema in `defaults/settings.json`.
- `README.md`, `ROADMAP.md` and this file as the public tracking
  surface.

**Next**

- Phase 0 — hardware validation on the Lenovo Legion Go S. First task:
  confirm the SteamOS kernel version and whether the Legion Go S
  rumble path goes through the mainline `hid-lenovo-go-s` driver or
  through InputPlumber.
