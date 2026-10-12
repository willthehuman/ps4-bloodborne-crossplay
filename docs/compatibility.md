# Compatibility matrix — native PS4 Bloodborne ↔ bbport seat ↔ shadnet-p2p

Sources: plugin @ `9f33b1e8…`, PC reference @ `test-issue1-1` (`04fc67d8…`), game imports from
`eboot.bin` (APP_VER 01.09). All status claims verified by source scan on 2026-10-12.

**Legend:** `ABSENT` = no code · `PASS-THRU` = hook forwards to native · `STUB` = surface only ·
`PARTIAL` = some behavior implemented · `PRESENT` = implemented, unvalidated end-to-end.

## Main matrix

| Module (game import) | PC reference | Plugin status | Gap / next step |
|---|---|---|---|
| `libSceUserService` | (native) | 4 hooks — PARTIAL | verify username/NP-ID flows behave under isolation |
| `libSceNpManager` | 58 exports | 11 hooks (state/NP ID/callbacks) — PARTIAL | extend as needed; state callbacks usable |
| `libSceNpAuth` | 15 exports | **ABSENT** | online-entry gate → port candidate (Task 6) |
| `libSceNpCommon` | 55 exports | **ABSENT** | determine needed subset (Task 6) |
| `libSceNpMatching2` | 58 exports / 5,116 lines | **ABSENT** (handoff + dispatcher commented out — verified) | primary port (Task 7) |
| `libSceNpSignaling` | 24 exports / 3,423 lines; custom `SHAD` handshake | **ABSENT** | peer transport port (Task 8) |
| `libSceNpWebApi` | 112 exports | 54 hooks + internal impl — PARTIAL | configure + validate against server (Tasks 5–6) |
| `libSceNpScore` / `…ScoreRanking` | 62 exports | hook surface → shim — STUB | keep non-blocking; not co-op-critical |
| `libSceNpUtility` | no PC module found | **ABSENT** | investigate actual call usage (follow-up) |
| `libSceNet` | 219 exports | 2 PASS-THRU hooks | by design; targeted redirect hooks later (Tasks 6/8) |
| `libSceNetCtl` | 98 exports | none | check whether game needs faked interface status |
| `libSceHttp` | 115 exports | none | URL-routing layer needed (Task 6) |
| `libSceSsl` | 208 exports | none | prefer plain-HTTP LAN; never globally disable TLS verification |
| `libSceNpTrophy` | 87 exports | **ABSENT** | likely menu-only; verify non-blocking |
| `libSceNpCommerce` | 11 exports | **ABSENT** | likely menu-only; verify non-blocking |
| `libSceNpProfileDialog` | 9 exports | **ABSENT** | likely menu-only; verify non-blocking |

## Key flows and what each needs

1. **Sign-in / online entry** — NpAuth + NpCommon + NpManager state. Needs identity facade (Task 6).
2. **WebAPI / push events** — plugin has an implementation; must match server endpoints + token handling (validated Task 5).
3. **Game HTTP bootstrap** — `ss.info`, directory/statistics, summon broker. No plugin support for
   generic `sceHttp`; needs a game-scoped URL hook (design + implement, Task 6).
4. **Matchmaking** — NpMatching2 room lifecycle + callbacks; handoff exists but is commented out; full port (Task 7).
5. **Peer transport** — custom `SHAD` handshake/control packets; port target (Task 8).

## Protocol anchors already identified

- Server wire protocol v1 (15-byte header, protobuf payloads — server source `documentation/protocol.md`).
- Plugin client implements login/token/server-features; commented dispatcher references matching command
  range 100–200 (`np_handler.cpp` 468–484) — evidence of the intended mapping, not an implementation.
- PC signaling defines the `SHAD` magic + echo ping/pong + handshake/control states (`np_signaling_state.h`).

## Riskiest unknowns (ranked)

1. Native libs on console may own sockets/contexts in ways the custom transport can't reuse — proven only by Task 8 test.
2. Bloodborne's exact HTTP endpoint set under our server is unmapped until Task 6 captures.
3. Function-level NP import surface (which NIDs are actually called) — follow-up extraction.
4. Whether NpScore/trophy/commerce calls gate session setup (unlikely, unverified).

## Immediate next analysis steps

- Function-level import extraction from the SELF.
- Diff plugin WebAPI + protocol against server source (field-level).
- Sweep scene for other GoldHEN NP plugins (reuse-first).
