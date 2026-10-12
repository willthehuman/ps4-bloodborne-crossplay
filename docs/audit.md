# Task 1 — Identity freeze & environment audit

> Plan: `/home/crow/.hermes/plans/2026-10-12_074625-bloodborne-ps4-shadnet-crossplay.md` (Task 1)
> Date: 2026-10-12 · Executor: Hermes · Scope: read-only checks + workspace scaffolding.
> No console operations, no builds, no service changes, no public posts.

## 1. Purpose

Freeze the exact artifacts and interfaces that must interoperate so every later task is
validated against a fixed baseline instead of moving upstream heads.

## 2. Pinned identities

Machine-readable copy: `docs/build-manifest.json`.

- **Plugin:** `StevenMiller123/shadNet-PS4` @ `9f33b1e86f655cc73cf93f017272ff03f966559c` (main, read 2026-10-12).
  Branch `failed-attempt-at-fixing-some-issues` @ `fff22b9085c6f099f0f9bfdc791fa7698be65484` also inspected.
- **Plugin SDK:** `StevenMiller123/GoldHEN_Plugins_SDK` @ `3cf7d13f5441c13939a15e7308bb191f15cc5b0f` (HEAD at freeze; committed 2026-09-15).
- **Toolchain:** `OpenOrbis-PS4-Toolchain` release `release-46e63322a7c9101c9e0c95bff8723a59e2cd7718`;
  asset `openorbis_toolchain.tar.gz`, 159,022,440 bytes, sha256 `40bd99bf990f73fbaa494ac84c8354a2dda50fdfdecd0250d99d4a0cb98a3fbb` (digest from GitHub API).
- **PC network source (porting reference):** `ayozetr/bloodborne_linux` tag `test-issue1-1` @
  `04fc67d8dc789848aa92baac64a299cac6e30855` — matches the tree deployed to seat A for the issue-#1 test.
- **Server source (reference):** `Wozzardman/shadnet-p2p` @ `5a849a192fd4450593c57b10697316ac324c856e`.
- **Server binary (local):** `/home/crow/shadnet/shadnet`, 2,117,888 bytes,
  sha256 `8cc32eb2b115e16a967edc02d12463b2183f8c6728b885cb934706b1ba26e5fa`.
  Built by CI (path strings reference `/home/runner/work/shadnet-p2p`); exact workflow run not yet matched (follow-up §8).
- **Game dump (PC-side, reference):** `EP9000-CUSA03173_00-BLOODBORNE0000EU`, APP_VER **01.09**;
  `eboot.bin` 93,825,704 bytes, sha256 `d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9`.
  This is the PC port's game copy — it is **not** automatically the console's edition (do not assume title ID).

## 3. Environment observations (verified today, read-only)

- Host: Omarchy/Linux, user `crow`, LAN IP `192.168.50.198`; 23 GB free on `/home`.
- `shadnet.service` and `shadnet-ndfh.service`: active user units; server root `/home/crow/shadnet`.
- Listeners: TCP 31313 (control) / 31315 (WebAPI), UDP 31314 (matching/STUN), backend TCP 20443 — wildcard binds.
- Non-secret server config: `Matching2Enabled=true`, `BloodborneSeamlessCoop=false`,
  `MatchingUdpPort=31314`, `UnsecuredPort=31313`, `WebApiPort=31315`, `Host=0.0.0.0`.
- Seat A bbport settings point at `192.168.50.239:31313` and `http://192.168.50.239:31315`.
  Its "community" setting is currently an external endpoint (`thehuntersdream.com`) — do **not** assume every
  HTTP path is local until per-endpoint verification in Task 6.
