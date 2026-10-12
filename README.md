# ps4-bloodborne-crossplay

Making a jailbroken PS4 run **Bloodborne** natively and bell-co-op against a
[bbport](https://github.com/ayozetr/bloodborne_linux) seat through a private
[shadNet](https://github.com/Wozzardman/shadnet-p2p) server — no PSN, and without touching the
working PC co-op stack.

Built around the experimental [StevenMiller123/shadNet-PS4](https://github.com/StevenMiller123/shadNet-PS4)
GoldHEN plugin. This repo is the verification/workspace side: console audits, save-transfer
tooling, build/deploy/rollback scripts, protocol tests, and the recorded evidence trail.

## Status (2026-10-12)

- ✅ **Save transfer**: a PC bbport character ("crow") was transferred to the console (recipe in `docs/save-transfer.md`).
- ✅ **Plugin stability**: builds, loads, and runs on the console; two game-killing crashes
  (CE-34878-0) were diagnosed from kernel-log crash dumps and fixed — see `docs/status.md`.
- ✅ **Private login**: the console signs into the private shadNet server (`crowps4`).
- ✅ **Online/offline menu reached**: the game boots fine with the plugin active.
- ⏳ **Online entry**: currently falls back to offline — the NpMatching2 / signaling / auth
  bridge is the next implementation chunk (Tasks 6–8 of the plan).

Plugin-side work (crash fixes + hardening) lives in the fork:
[willthehuman/shadNet-PS4 @ `hardening`](https://github.com/willthehuman/shadNet-PS4/tree/hardening).

## Layout

- `docs/` — audit, compatibility matrix, status, runbook, save-transfer notes.
- `scripts/` — build / deploy / rollback / log-capture tooling.
- `tests/` — host-side protocol, config and endpoint tests.
- `private/` — local-only material (backups, raw captures, credentials): **git-ignored, never committed.**
- `vendor/`, `toolchains/` — pinned external checkouts (git-ignored; identities in `docs/build-manifest.json`).

## Rules

- No console operations before the safety gate (backups + isolated egress + rollback drill).
- No credentials in any tracked file, log, capture, or command transcript.
- The production server config/DB stays untouched during development (isolated test instance).
- Public communication on upstream repos happens via reviewed drafts.
