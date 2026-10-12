#!/usr/bin/env python3
"""Minimal FTP helper for the PS4 (GoldHEN ftpsrv).

Used by the cross-play project for console identity capture and backups.
`put` is explicit; everything else is pure read.

Usage:
  ps4-ftp.py list   <path>
  ps4-ftp.py get    <remote> <local>
  ps4-ftp.py mirror <remote_dir> <local_dir>
  ps4-ftp.py put    <local> <remote>
  ps4-ftp.py mkdir  <path>            (creates parents as needed)
  ps4-ftp.py rename <src> <dst>
  ps4-ftp.py rm     <remote_file>

Options:
  --host H (default 192.168.50.90)   --port P (default 2121)
"""
import argparse
import ftplib
import hashlib
from pathlib import Path


def connect(host, port):
    ftp = ftplib.FTP(timeout=60)
    ftp.connect(host, port)
    ftp.login("anonymous", "")
    ftp.set_pasv(True)
    return ftp


def parse_list(line):
    """Parse a unix-style LIST line -> (name, is_dir) or None."""
    parts = line.split(None, 8)
    if len(parts) < 9:
        return None
    perms, name = parts[0], parts[8]
    if " -> " in name:
        name = name.split(" -> ")[0]
    return name, perms.startswith("d")


def list_dir(ftp, path):
    lines = []
    ftp.retrlines(f"LIST {path}", lines.append)
    return lines


def download_file(ftp, remote, local):
    local = Path(local)
    local.parent.mkdir(parents=True, exist_ok=True)
    with local.open("wb") as f:
        ftp.retrbinary(f"RETR {remote}", f.write)
    h = hashlib.sha256()
    with local.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    size = local.stat().st_size
    print(f"  {remote}  ->  {local}  ({size} bytes)  sha256={h.hexdigest()}")
    return size


def mirror(ftp, remote_dir, local_dir):
    total_files = total_bytes = 0
    stack = [(remote_dir, Path(local_dir))]
    while stack:
        rdir, ldir = stack.pop()
        try:
            lines = list_dir(ftp, rdir)
        except ftplib.error_perm as e:
            print(f"  !! cannot list {rdir}: {e}")
            continue
        for line in lines:
            parsed = parse_list(line)
            if not parsed:
                continue
            name, is_dir = parsed
            rpath = rdir.rstrip("/") + "/" + name
            lpath = ldir / name
            if is_dir:
                stack.append((rpath, lpath))
            else:
                try:
                    total_bytes += download_file(ftp, rpath, lpath)
                    total_files += 1
                except ftplib.error_perm as e:
                    print(f"  !! cannot get {rpath}: {e}")
    print(f"mirror done: {total_files} files, {total_bytes} bytes -> {local_dir}")


def main():
    ap = argparse.ArgumentParser(description="PS4 FTP helper")
    ap.add_argument("--host", default="192.168.50.90")
    ap.add_argument("--port", type=int, default=2121)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("path")
    p = sub.add_parser("get")
    p.add_argument("remote")
    p.add_argument("local")
    p = sub.add_parser("mirror")
    p.add_argument("remote_dir")
    p.add_argument("local_dir")
    p = sub.add_parser("put")
    p.add_argument("local")
    p.add_argument("remote")
    p = sub.add_parser("mkdir")
    p.add_argument("path")
    p = sub.add_parser("rename")
    p.add_argument("src")
    p.add_argument("dst")
    p = sub.add_parser("rm")
    p.add_argument("remote")
    args = ap.parse_args()

    ftp = connect(args.host, args.port)
    try:
        if args.cmd == "list":
            for line in list_dir(ftp, args.path):
                print(line)
        elif args.cmd == "get":
            download_file(ftp, args.remote, args.local)
        elif args.cmd == "mirror":
            mirror(ftp, args.remote_dir, args.local_dir)
        elif args.cmd == "put":
            with open(args.local, "rb") as f:
                ftp.storbinary(f"STOR {args.remote}", f)
            print(f"uploaded {args.local} -> {args.remote}")
        elif args.cmd == "mkdir":
            cur = ""
            for part in [x for x in args.path.split("/") if x]:
                cur += "/" + part
                try:
                    ftp.mkd(cur)
                    print("mkd", cur)
                except ftplib.error_perm as e:
                    print("exists/skip", cur, "->", e)
        elif args.cmd == "rename":
            ftp.rename(args.src, args.dst)
            print("renamed", args.src, "->", args.dst)
        elif args.cmd == "rm":
            ftp.delete(args.remote)
            print("deleted", args.remote)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


if __name__ == "__main__":
    main()
