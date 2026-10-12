#!/usr/bin/env python3
"""Capture the console's GoldHEN klog stream (TCP 3232) to a file while a test runs.

Usage:
  scripts/capture-klog.py [--host 192.168.50.90] [--seconds 180]
                          [--filter shadNet|NpHandler|Config]
                          [--out private/logs/klog-YYYYmmdd-HHMMSS.log]

Everything is saved; matching lines are echoed live. The plugin's LOG_* output
and GoldHEN's plugin banner both land in this stream.
"""

import argparse
import socket
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description="Capture GoldHEN klog over TCP 3232")
    ap.add_argument("--host", default="192.168.50.90")
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--filter", default="",
                    help="echo only lines containing this substring (case-insensitive)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = Path(args.out) if args.out else (
        WS / "private" / "logs" / f"klog-{time.strftime('%Y%m%d-%H%M%S')}.log")
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        sock = socket.create_connection((args.host, 3232), timeout=5)
    except OSError as exc:
        print(f"FAIL: cannot reach klog at {args.host}:3232 ({exc})", file=sys.stderr)
        return 1
    sock.settimeout(1.0)
    deadline = time.time() + args.seconds
    total = 0
    needle = args.filter.lower()
    print(f"[capture] {args.host}:3232 -> {out} for {args.seconds}s"
          + (f" (filter: {args.filter})" if args.filter else ""))
    with open(out, "wb") as f:
        while time.time() < deadline:
            try:
                data = sock.recv(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            f.write(data)
            f.flush()
            total += len(data)
            if needle:
                for line in data.decode(errors="replace").splitlines():
                    if needle in line.lower():
                        print(line)
    sock.close()
    print(f"[capture] {total} bytes captured -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
