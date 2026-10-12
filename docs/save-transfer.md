# Save transfer — Will's PC character → PS4 (via Apollo Save Tool)

> **Status: PREPARED, NOT EXECUTED.** The console's game has no save yet; the import runs together
> with Will at the console. Next action: Will launches Bloodborne once to create the save container.
> Date: 2026-10-12.

## Findings (verified 2026-10-12)

- **PC live save** (seat A, Will): `desktop-a/.local/share/bbport/user/savedata/1/CUSA00207/SPRJ0005/`
  — one active character (`userdata0000`, last written 2026-10-11 23:35) + 9 empty slots + backups;
  ~14.5 MB. Same content in the nightly backup `save-backup-hermes/bbport-user-2256.tgz`.
- **Console:** game = `CUSA03173` (GOTY EU, v1.09), **no save yet**. Will's profile = `114633a1`.
  Old saves from earlier installs, **left untouched**: `CUSA00207` + `CUSA00900` (Aug 14 / Jul 11).
- **Icons byte-identical** across PC save + both console saves → same game across all three.
- **Apollo Save Tool v2.3.2 is installed** (`/user/app/APOL00004`; pkg via `NPXS39041/downloads`).
- **Save layout** (all Bloodborne editions): save folder `SPRJ0005` containing
  `userdata0000..0010`, `backup0000`, `backup0010`, `sce_sys/` (param.sfo + icon0.png).
  Console stores it encrypted (`sdimg_SPRJ0005` + `SPRJ0005.bin`); PC stores the decrypted files directly.
- Why the PC save lives under `CUSA00207` while the game runs as `CUSA03173`: observed but not fully
  explained (standard-vs-GOTY edition namespace). Apollo's documented "same game, different CUSA IDs"
  method covers exactly this case.

## Payload (staged, reproducible)

`private/stage/save-transfer/from-pc/SPRJ0005/` — hashes in `payload.sha256`.

- `userdata0000..0010`, `backup0000`, `backup0010`, `sce_sys/icon0.png`
- `sce_sys/param.sfo` — copy patched `TITLE_ID: CUSA00207 → CUSA03173`
- `sce_sys/param.sfo.orig` — untouched original

## Plan A — Apollo fake-USB path (fewest console steps)

1. **Will:** launch Bloodborne once → create a character / reach the first lamp → quit.
   (Creates the console's `CUSA03173` save; also the Task 2 baseline.)
2. **Me (FTP):** back up the fresh save; create `/data/fakeusb/PS4/APOLLO/<USER-ID>_CUSA03173_SPRJ0005/`
   and upload the payload files. *(First write to the console — requested by Will; fully reversible.)*
3. **Will:** Apollo → **USB Saves** → select the save → **Copy save game** → to HDD → accept **resign**.
4. **Will:** launch the game → check the character. 

If flagged / ??? / corrupted: keystone fix per Apollo docs (export keystone from the fresh save,
import into the new one), or fall back to Plan B.

## Plan B — Apollo decrypted export/import ("different CUSA IDs" method)

1. **Will:** Apollo → HDD Saves → fresh save → **Export decrypted save files**.
2. **Me (FTP):** overwrite the exported data files under `/data/apollo/<profile>/…` with the payload
   (keep the target's `sce_sys`), per Apollo's region/eidition method.
3. **Will:** Apollo → **Import decrypted save files** → **Apply Changes & Resign**.

## Safety

- Old console saves (`CUSA00207`, `CUSA00900`) are not touched; the operation targets only the new
  `CUSA03173` save. Fresh-save backup is taken before any import. Everything reversible by deleting
  the imported save and re-launching the game.
- Apollo's resign step handles user/account binding; if Apollo requests account activation, that is a
  one-time "User Tools → Activate PS4 Accounts" step.

## Open items

- Whether the game accepts the import without a keystone fix.
- Whether the fakeusb folder needs the `<USER-ID>_` prefix (docs are ambiguous; fallback = title-id-only name).
- After success: back up the final save + record hashes; then the console character can co-op with the seats.
