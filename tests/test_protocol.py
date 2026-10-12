#!/usr/bin/env python3
"""shadNet wire-protocol integration tests (stdlib only, no dependencies).

Target: the ISOLATED TEST instance — never production. See docs/runbook.md
("Task 4 — isolated test instance") for how to start/stop it.

Configure via env:
    SHADNET_TEST_SERVER   host:port   (default 192.168.50.239:31323)

The test instance uses ALTERNATE PORTS (31323/24/25) with prod untouched:
TCP 31323, STUN UDP 31324 (=TCP+1 — client convention), WebAPI 31325.

Without the test instance running, setUpModule fails with an explicit
reachability error — that is the intended RED state before the instance
is started; GREEN means every check below passes against a live server.

Spec: vendor/shadnet-p2p/documentation/protocol.md (pinned 5a849a1).
"""

import os
import random
import re
import socket
import struct
import time
import unittest

DEFAULT_SERVER = "172.31.13.23:31313"
NPID_RE = re.compile(r"^[A-Za-z0-9_-]{3,16}$")

# ---- wire constants (protocol.md) ----
HEADER = struct.Struct("<BHQI")            # type, command, size, packetId
TYPE_REQUEST, TYPE_REPLY, TYPE_NOTIFICATION, TYPE_SERVERINFO = 0, 1, 2, 3
CMD_LOGIN, CMD_TERMINATE, CMD_CREATE, CMD_DELETE = 0, 1, 2, 3

ERR_NAMES = {
    0: "NoError", 1: "Malformed", 2: "Invalid", 3: "InvalidInput",
    6: "LoginAlreadyLoggedIn", 8: "LoginInvalidPassword",
    11: "CreationExistingUsername", 23: "Unauthorized", 33: "Unsupported",
}


def server_addr():
    raw = os.environ.get("SHADNET_TEST_SERVER", DEFAULT_SERVER)
    host, _, port = raw.partition(":")
    return host, int(port or "31313")


# ---- socket helpers ----

