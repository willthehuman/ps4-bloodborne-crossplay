#!/usr/bin/env python3
"""Create a shadNet account on the ISOLATED TEST instance (quiet registrar).

Password handling (per plan Task 4.4): the password is never passed via argv
and never echoed. Supply it via the SHADNET_TEST_PASSWORD env var, or type it
at a hidden interactive prompt. Output is limited to status lines.

Usage:
    register-test-account.py <npid> [--host H] [--port P] [--email E]
                             [--secret S] [--dry-run] [--no-verify]

Defaults: SHADNET_TEST_SERVER env or 192.168.50.233:31313 (test instance).
Mirrors the conventions of shadnet-p2p's scripts/create_test_user.sh.
"""

import argparse
import getpass
import os
import re
import socket
import struct
import sys

NPID_RE = re.compile(r"^[A-Za-z0-9_-]{3,16}$")
DEFAULT_SERVER = "172.31.13.23:31313"  # isolated TEST instance (container; seats/console use 192.168.50.233)

HEADER = struct.Struct("<BHQI")
CMD_LOGIN, CMD_CREATE = 0, 2

ERR = {
    0: "OK", 1: "Malformed", 2: "Invalid", 3: "InvalidInput", 4: "TooSoon",
    5: "LoginError", 6: "LoginAlreadyLoggedIn", 8: "LoginInvalidPassword",
    9: "LoginInvalidToken", 10: "CreationError", 11: "CreationExistingUsername",
    12: "CreationBannedEmailProvider", 13: "CreationExistingEmail",
    23: "Unauthorized", 24: "DbFail", 26: "NotFound", 33: "Unsupported",
}


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def f_str(num, value):
    data = value.encode()
    return bytes([(num << 3) | 2]) + varint(len(data)) + data


def blob(data):
    return struct.pack("<I", len(data)) + data


def recvn(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed by server")
        buf += chunk
    return buf


def recv_reply(sock):
    while True:
        ptype, cmd, size, pktid = HEADER.unpack(recvn(sock, 15))
        payload = recvn(sock, size - 15) if size > 15 else b""
        if ptype == 1:  # Reply
            return payload[0] if payload else -1


def do(host, port, cmd, payload, timeout=10):
    with socket.create_connection((host, port), timeout=timeout) as sock:
        recvn(sock, 19)  # ServerInfo handshake (15 + u32 version)
        sock.sendall(HEADER.pack(0, cmd, 15 + len(payload), 1) + payload)
        return recv_reply(sock)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("npid")
    default_host, _, default_port = DEFAULT_SERVER.partition(":")
    env = os.environ.get("SHADNET_TEST_SERVER", "")
    if env:
        default_host, _, default_port = env.partition(":")
    ap.add_argument("--host", default=default_host)
    ap.add_argument("--port", type=int, default=int(default_port or 31313))
    ap.add_argument("--email", default=None)
    ap.add_argument("--secret", default=os.environ.get("SHADNET_REGISTRATION_SECRET", ""))
    ap.add_argument("--dry-run", action="store_true", help="validate and print non-secret settings only")
    ap.add_argument("--no-verify", action="store_true", help="skip the login verification step")
    args = ap.parse_args()

    npid = args.npid
    if not NPID_RE.match(npid) or npid == "DeletedUser":
        print("NPID must be 3-16 letters, numbers, hyphens or underscores.", file=sys.stderr)
        return 2
    email = args.email or f"{npid.lower()}@bb.local"
    if "@" not in email:
        print("A nonempty email address is required.", file=sys.stderr)
        return 2
    if not (1 <= args.port <= 65535):
        print("Port must be between 1 and 65535.", file=sys.stderr)
        return 2

    print(f"  server:   {args.host}:{args.port}")
    print(f"  npid:     {npid}")
    print(f"  email:    {email}")
    print(f"  secret:   {'configured' if args.secret else 'not configured'}")

    if args.dry_run:
        print("  dry run — no account created.")
        return 0

    password = os.environ.get("SHADNET_TEST_PASSWORD", "")
    if not password:
        if not sys.stdin.isatty():
            print("Set SHADNET_TEST_PASSWORD or run interactively.", file=sys.stderr)
            return 2
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            return 2
        del confirm
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        return 2

    try:
        payload = blob(f_str(1, npid) + f_str(2, password) + f_str(4, email))
        if args.secret:
            payload = blob(f_str(1, npid) + f_str(2, password) + f_str(4, email)
                           + f_str(5, args.secret))
        err = do(args.host, args.port, CMD_CREATE, payload)
    except OSError as exc:
        print(f"FAILED   {npid}: cannot reach {args.host}:{args.port} ({exc})", file=sys.stderr)
        return 1

    name = ERR.get(err, f"error {err}")
    if err == 0:
        print(f"  created  {npid}")
    elif err == 11:
        print(f"  exists   {npid} (password unchanged)")
        return 1
    else:
        print(f"FAILED   {npid}: {name}", file=sys.stderr)
        return 1

    if args.no_verify:
        return 0

    try:
        login_payload = blob(f_str(1, npid) + f_str(2, password))
        err = do(args.host, args.port, CMD_LOGIN, login_payload)
    except OSError as exc:
        print(f"WARNING  login verification could not run ({exc})", file=sys.stderr)
        return 1
    if err == 0:
        print(f"  verified {npid} (login OK)")
        return 0
    print(f"WARNING  login verification failed: {ERR.get(err, err)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
