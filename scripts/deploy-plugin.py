#!/usr/bin/env python3
"""Deploy the shadNet-PS4 plugin to the console over FTP (plan Task 5).

Writes (the game must be CLOSED; nothing else is touched):
    /data/GoldHEN/plugins/shadNet-PS4.prx   uploaded, readback sha256-verified
    /data/shadnet/config.json               generated, readback verified
    /data/GoldHEN/plugins.ini               merged — only our [title] stanza changes

Safety rules:
  * the account password is read from the accounts file or an env var, never argv
  * existing plugins.ini / config.json are backed up before any write
  * --dry-run prints the exact change set (password masked) and writes nothing
  * every upload is read back and hash/size-compared

Usage:
  scripts/deploy-plugin.py [--enabled] [--dry-run]
                           [--accounts-file private/test-server/accounts.env]
                           [--npid crowps4] [--user-id 289813409]
                           [--server 192.168.50.233:31313]
                           [--webapi http://192.168.50.233:31315]
                           [--title CUSA03173] [--prx <file>] [--host 192.168.50.90]
"""

import argparse
import difflib
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parent.parent

REMOTE_PRX = "/data/GoldHEN/plugins/shadNet-PS4.prx"
REMOTE_INI = "/data/GoldHEN/plugins.ini"
REMOTE_CFG = "/data/shadnet/config.json"
REMOTE_CFG_DIR = "/data/shadnet"

NPID_RE = re.compile(r"^[A-Za-z0-9_-]{3,16}$")


# ---------------------------------------------------------------- pure logic

def build_config(user_id, npid, password, server, webapi, enabled=False,
                 appear_offline=False, extra_users=None):
    """Mirror of the plugin's config schema (src/shadnet/config.h).

    user_id: local Orbis user id as a DECIMAL string ("289813409" for 0x114633a1).
    extra_users: optional list of dicts {user_id, npid, password, enabled}.
    """
    def user_block(np_, pw_, en_, ao_):
        return {
            "shadnet_appear_offline": bool(ao_),
            "shadnet_enabled": bool(en_),
            "shadnet_npid": np_,
            "shadnet_password": pw_,
        }

    cfg = {user_id: user_block(npid, password, enabled, appear_offline)}
    for u in extra_users or []:
        cfg[u["user_id"]] = user_block(u["npid"], u["password"],
                                       u.get("enabled", False),
                                       u.get("appear_offline", False))
    cfg["Server"] = {
        "shadnet_enable_upnp": False,
        "shadnet_server": server,
        "shadnet_webapi_server": webapi,
        "shadnet_signaling_info": "",
    }
    return cfg


def config_to_json(cfg):
    return json.dumps(cfg, indent=2, sort_keys=True) + "\n"


def validate_user_id(s):
    if not re.fullmatch(r"[1-9][0-9]{0,9}", s or ""):
        raise ValueError(f"user id must be a decimal Orbis user id, got {s!r}")
    return s


def validate_npid(s):
    if not NPID_RE.fullmatch(s or ""):
        raise ValueError(f"invalid npid {s!r} (expected [A-Za-z0-9_-]{{3,16}})")
    return s


def validate_hostport(s):
    host, sep, port = (s or "").rpartition(":")
    if not sep or not host or not port.isdigit() or not (1 <= int(port) <= 65535):
        raise ValueError(f"expected host:port, got {s!r}")
    return s


def validate_webapi(s):
    if not re.fullmatch(r"https?://\S+", s or ""):
        raise ValueError(f"expected http(s) URL, got {s!r}")
    return s


def parse_accounts_file(path, npid):
    """Read SHADNET_TEST_PW_<NPID> from an accounts file (simple KEY=VALUE)."""
    key = f"SHADNET_TEST_PW_{npid.upper()}"
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        if k.strip() == key and v.strip():
            return v.strip()
    return None


def _is_header(line):
    s = line.strip()
    return s.startswith("[") and s.endswith("]")