- Seat A runs the `test-issue1-1` tree with `BB_TC_LEGACY_HASH=1` (issue-#1 test). Unrelated to this
  project; preserve untouched.
- Host tooling available: `readelf`, `llvm-readelf`, `objdump`, `file`, `bsdtar`, `cmake`, `ninja`, `clang`, `clang++`.
- Workspace created: `/home/crow/Projects/ps4-bloodborne-crossplay` (`docs/ scripts/ tests/fixtures/ private/ vendor/ toolchains/`).
  `vendor/` and `toolchains/` are git-ignored; identities live in the manifest.

## 4. Console state to (re)establish — input for Task 2

Prior notes (firmware 9.03, GoldHEN, FTP :2121) were **not** re-verified today. Task 2 must capture:

1. Firmware + GoldHEN version + plugin-loader mode.
2. Exact installed Bloodborne title/version (never inferred from the PC dump).
3. Local Orbis user ID (the decimal key used in `/data/shadnet/config.json` — **not** user `1`).
4. Save export + a restore rehearsal (the rollback baseline).
5. `plugins.ini` backup + any existing plugin with the same filename.
6. Egress policy: router/firewall allowlist for the console's own traffic, including IPv6;
   keep PSN + update blocks; verify with captures before trying online mode.

## 5. Game import surface (module level)

From `strings` on the decrypted `eboot.bin` — 40 `libSce` modules. Networking/NP-relevant subset:

- `libSceNet`, `libSceNetCtl`, `libSceHttp`, `libSceSsl`
- `libSceNpAuth`, `libSceNpCommon`, `libSceNpManager`, `libSceNpMatching2`, `libSceNpSignaling`,
  `libSceNpUtility`, `libSceNpWebApi`, `libSceNpScore`, `libSceNpScoreRanking`, `libSceNpCommerce`,
  `libSceNpProfileDialog`, `libSceNpTrophy`
- (also: video/audio/input/system modules — irrelevant to this project)

**Caveat:** module-level only. Function-level import-table extraction from the SELF is a follow-up (§8 #1).

## 6. Source capability inventory — plugin @ pin

- **Hooks present (verified by source scan, 70 declarations + macro hooks):**
  - Kernel: 2 pass-through hooks (`socket`, `__sys_socketex`) — export/later-interception groundwork only.
  - Net: 2 pass-through hooks (`sceNetSocket`, `sceNetResolverStartNtoa`) — log + continue.
  - UserService: 4 hooks (init ×2, `GetUserName`, `GetEvent`).
  - NpManager: 11 hooks (state, NP ID, online ID, callback register/unregister variants).
  - NpScore: hook surface exists, forwarding into a local shim — behavior unverified (likely placeholder).
  - NpWebApi: **54 hooks** + a sizeable internal implementation (`np_web_api_internal.cpp`, 79,614 B).
- **Notable components:** `client.cpp/.h` (34.4 KB — shadNet session: login, token, server features,
  notifications, invitations, appear-offline), `server_probe.cpp` (server feature probing),
  `np_callbacks.cpp`, `np_handler.cpp` (connect/auth orchestration).
- **Verified absences (critical):**
  - `np_handler.cpp` lines 178–183: UPnP + **`NpMatching2::SetMmShadNetClient(...)` handoff commented out**.
  - `np_handler.cpp` lines 468–484: async reply dispatcher (incl. `NpMatching2::OnMatchingReply`) **fully commented out**.
  - No source modules or hooks for: **NpAuth, NpMatching2, NpSignaling, NpCommon, NpUtility, NpTrophy,
    NpCommerce, NpProfileDialog, NpWebApi2**.
- Net effect: the plugin can (in principle) log into shadNet and fake identity/WebAPI, but has **no
  matchmaking, no signaling/peer transport, no auth surface** — exactly the modules co-op needs.

## 7. PC reference inventory (what a port must reproduce)

From the deployed `test-issue1-1` tree (`gpu/bbnet/shadps4/core/libraries/…`), measured

- `np_matching2`: 58 exports / 8 files / 5,116 lines
- `np_signaling`: 24 exports / 8 files / 3,423 lines — custom `SHAD` handshake/control packets
- `np_auth`: 15 · `np_common`: 55 · `np_manager`: 58 · `np_score`: 62 · `np_web_api`: 112
- `np_web_api2`: 42 (game does not import) · `np_trophy`: 87 · `np_commerce`: 11 · `np_profile_dialog`: 9
- `np_partner`: 4 · `np_party`: 32 · `np_tus`: 186 (not found in game imports — verify)
- network: `net` 219 · `netctl` 98 · `http` 115 · `http2` 55 · `ssl` 208 · `ssl2` 56
- **Total exports measured across np + network modules: 1,507.**

Note: on console most native system libs actually work; the requirement is to intercept/redirect only
what must change (Sony-bound identity/matching/signaling + specific HTTP endpoints), not to port everything.

## 8. Follow-ups / open questions

1. Function-level import extraction from the SELF (`eboot.bin` is a SELF — magic `4f 15 3d 1d`; needs a
   segment-table parse or PS4 tooling) to confirm which NP functions the game actually binds.
2. `libSceNpUtility`: imported (3× strings), no PC module, no plugin module — check whether any of its
   functions matter in login/co-op flows.
3. NpScore naming: eboot references both `libSceNpScore` and `libSceNpScoreRanking`; PC registers
   `libSceNpScore`. Confirm which module name the game's imports target.
4. Server binary exact CI provenance (optional; run matching).
5. Whether commerce/profile/trophy calls occur mid-session or only in menus (runtime tracing, later task).
6. Reuse-first: sweep the scene for other GoldHEN NP-hook plugins before writing porting code from scratch.

## 9. Gate A status

Gate A asks for a concrete implementation candidate for every indispensable dependency. Current candidate set:

| Need | Candidate | Task |
|---|---|---|
| Online entry / identity | port `np_auth` (15 exports) + needed `np_common` subset; extend NpManager hooks | 6 |
| Game HTTP routing (ss.info, broker, directory) | new game-scoped URL hook layer (design) | 6 |
| Matchmaking rooms/callbacks | port `np_matching2` (58 exports) | 7 |
| Peer transport | port `np_signaling` (24 exports; `SHAD` protocol) | 8 |
| Non-blocking stubs (score/trophy/commerce/profile) | one-way stubs to avoid hangs | 5–6 |

**Gate A: candidate path identified for all indispensable dependencies; pending Will's review and
follow-ups #2/#3.** Negative finding recorded honestly: none of this exists yet in the plugin.
