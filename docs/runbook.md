# Runbook — Task 2: console safety gate & recovery

> **Status: IN PROGRESS** — partial execution 2026-10-12 (read-only captures + backups done; see
> `docs/status.md`). Remaining steps need Will at the console / a router session.
> Plan reference: Task 2 + Gate B.
> Evidence for each step goes to `private/backups/<timestamp>/` and `private/logs/`.
> No secrets in any tracked file — credentials stay out of this repo entirely.

## 0. Preconditions (Will)

- PS4 powered on, GoldHEN active, FTP reachable from this host (port 2121 normally).
- Console on the LAN; a 30–60 min quiet window; not mid-session.
- Copy tooling pattern available from the Moonlight work (`~/ps4-moonlight/push-to-ps4.sh`).

## 1. Capture console identity (read-only)

- [ ] Console IP address (from router or GoldHEN menu) → record here: `______`
- [ ] Firmware version (Settings → System Information) → `______`
- [ ] GoldHEN version + plugin loader state → `______`
- [ ] Installed Bloodborne: title ID + app version + region (read `/mnt/sandbox/...`/`param.sfo` over FTP).
      **Do not assume CUSA03173 from the PC dump.**
- [ ] Local Orbis user ID (the numeric one under Users) → `______`
- [ ] Directory listing of `/data/GoldHEN/` + whether `plugins.ini` exists.

## 2. Backups (rollback baseline)

- [ ] Bloodborne saves exported via console UI (Settings → Application Saved Data → export), verified
      readable, stored under `private/backups/<ts>/ps4-saves/`.
- [ ] `/data/GoldHEN/plugins.ini` copied + sha256 recorded.
- [ ] `/data/shadnet/config.json` copied if it exists (expected: not yet).
- [ ] Any existing plugin file with our future name (`shadNet-PS4.prx`) backed up.
- [ ] PC side, same timestamp: seat A `settings.json`, `bbport.ini`, save dir — snapshot copies.

## 3. Offline baseline drill

- [ ] Launch Bloodborne with NO new plugin — confirm saves load and the game version in its menu
      matches the param.sfo read. Screenshot as evidence.
- [ ] Confirm the restart/recovery path works with the game stopped.

## 4. Egress policy (scoped isolation)

- [ ] Confirm existing PSN/update blocks still in place.
- [ ] Add explicit allowlist: console ↔ `192.168.50.239` TCP 31313 / UDP 31314 / TCP 31315.
- [ ] Deny the rest (including IPv6 paths). Router changes need Will's separate OK and must not affect
      other devices.
- [ ] Evidence: rule screenshots; a scoped capture during a later connectivity test.
- [ ] Document the exact revert procedure (single switch) and test it once.

## 5. Recovery rehearsal (Gate B evidence)

- [ ] With the game stopped, disable the plugin (remove only our game stanza / move the `.prx`).
- [ ] Relaunch offline → saves load → normal play. Record exact steps as the stop-button procedure.
- [ ] Re-enable nothing until Task 5's staged trial.

## 6. Gate B checklist

- [ ] Restorable save backup demonstrated (not just a copied folder).
- [ ] Config/plugin backups with hashes, restore steps written and tried.
- [ ] Offline baseline confirmed.
- [ ] Egress isolation verified (allowlist + deny-all remainder), revert tested.
- [ ] Log retrieval method for the console works (GoldHEN log transport — discover here).

## Result log

- Date executed: `______` · Operator: Will + Hermes · Outcome: `______`
- Blockers found: `______`