def merge_plugins_ini(text, title, prx_path):
    """Ensure [title] exists and contains prx_path. Returns (new_text, changed).

    Preserves every other line verbatim. Idempotent.
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if _is_header(l) and l.strip()[1:-1].strip() == title), None)

    def finish(new_lines):
        new_text = "\n".join(new_lines)
        if text.endswith("\n") or text == "":
            new_text += "\n"
        return new_text

    if start is None:
        body = text if text.endswith("\n") or not text else text + "\n"
        if body and not body.endswith("\n\n"):
            body += "\n"
        return body + f"[{title}]\n{prx_path}\n", True

    end = next((j for j in range(start + 1, len(lines)) if _is_header(lines[j])),
               len(lines))
    seg = lines[start + 1:end]

    new_seg, done = [], False
    for l in seg:
        s = l.strip()
        if not done and s == prx_path:
            new_seg.append(l)
            done = True
        elif not done and s.endswith("shadNet-PS4.prx"):
            new_seg.append(prx_path)
            done = True
        else:
            new_seg.append(l)
    if not done:
        new_seg = [prx_path] + new_seg

    new_lines = lines[:start + 1] + new_seg + lines[end:]
    new_text = finish(new_lines)
    return new_text, new_text != text


def remove_prx_from_ini(text, title, filename="shadNet-PS4.prx"):
    """Remove any line ending with `filename` inside the [title] stanza.

    If the stanza becomes void of entries, its header is removed as well.
    Returns (new_text, changed).
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if _is_header(l) and l.strip()[1:-1].strip() == title), None)
    if start is None:
        return text, False
    end = next((j for j in range(start + 1, len(lines)) if _is_header(lines[j])),
               len(lines))
    seg = [l for l in lines[start + 1:end] if not l.strip().endswith(filename)]
    if seg == lines[start + 1:end]:
        return text, False
    keep_header = any(l.strip() and not l.strip().startswith(("#", ";")) for l in seg)
    new_lines = lines[:start] + ([lines[start]] if keep_header else []) + seg + lines[end:]
    new_text = "\n".join(new_lines)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text, True


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


# ---------------------------------------------------------------- ftp plumbing

