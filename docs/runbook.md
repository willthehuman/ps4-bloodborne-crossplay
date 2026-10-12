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

## Task 4 — isolated test instance (shadNet)

A second, fully isolated shadnet server for development: own container, own IP, own DB/config. Production (`/home/crow/shadnet`, ports 31313-31315 on the host) is never touched.

**Addresses**
- `192.168.50.233:31313` TCP / `:31314` STUN UDP / `:31315` WebAPI — from the seats (verified) and (expected) the console.
- `172.31.13.23:31313` / `:31315` — from BIG-PC (host); this is the test suite default.

**Control**
- `scripts/run-test-server.sh {start|stop|restart|status|logs}`
- DB lives at `private/test-server/db/` (reset: stop, `rm -rf private/test-server/db`, start — schema self-creates; re-register accounts).
- Accounts (test DB only; passwords in `private/test-server/accounts.env`, mode 600): `crowps4` (console), `crowseat` (test seat). Add more: `scripts/register-test-account.py <npid>`.
- Tests: `python3 -m unittest discover -s tests -p 'test_protocol.py' -v` (11 checks: handshake, create/login/delete, session conflict, framing, STUN ping).

**Why a container on macvlan** — measured, not guessed: the host-shim (`sh-macvlan-shim` / 192.168.50.239) only carries the production ports for macvlan containers (31313/31315/20443 pass; arbitrary new host ports on 239 fail). A container with its own macvlan IP gets an unrestricted path while keeping familiar ports.

**Container gotchas (already encoded in the script)**
- Base `josh5/steam-headless:2` (glibc 2.43 >= binary's GLIBC_2.38 requirement; local).
- `libs-full/` = full ldd closure of `shadnet` + bundle libs, minus glibc core (image provides newer) — otherwise the image's own Qt mixes in and the app dies with `Qt_6_PRIVATE_API not found`.
- Qt SQL plugin: `qtplugins/sqldrivers` (from the host Qt) + `QT_PLUGIN_PATH=/srv/qtplugins`. Missing it = silent exit 1 (`QSQLITE driver` load failure).
- `QT_FORCE_STDERR_LOGGING=1 QT_ASSUME_STDERR_HAS_CONSOLE=1` so `docker logs` shows Qt output.

**Protocol quirks (verified against 0.0.13, encoded in tests)**
- STUN datagrams carry a 4-byte signaling vport header `FF FF FF FF` on BOTH request and reply.
- Client convention: STUN UDP port = server TCP port + 1 (nothing advertises it).
- Terminate replies `NoError` but the server does not close the socket (its queued disconnect errors: "No such method QTcpSocket::disconnectFromHost()"); the client closes; the server releases the session on disconnect.
- Pre-auth only Login/Create are allowed; anything else answers `Unauthorized (23)`. NPID format `[A-Za-z0-9_-]{3,16}`.
