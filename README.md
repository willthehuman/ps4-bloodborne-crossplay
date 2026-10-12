# ps4-bloodborne-crossplay

Implementation workspace for the plan
`/home/crow/.hermes/plans/2026-10-12_074625-bloodborne-ps4-shadnet-crossplay.md`.

**Goal:** let the jailbroken PS4 run Bloodborne natively and bell-co-op with one bbport
seat through the private shadNet server — via the experimental
`StevenMiller123/shadNet-PS4` GoldHEN plugin — without PSN, and without disturbing the
working PC co-op stack.

## Layout

- `docs/` — audit, compatibility matrix, status; runbook arrives with Task 2.
- `scripts/` — build / deploy / rollback tooling (Tasks 3+).
- `tests/` — host-side protocol, config and endpoint tests (Tasks 4+).
- `private/` — untracked: backups, raw captures, temporary configs. **Never commit secrets.**
- `vendor/` — pinned external source checkouts (git-ignored; identities in `docs/build-manifest.json`).
- `toolchains/` — verified OpenOrbis toolchain (git-ignored; identity in `docs/build-manifest.json`).

## Rules

- No console operations before the Task 2 safety gate (backups + isolated egress + rollback drill).
- Nothing public (issues, PRs, posts) without Will's approval of the draft.
- No credentials in any tracked file, log, capture, or command transcript.
- Production server config/DB stay untouched during development (isolated test instance per Task 4).
