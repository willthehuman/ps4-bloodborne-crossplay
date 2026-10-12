#!/usr/bin/env python3
"""Freeze a built PRX + its matching unstripped ELF with a manifest.

Task 1 of the crossplay recovery plan: every console run must be attributable
to one source/config/binary tuple. `bin/plugins/elf_final/` is overwritten by
each build, so the ELF must be copied out together with the PRX.

Usage:
    scripts/freeze-artifact.py [--prx PATH] [--elf PATH] [--note TEXT] [--game GAME_ID]

Defaults:
    --prx vendor/shadNet-PS4/bin/plugins/prx_final/shadNet-PS4.prx
    --elf vendor/shadNet-PS4/bin/plugins/elf_final/shadNet-PS4.elf

Effects:
    - copies <prx> -> private/artifacts/shadNet-PS4-<sha8>.prx   (if absent / differing)
    - copies <elf> -> private/artifacts/shadNet-PS4-<sha8>.elf   (if absent)
    - writes   private/runs/<UTCstamp>-<sha8>/manifest.json

Exit codes: 0 ok, 1 error, 2 pair mismatch (both files must exist).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
ARTIFACTS = WS / "private" / "artifacts"
RUNS = WS / "private" / "runs"

DEFAULT_PRX = WS / "vendor" / "shadNet-PS4" / "bin" / "plugins" / "prx_final" / "shadNet-PS4.prx"
DEFAULT_ELF = WS / "vendor" / "shadNet-PS4" / "bin" / "plugins" / "elf_final" / "shadNet-PS4.elf"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_rev(repo: Path) -> dict:
    """Best-effort revision info; never fails the script."""
    out: dict = {}
    try:
        out["head"] = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or None
        out["branch"] = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or None
        dirty = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        out["dirty"] = bool(dirty)
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        out["error"] = repr(exc)
    return out


def tool_version(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        line = (r.stdout or r.stderr).splitlines()
        return line[0].strip() if line else None
    except Exception:  # noqa: BLE001
        return None


def copy_into_artifacts(src: Path, sha: str, stem: str | None = None) -> Path:
    """Copy into private/artifacts as shadNet-PS4-<stem or sha8><suffix>.
    The ELF is named with the PRX's stem so the pair sorts together."""
    dst = ARTIFACTS / f"shadNet-PS4-{stem or sha[:8]}{src.suffix}"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if dst.exists() and sha256_file(dst) == sha:
        return dst
    shutil.copy2(src, dst)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prx", type=Path, default=DEFAULT_PRX)
    ap.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    ap.add_argument("--note", default="")
    ap.add_argument("--game", default="CUSA03173/01.09")
    args = ap.parse_args()

    prx, elf = args.prx.resolve(), args.elf.resolve()
    missing = [str(p) for p in (prx, elf) if not p.is_file()]
    if missing:
        print(f"ERROR: missing file(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    prx_sha, elf_sha = sha256_file(prx), sha256_file(elf)
    short = prx_sha[:8]
    now = _dt.datetime.now(_dt.timezone.utc)

    prx_frozen = copy_into_artifacts(prx, prx_sha)
    elf_frozen = copy_into_artifacts(elf, elf_sha, stem=short)

    manifest = {
        "run_id": f"{now:%Y-%m-%d_%H%M%S}-{short}",
        "created_utc": now.isoformat(),
        "game": args.game,
        "note": args.note,
        "artifact": {
            "prx": {
                "source": str(prx.relative_to(WS)),
                "frozen": str(prx_frozen.relative_to(WS)),
                "sha256": prx_sha,
                "size": prx.stat().st_size,
            },
            "elf": {
                "source": str(elf.relative_to(WS)),
                "frozen": str(elf_frozen.relative_to(WS)),
                "sha256": elf_sha,
                "size": elf.stat().st_size,
            },
        },
        "source_revisions": {
            "workspace": git_rev(WS),
            "plugin": git_rev(WS / "vendor" / "shadNet-PS4"),
            "server": git_rev(WS / "vendor" / "shadnet-p2p"),
        },
        "toolchain": {
            "clang": tool_version(["clang", "--version"]),
            "cmake": tool_version(["cmake", "--version"]),
            "ld_lld": tool_version(["ld.lld", "--version"]),
        },
        "verification_level": "size+sha256 of local pair; remote deployment identity is "
                              "recorded separately by scripts/deploy-plugin.py output",
    }

    run_dir = RUNS / manifest["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"run_id:  {manifest['run_id']}")
    print(f"prx:     {prx_sha}  ({prx.stat().st_size} bytes)")
    print(f"elf:     {elf_sha}  ({elf.stat().st_size} bytes)")
    print(f"frozen:  {prx_frozen.name}, {elf_frozen.name}")
    print(f"manifest:{manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
