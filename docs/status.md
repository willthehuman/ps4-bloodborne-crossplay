# Implementation status

Updated: 2026-10-12 · Plan: `/home/crow/.hermes/plans/2026-10-12_074625-bloodborne-ps4-shadnet-crossplay.md`

| # | Task | State | Notes |
|---|---|---|---|
| 1 | Identity freeze / audit | **DONE** | `docs/audit.md`, `docs/compatibility.md`, `docs/build-manifest.json`. Gate A candidate path identified; awaits Will review + 2 open follow-ups. |
| 2 | Console safety & recovery | **IN PROGRESS** | Console `192.168.50.90` reachable; identity captured (CUSA03173 v1.09 ✓; Will's profile = `114633a1`); backups taken. Apollo v2.3.2 installed. Save transfer (PC→PS4) researched + payload staged (`docs/save-transfer.md`). Remaining: game-launch baseline + Apollo import (with Will), egress session. |
| 3 | Reproduce & fix cross-build | **DONE (local build)** | PRX built clean; import audit: 368 undefined → 139 `sce*` + 191 libc/cxx-rt + 38 C++ mangled, all from the 11 expected PS4 system libs; script validated; CI path bug fixed locally (not pushed). Console load test belongs to Task 5. Artifacts: `private/artifacts/`. |
| 4 | Isolated backend & identities | pending | after Task 3 basics |
| 5 | Plugin-load + private login milestone | pending | |
| 6 | Online entry, auth, HTTP routing | pending | |
| 7 | Matching2 bridge | pending | |
| 8 | SHAD signaling / peer transport | pending | |
| 9 | Two-way summon trial | pending | |
| 10 | Promotion, rollback drill, handoff | pending | |

## Log

- 2026-10-12 — Task 1 executed. Verified: game imports (40 modules incl. NpAuth/NpMatching2/NpSignaling);
  plugin gaps (matching handoff + dispatcher commented out; no auth/matching/signaling modules);
  build paths; toolchain digest; server binary hash; seat/dump identities. Workspace created,
  vendor repos cloned at pinned SHAs. Toolchain download initiated (background, verified on completion).
- 2026-10-12 — Task 3 progress: toolchain archive fetched from pinned release and sha256-verified;
  extracted to `toolchains/extracted/OpenOrbis/PS4Toolchain`. Smoke test
  (`tests/toolchain_smoke/orbis_headers.cpp`) compiles for `x86_64-pc-freebsd12-elf` with clang 22.1.8.
  GoldHEN SDK built (`libGoldHEN_Hook.a`, `crtprx.o`). Plugin CMake configure clean; full build started
  (`scripts/build-plugin.sh`; log `private/logs/build-1.log`).
- 2026-10-12 — Task 3 build complete: full build succeeded (12:17→12:22, `-j8`; clang 22.1.8, LLD 22.1.8,
  cmake 4.4.3). Artifact `bin/plugins/prx_final/shadNet-PS4.prx` (~3.17 MB), audit of 368 undefined
  imports clean (all resolve to the 11 NEEDED PS4 libs; still no matching2/signaling/auth imports).
  Re-validated end-to-end via `scripts/build-plugin.sh`. Builds are not bit-reproducible (embedded
  timestamp) — deployed-file hash recorded at push time (`private/artifacts/PROVENANCE.md`).
  CI failures (missing C++ headers on GitHub runners) did NOT reproduce locally; CI release path fixed
  on local branch `local/ci-artifact-path` (not pushed).
- 2026-10-12 — Task 2 started (console `192.168.50.90` via GoldHEN FTP). Read-only captures: title
  `CUSA03173` Bloodborne GOTY with Patch **v1.09** (patch.json + changeinfo); three user profiles;
  GoldHEN `config.ini` (PluginLoader currently OFF), `plugins/` empty, no `plugins.ini`; no save data
  yet. Backups + hashes in `private/backups/2026-10-12-ps4/`. Nothing written to the console.
- 2026-10-12 — Save transfer prep (Will request): PC live save located (CUSA00207/SPRJ0005, one active
  character); console's older saves identified and left untouched; Apollo v2.3.2 confirmed installed.
  Payload staged (`private/stage/save-transfer/`, patched param.sfo) + method documented in
  `docs/save-transfer.md`. No console writes yet — waiting on the first game launch to create the save.
- 2026-10-12 — Save transfer, my side complete: uploaded staged save (15 files, sha256-verified) to
  the console's fake-USB staging path (`/data/fakeusb/PS4/APOLLO/114633a1_CUSA03173_SPRJ0005/`).
  Blocked on: fresh `CUSA03173` save not yet present (game must reach first autosave + full close).
- 2026-10-12 — Save mystery round: game-side save exists ('Continue' works) but sat in a *pending*
  state invisible to FTP; after Will's Apollo pass the `CUSA03173` save + meta surfaced on disk
  (snapshot sha256 `59f4c3e7…`; written by the copy op perms). Next: decrypted export via Apollo →
  identify contents vs staged payload, then refresh/retry/keystone as needed.
