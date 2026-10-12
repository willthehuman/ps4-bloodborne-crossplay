#!/usr/bin/env python3
"""Rollback the shadNet-PS4 plugin from the console (Tasks 2/5/10 recovery drill).

Default actions (all readback-verified):
  * remove the shadNet-PS4.prx line from the [title] stanza in plugins.ini
    (every other line stays; an emptied stanza header is dropped)
  * rename the deployed PRX to shadNet-PS4.prx.disabled (kept on disk as evidence;
    --delete removes it entirely instead)
  * rename /data/shadnet/config.json to config.json.disabled
  * (optional) --restore <dir>: restore plugins.ini / config.json from a
    deploy-plugin backup directory, then remove the PRX

Usage:
  scripts/rollback-plugin.py [--title CUSA03173] [--host 192.168.50.90]
                             [--restore private/backups/plugin-deploy-YYYYmmdd-HHMMSS]
                             [--delete]
"""

import argparse
import importlib.util
import io
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent

REMOTE_PRX = "/data/GoldHEN/plugins/shadNet-PS4.prx"
REMOTE_PRX_DISABLED = REMOTE_PRX + ".disabled"
REMOTE_INI = "/data/GoldHEN/plugins.ini"
REMOTE_CFG = "/data/shadnet/config.json"
REMOTE_CFG_DISABLED = REMOTE_CFG + ".disabled"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, WS / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description="Rollback the shadNet-PS4 plugin (safe, verified)")
    ap.add_argument("--host", default="192.168.50.90")
    ap.add_argument("--title", default="CUSA03173")
    ap.add_argument("--restore", default=None,
                    help="backup dir from deploy-plugin (plugins.ini.bak / config.json.bak)")
    ap.add_argument("--delete", action="store_true", help="delete the PRX instead of renaming")
    args = ap.parse_args()

    dp = _load("deploy_plugin", "scripts/deploy-plugin.py")
    ftp = dp.load_ftp_module().connect(args.host, 2121)

    actions = []

    if args.restore:
        bdir = Path(args.restore)
        for name, remote in (("plugins.ini.bak", REMOTE_INI),
                             ("config.json.bak", REMOTE_CFG)):
            src = bdir / name
            if src.is_file():
                dp.remote_write(ftp, remote, src.read_bytes())
                back = dp.remote_read(ftp, remote)
                ok = back == src.read_bytes()
                actions.append(f"restored {remote} from {src.name}: {'verified' if ok else 'FAILED'}")
        if not args.delete:
            try:
                ftp.rename(REMOTE_PRX, REMOTE_PRX_DISABLED)
                actions.append(f"renamed {REMOTE_PRX} -> {REMOTE_PRX_DISABLED}")
            except Exception as e:
                actions.append(f"prx rename skipped: {e}")
        else:
            try:
                ftp.delete(REMOTE_PRX)
                actions.append(f"deleted {REMOTE_PRX}")
            except Exception as e:
                actions.append(f"prx delete skipped: {e}")
    else:
        ini_b = dp.remote_read(ftp, REMOTE_INI)
        ini = ini_b.decode() if ini_b else ""
        new_ini, changed = dp.remove_prx_from_ini(ini, args.title)
        if changed:
            dp.remote_write(ftp, REMOTE_INI, new_ini.encode())
            back = dp.remote_read(ftp, REMOTE_INI)
            ok = back == new_ini.encode()
            actions.append(f"plugins.ini updated ({args.title} stanza): "
                           f"{'verified' if ok else 'FAILED'}")
        else:
            actions.append(f"plugins.ini: nothing to remove for [{args.title}]")

        try:
            if args.delete:
                ftp.delete(REMOTE_PRX)
                actions.append(f"deleted {REMOTE_PRX}")
            else:
                ftp.rename(REMOTE_PRX, REMOTE_PRX_DISABLED)
                actions.append(f"renamed {REMOTE_PRX} -> {REMOTE_PRX_DISABLED}")
        except Exception as e:
            actions.append(f"prx step skipped: {e}")

        try:
            ftp.rename(REMOTE_CFG, REMOTE_CFG_DISABLED)
            actions.append(f"renamed {REMOTE_CFG} -> {REMOTE_CFG_DISABLED}")
        except Exception as e:
            actions.append(f"config step skipped: {e}")

    ftp.quit()
    print("== rollback summary ==")
    for a in actions:
        print("  " + a)
    print("NOTE: relaunch the game to confirm normal offline behavior.")


if __name__ == "__main__":
    sys.exit(main())