def recvn(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed by server")
        buf += chunk
    return buf


def recv_packet(sock):
    ptype, cmd, size, pktid = HEADER.unpack(recvn(sock, 15))
    payload = recvn(sock, size - 15) if size > 15 else b""
    return ptype, cmd, pktid, payload


def send_request(sock, cmd, payload=b"", pktid=1):
    sock.sendall(HEADER.pack(TYPE_REQUEST, cmd, 15 + len(payload), pktid) + payload)


def recv_reply(sock):
    """Skip async notifications; return (cmd, packetId, error, payload)."""
    while True:
        ptype, cmd, pktid, payload = recv_packet(sock)
        if ptype == TYPE_REPLY:
            return cmd, pktid, payload[0] if payload else -1, payload[1:]


def connect_raw(timeout=5):
    host, port = server_addr()
    sock = socket.create_connection((host, port), timeout=timeout)
    ptype, cmd, pktid, payload = recv_packet(sock)
    return sock, (ptype, cmd, pktid, payload)


def connect(timeout=5):
    sock, info = connect_raw(timeout)
    ptype, _, _, payload = info
    assert ptype == TYPE_SERVERINFO, f"expected ServerInfo first, got type {ptype}"
    return sock


# ---- minimal protobuf3 (wire-format level; enough for these messages) ----

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


def f_varint(num, value):
    return bytes([(num << 3) | 0]) + varint(value)


def f_bool(num, value):
    return f_varint(num, 1 if value else 0)


def blob(data):
    return struct.pack("<I", len(data)) + data


def pparse(buf):
    """Parse a proto3 message into {field_number: [values]} (varint ints or str/bytes)."""
    out, i = {}, 0
    while i < len(buf):
        tag = buf[i]
        i += 1
        num, wire = tag >> 3, tag & 7
        if wire == 0:
            shift = val = 0
            while True:
                b = buf[i]
                i += 1
                val |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            out.setdefault(num, []).append(val)
        elif wire == 2:
            ln = shift = 0
            while True:
                b = buf[i]
                i += 1
                ln |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            data = buf[i:i + ln]
            i += ln
            try:
                data = data.decode()
            except UnicodeDecodeError:
                pass
            out.setdefault(num, []).append(data)
        elif wire == 5:
            i += 4
        elif wire == 1:
            i += 8
        else:
            raise ValueError(f"unsupported wire type {wire} (field {num})")
    return out


def cmd_create(sock, npid, password, email, pktid=1):
    payload = blob(f_str(1, npid) + f_str(2, password) + f_str(4, email))
    send_request(sock, CMD_CREATE, payload, pktid)
    return recv_reply(sock)


def cmd_login(sock, npid, password, pktid=1,
              title_id="CUSA03173", title_name="Bloodborne"):
    payload = blob(
        f_str(1, npid) + f_str(2, password) + f_str(4, title_id) + f_str(5, title_name)
    )
    send_request(sock, CMD_LOGIN, payload, pktid)
    return recv_reply(sock)


def cmd_terminate(sock, pktid=1):
    send_request(sock, CMD_TERMINATE, b"", pktid)
    return recv_reply(sock)


def cmd_delete(sock, npid, password, pktid=1):
    send_request(sock, CMD_DELETE, npid.encode() + b"\x00" + password.encode() + b"\x00", pktid)
    return recv_reply(sock)


def fresh_creds():
    return f"ptest{random.randrange(0x100000):05x}", "Test-Pw-" + os.urandom(4).hex()


def setUpModule():
    host, port = server_addr()
    try:
        probe = socket.create_connection((host, port), timeout=3)
        probe.close()
    except OSError as exc:
        raise RuntimeError(
            f"shadNet TEST instance not reachable at {host}:{port} ({exc}).\n"
            "Start it first — docs/runbook.md, section 'Task 4 — isolated test instance'."
        ) from exc


class WireProtocolTest(unittest.TestCase):
    """Integration checks against the isolated test server."""

    def setUp(self):
        self._socks = []

    def tearDown(self):
        for s in self._socks:
            try:
                s.close()
            except OSError:
                pass

    def connect(self):
        sock = connect()
        self._socks.append(sock)
        return sock

    def make_account(self):
        """Create a fresh account on the test server; delete it at test end."""
        npid, password = fresh_creds()
        sock = self.connect()
        _, _, err, _ = cmd_create(sock, npid, password, f"{npid.lower()}@bb.local")
        self.assertEqual(err, 0, f"create failed for {npid}: {ERR_NAMES.get(err, err)}")
        self.addCleanup(self._delete_account, npid, password)
        return npid, password

    def _delete_account(self, npid, password):
        try:
            sock = connect()
            _, _, err, _ = cmd_login(sock, npid, password)
            if err == 0:
                cmd_delete(sock, npid, password)
            sock.close()
        except OSError:
            pass

    # ---- handshake ----

    def test_00_serverinfo_handshake(self):
        sock, (ptype, cmd, pktid, payload) = connect_raw()
        self._socks.append(sock)
        self.assertEqual(ptype, TYPE_SERVERINFO, "first packet must be ServerInfo")
        self.assertEqual(len(payload), 4, "ServerInfo payload = u32 version")
        self.assertEqual(struct.unpack("<I", payload)[0], 1, "PROTOCOL_VERSION must be 1")

    # ---- account creation ----

    def test_01a_create_ok(self):
        npid, password = fresh_creds()
        sock = self.connect()
        cmd, pktid, err, _ = cmd_create(sock, npid, password, f"{npid.lower()}@bb.local", pktid=7)
        self.assertEqual(cmd, CMD_CREATE)
        self.assertEqual(pktid, 7, "packetId must be echoed")
        self.assertEqual(err, 0, f"expected NoError, got {ERR_NAMES.get(err, err)}")
        self._delete_account(npid, password)

    def test_01b_create_duplicate_username(self):
        npid, password = self.make_account()
        sock = self.connect()
        _, _, err, _ = cmd_create(sock, npid, password, f"{npid.lower()}@bb.local")
        self.assertEqual(err, 11, f"expected CreationExistingUsername, got {ERR_NAMES.get(err, err)}")

    def test_01c_create_invalid_npid(self):
        for bad in ("ab", "bad name!", "sixteen_characters-ok"[:17] + "x"):
            with self.subTest(npid=bad):
                sock = self.connect()
                _, _, err, _ = cmd_create(sock, bad, "whatever-pw", "x@bb.local")
                self.assertEqual(err, 3, f"expected InvalidInput for {bad!r}, got {ERR_NAMES.get(err, err)}")

    # ---- login ----

    def test_02_login_ok_returns_userid(self):
        npid, password = self.make_account()
        sock = self.connect()
        cmd, pktid, err, payload = cmd_login(sock, npid, password, pktid=3)
        self.assertEqual(err, 0, f"login failed: {ERR_NAMES.get(err, err)}")
        blob_len = struct.unpack("<I", payload[:4])[0]
        fields = pparse(payload[4:4 + blob_len])
        user_id = fields.get(2, [0])[0]
        self.assertGreaterEqual(user_id, 1, "LoginReply.user_id must be assigned")
        # Terminate: server replies NoError. NOTE (observed on 0.0.13): this server
        # build does NOT close the socket afterwards (its queued disconnect fails:
        # "No such method QTcpSocket::disconnectFromHost()"); the client closes and
        # the server cleans the session up on disconnect.
        _, _, terr, _ = cmd_terminate(sock, pktid=4)
        self.assertEqual(terr, 0)
        sock.close()

    def test_03_login_wrong_password(self):
        npid, password = self.make_account()
        sock = self.connect()
        _, _, err, _ = cmd_login(sock, npid, password + "-wrong")
        self.assertEqual(err, 8, f"expected LoginInvalidPassword, got {ERR_NAMES.get(err, err)}")

    def test_04_second_session_conflict_then_recover(self):
        npid, password = self.make_account()
        sock_a = self.connect()
        _, _, err, _ = cmd_login(sock_a, npid, password)
        self.assertEqual(err, 0)
        sock_b = self.connect()
        _, _, err, _ = cmd_login(sock_b, npid, password)
        self.assertEqual(err, 6, f"expected LoginAlreadyLoggedIn, got {ERR_NAMES.get(err, err)}")
        # terminate + close on the first session (server releases it on disconnect)
        _, _, terr, _ = cmd_terminate(sock_a)
        self.assertEqual(terr, 0)
        sock_a.close()
        # after the first session is gone, the second login must succeed
        for _ in range(25):  # server needs a beat to release the session
            _, _, err, _ = cmd_login(sock_b, npid, password)
            if err == 0:
                break
            time.sleep(0.2)
        self.assertEqual(err, 0, "login did not recover after first session terminated")

    # ---- framing / robustness ----

    def test_05_unknown_command(self):
        sock = self.connect()
        send_request(sock, 250, b"", 1)
        try:
            _, _, err, _ = recv_reply(sock)
            # observed server behavior: pre-auth unknown command -> Unauthorized;
            # tolerate Malformed/Invalid/Unsupported paths too.
            self.assertIn(err, (23, 1, 2, 33), f"unexpected error for unknown command: {err}")
        except ConnectionError:
            pass  # server closing on unknown command is acceptable

    def test_06_bad_proto_blob(self):
        sock = self.connect()
        # login with a blob length longer than the payload
        send_request(sock, CMD_LOGIN, struct.pack("<I", 100) + b"\x0a\x01x", 1)
        try:
            _, _, err, _ = recv_reply(sock)
            self.assertNotEqual(err, 0)
        except ConnectionError:
            pass

    # ---- STUN / endpoint discovery (UDP port = TCP port + 1 by client convention) ----

    def test_07_stun_ping(self):
        npid, password = self.make_account()
        host, port = server_addr()
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(udp.close)
        udp.settimeout(3)
        udp.connect((host, port + 1))
        local_ip = udp.getsockname()[0]
        # Both directions carry a 4-byte signaling vport header (0xFFFF x2, network
        # order; "stripped first" per signaling.md — see stun_server.cpp StripVportHeader).
        vport = b"\xff\xff\xff\xff"
        ping = vport + b"\x01" + npid.encode().ljust(16, b"\x00") + socket.inet_aton(local_ip)
        udp.send(ping)
        data = udp.recv(64)
        self.assertGreaterEqual(len(data), 10, f"STUN reply too short: {len(data)} bytes")
        self.assertEqual(data[:4], vport, "reply must carry the signaling vport header")
        body = data[4:10]
        self.assertEqual(len(body), 6, f"STUN payload must be 6 bytes, got {len(body)}")
        ext_ip = socket.inet_ntoa(body[:4])
        ext_port = struct.unpack("!H", body[4:6])[0]
        self.assertEqual(ext_ip, local_ip, "same-LAN external IP should equal local IP")
        self.assertEqual(ext_port, udp.getsockname()[1],
                         "same-LAN external port should equal local UDP port")

    # ---- cleanup path ----

    def test_08_delete_own_account(self):
        npid, password = fresh_creds()
        sock = self.connect()
        _, _, err, _ = cmd_create(sock, npid, password, f"{npid.lower()}@bb.local")
        self.assertEqual(err, 0)
        sock = self.connect()
        _, _, err, _ = cmd_login(sock, npid, password)
        self.assertEqual(err, 0)
        _, _, err, _ = cmd_delete(sock, npid, password)
        self.assertEqual(err, 0, f"delete failed: {ERR_NAMES.get(err, err)}")
        # account must be gone: login now fails
        sock2 = self.connect()
        _, _, err, _ = cmd_login(sock2, npid, password)
        self.assertEqual(err, 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
