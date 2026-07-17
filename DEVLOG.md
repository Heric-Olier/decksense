# Dev Log

A chronological log of technical decisions and progress. Newest entries
appear at the top.

The intent of this file is to be the source of truth for "why is the
code like this" — every non-trivial decision should be findable here.

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
- Packaged `out/decksense-v0.0.1.zip` (21 entries, ~25 KB).
- Created the GitHub repository at `Heric-Olier/decksense` as
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
- **Module layout under `py_modules/decksense/`** with one subpackage
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
