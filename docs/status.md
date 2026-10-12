# Implementation status

Updated: 2026-10-12 · Plan: `/home/crow/.hermes/plans/2026-10-12_074625-bloodborne-ps4-shadnet-crossplay.md`

| # | Task | State | Notes |
|---|---|---|---|
| 1 | Identity freeze / audit | **DONE** | `docs/audit.md`, `docs/compatibility.md`, `docs/build-manifest.json`. Gate A candidate path identified; awaits Will review + 2 open follow-ups. |
| 2 | Console safety & recovery | **BLOCKED — needs Will + console** | Checklist in `audit.md` §4. |
| 3 | Reproduce & fix cross-build | **IN PROGRESS** | Toolchain verified (sha256 match) + extracted; Orbis headers smoke test PASS; GoldHEN SDK built; CMake configure OK; full plugin build running (`private/logs/build-1.log`). `ld.lld` absent on host → user-local lld package + wrapper in `toolchains/bin` (no system change). |
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