def load_ftp_module():
    spec = importlib.util.spec_from_file_location("ps4ftp", WS / "scripts" / "ps4-ftp.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def remote_read(ftp, path):
    buf = io.BytesIO()
    try:
        ftp.retrbinary(f"RETR {path}", buf.write)
    except Exception:
        return None
    return buf.getvalue()


def remote_write(ftp, path, data: bytes):
    ftp.storbinary(f"STOR {path}", io.BytesIO(data))


def ensure_dir(ftp, path):
    try:
        ftp.mkd(path)
    except Exception:
        pass  # exists (or created concurrently)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Deploy shadNet-PS4 plugin to the console (Task 5)")
    ap.add_argument("--host", default="192.168.50.90")
    ap.add_argument("--title", default="CUSA03173")
    ap.add_argument("--user-id", default="289813409", help="Orbis user id, decimal (0x114633a1)")
    ap.add_argument("--npid", default="crowps4")
    ap.add_argument("--accounts-file", default=str(WS / "private" / "test-server" / "accounts.env"))
    ap.add_argument("--server", default="192.168.50.233:31313")
    ap.add_argument("--webapi", default="http://192.168.50.233:31315")
    ap.add_argument("--prx", default=None)
    ap.add_argument("--enabled", action="store_true",
                    help="set shadnet_enabled=true for the user (default: disabled for a safe first boot)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    validate_user_id(args.user_id)
    validate_npid(args.npid)
    validate_hostport(args.server)
    validate_webapi(args.webapi)

    if args.prx:
        prx = Path(args.prx)
    else:
        candidates = sorted((WS / "private" / "artifacts").glob("shadNet-PS4-*.prx"),
                            key=lambda p: p.stat().st_mtime)
        if not candidates:
            print("FAIL: no PRX in private/artifacts; build first (scripts/build-plugin.sh)", file=sys.stderr)
            return 2
        prx = candidates[-1]
    if not prx.is_file():
        print(f"FAIL: prx not found: {prx}", file=sys.stderr)
        return 2
    prx_data = prx.read_bytes()
    prx_sha = sha256_bytes(prx_data)

    password = os.environ.get("SHADNET_TEST_PASSWORD") or parse_accounts_file(
        args.accounts_file, args.npid)
    if not password:
        print(f"FAIL: no password for {args.npid} (set SHADNET_TEST_PASSWORD or add it to "
              f"{args.accounts_file})", file=sys.stderr)
        return 2

    cfg_text = config_to_json(build_config(args.user_id, args.npid, password,
                                           args.server, args.webapi, enabled=args.enabled))
    cfg_bytes = cfg_text.encode()

    ftp = load_ftp_module().connect(args.host, 2121)
    existing_ini_b = remote_read(ftp, REMOTE_INI)
    existing_ini = existing_ini_b.decode() if existing_ini_b else ""
    merged_ini, ini_changed = merge_plugins_ini(existing_ini, args.title, REMOTE_PRX)
    merged_b = merged_ini.encode()

    print("== deploy plan ==")
    print(f"  console:   {args.host} (FTP)")
    print(f"  prx:       {prx.name} ({len(prx_data)} bytes) sha256={prx_sha[:24]}…")
    print(f"  config:    {args.user_id}: npid={args.npid} enabled={args.enabled} "
          f"server={args.server}")
    print(f"  webapi:    {args.webapi}")
    masked = cfg_text.replace(password, "***") if password else cfg_text
    print("  config.json:")
    for line in masked.splitlines():
        print("    " + line)
    if ini_changed:
        print("  plugins.ini changes:")
        for line in difflib.unified_diff(existing_ini.splitlines(), merged_ini.splitlines(),
                                         lineterm="", n=2):
            print("    " + line)
    else:
        print(f"  plugins.ini: [{args.title}] already points at {REMOTE_PRX}")

    if args.dry_run:
        print("== dry run — nothing written ==")
        ftp.quit()
        return 0

    # backups
    ts = time.strftime("%Y%m%d-%H%M%S")
    bdir = WS / "private" / "backups" / f"plugin-deploy-{ts}"
    bdir.mkdir(parents=True, exist_ok=True)
    if existing_ini_b is not None:
        (bdir / "plugins.ini.bak").write_bytes(existing_ini_b)
    existing_cfg = remote_read(ftp, REMOTE_CFG)
    if existing_cfg is not None:
        (bdir / "config.json.bak").write_bytes(existing_cfg)
    existing_prx = remote_read(ftp, REMOTE_PRX)
    if existing_prx is not None:
        (bdir / "shadNet-PS4.prx.bak").write_bytes(existing_prx)
    print(f"== backups -> {bdir} ==")

    # writes
    ensure_dir(ftp, REMOTE_CFG_DIR)
    remote_write(ftp, REMOTE_PRX, prx_data)
    remote_write(ftp, REMOTE_CFG, cfg_bytes)
    remote_write(ftp, REMOTE_INI, merged_b)

    # readback verification
    ok = True
    rb = remote_read(ftp, REMOTE_PRX)
    if rb is None or sha256_bytes(rb) != prx_sha:
        print("FAIL: prx readback mismatch", file=sys.stderr)
        ok = False
    rb = remote_read(ftp, REMOTE_CFG)
    if rb is None or rb != cfg_bytes:
        print("FAIL: config.json readback mismatch", file=sys.stderr)
        ok = False
    rb = remote_read(ftp, REMOTE_INI)
    if rb is None or rb != merged_b:
        print("FAIL: plugins.ini readback mismatch", file=sys.stderr)
        ok = False
    ftp.quit()

    if ok:
        print("== deployed & verified ==")
        print(f"  {REMOTE_PRX}  sha256={prx_sha[:24]}…")
        print(f"  {REMOTE_CFG}  sha256={sha256_bytes(cfg_bytes)[:24]}…")
        print(f"  {REMOTE_INI}  (merged, verified)")
        print("NOTE: launch the game (with only the intended profile logged in) to test.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
