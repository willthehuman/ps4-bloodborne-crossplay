#!/usr/bin/env python3
"""Analyze a klog run capture for the Bloodborne PS4 <-> Linux crossplay effort.

Task 2 of the crossplay recovery plan: stop classifying runs by vibes. A run is
only "bootstrap ok" when the plugin reaches the server; it is only "misroute
confirmed" when the resolver junk-path fires while a socket continuation is on
the stack; it is NEVER "crossplay verified" from these logs alone (that needs
peer/room/gameplay evidence this instrument set does not yet produce).

Inputs: files as written by scripts/capture-klog.py (raw console klog stream).
Line shapes parsed (see tests/fixtures/runs/README.md):
  - client_start marker            [shadNet] client_main.cpp:NN client_start: Initializing shadNet Client
  - bootstrap                      ProbeServer: server ... is reachable / DoConnect: TCP connected
  - login/features                 HandleLoginReply / HandleServerFeaturesReply
  - hook install snapshots (v27)   [Lib_HookDiag] hookdiag[NAME]: target=... stub=... stubsiz=... tramp=... hook=... diagbase=...
                                   hookdiag[NAME]: stub bytes: <hex> / target after patch: <hex> / trampoline bytes: <hex>
  - socket continuation (v27)      sceNetSocket_hook: depth=N result=0x... entry_ret=0x... entry_rsp=0x...
  - resolver junk path             sceNetResolverStartNtoa_hook: raw rid=... caller=... code48=...
                                   sceNetResolverStartNtoa_hook: raw64 rdi=... rsp=... sockdepth=N
  - STUN / matching2 / webapi      HandleStunEcho: STUN echo / GetWorldInfoList / FireEvent: ... err=0x0 / NpHttp: ... -> 200

Exit codes: 0 = complete run, no failures; 2 = failures recorded; 3 = run
incomplete or no client_start marker (round is void for interpretation).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Firmware 9.03 module ranges, transcribed from a captured console module map
# (klog-round19 crash region). Used only for labeling addresses in reports;
# treat as heuristic and update from the current run's own map when present.
MODULE_RANGES: list[tuple[int, int, str]] = [
    (0x400000, 0x5AD4000, "eboot.bin"),
    (0x800000000, 0x800054000, "libkernel.sprx"),
    (0x800090000, 0x8001B8000, "libSceLibcInternal.sprx"),
    (0x8001DC000, 0x8001E8000, "libSceSysmodule.sprx"),
    (0x80027C000, 0x8003CC000, "libSceNet.sprx"),
    (0x8003CC000, 0x8003F0000, "libSceIpmi/Mbus.sprx"),
    (0x8004D8000, 0x8004E0000, "libSceNetCtl.sprx"),
    (0x8004E8000, 0x800528000, "libSceHttp.sprx"),
    (0x800528000, 0x800678000, "libSceSsl2.sprx"),
    (0x800678000, 0x8006BC000, "libSceNpCommon.sprx"),
    (0x8006C4000, 0x800720000, "libSceNpManager.sprx"),
    (0x800720000, 0x800740000, "libSceNpWebApi.sprx"),
    (0x8007DC000, 0x8007F4000, "libSceUserService.sprx"),
]


def label_address(addr_hex: str | None) -> str:
    if not addr_hex:
        return "?"
    try:
        addr = int(addr_hex, 16)
    except ValueError:
        return addr_hex
    for lo, hi, name in MODULE_RANGES:
        if lo <= addr < hi:
            return f"{addr_hex} ({name})"
    return addr_hex


@dataclass
class HookRecord:
    name: str
    target: str | None = None
    stub: str | None = None
    stub_size: int | None = None
    trampoline: str | None = None
    hook: str | None = None
    diagbase: str | None = None
    stub_bytes: str = ""
    target_after: str = ""
    trampoline_bytes: str = ""
    stub_relative_hint: bool = False  # heuristic: e8/e9/eb token in the copied bytes


@dataclass
class SocketResult:
    depth: int
    result: str
    entry_ret: str | None = None
    entry_rsp: str | None = None

    @property
    def is_error(self) -> bool:
        try:
            return (int(self.result, 16) & 0x80000000) != 0
        except ValueError:
            return False


@dataclass
class ResolverJunk:
    fields: dict[str, str] = field(default_factory=dict)
    sock_depth: int | None = None


@dataclass
class RunReport:
    source: str
    found_client_start: bool = False
    bootstrap_ok: bool = False
    probe_line: str | None = None
    tcp_line: str | None = None
    hooks: dict[str, HookRecord] = field(default_factory=dict)
    socket_results: list[SocketResult] = field(default_factory=list)
    resolver_junk: list[ResolverJunk] = field(default_factory=list)
    stun_echoes: int = 0
    webapi_200: int = 0
    matching2_events: int = 0
    world_list_ok: bool = False
    misroute_suspected: bool = False
    misroute_confirmed: bool = False
    crossplay_verified: bool = False
    complete: bool = False
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["socket_results_errors"] = sum(1 for s in self.socket_results if s.is_error)
        return d


RE_HOOK_INSTALL = re.compile(
    r"hookdiag\[([^\]]+)\]: target=(0x[0-9a-fA-F]+) stub=(0x[0-9a-fA-F]+) "
    r"stubsiz=(\d+) tramp=(0x[0-9a-fA-F]+) hook=(0x[0-9a-fA-F]+) diagbase=(0x[0-9a-fA-F]+)"
)
RE_HOOK_STUB_BYTES = re.compile(r"hookdiag\[([^\]]+)\]: stub bytes: ([0-9a-fA-F ]+)")
RE_HOOK_TARGET_AFTER = re.compile(r"hookdiag\[([^\]]+)\]: target after patch: ([0-9a-fA-F ]+)")
RE_HOOK_TRAMP_BYTES = re.compile(r"hookdiag\[([^\]]+)\]: trampoline bytes: ([0-9a-fA-F ]+)")
RE_SOCKET_RESULT = re.compile(
    r"sceNetSocket_hook: depth=(\d+) result=(0x[0-9a-fA-F]+) "
    r"entry_ret=(0x[0-9a-fA-F]+) entry_rsp=(0x[0-9a-fA-F]+)"
)
RE_JUNK_RAW = re.compile(
    r"sceNetResolverStartNtoa_hook: raw rid=(0x[0-9a-fA-F]+) hostname=(0x[0-9a-fA-F]+) "
    r"addr=(0x[0-9a-fA-F]+) timeout=(0x[0-9a-fA-F]+) retry=(0x[0-9a-fA-F]+) "
    r"flags=(0x[0-9a-fA-F]+) caller=(0x[0-9a-fA-F]+) code48=([0-9a-fA-F]*)"
)
RE_JUNK_RAW64 = re.compile(
    r"sceNetResolverStartNtoa_hook: raw64 rdi=(0x[0-9a-fA-F]+) rsi=(0x[0-9a-fA-F]+) "
    r"rdx=(0x[0-9a-fA-F]+) rcx=(0x[0-9a-fA-F]+) r8=(0x[0-9a-fA-F]+) r9=(0x[0-9a-fA-F]+) "
    r"rsp=(0x[0-9a-fA-F]+) rbp=(0x[0-9a-fA-F]+) rip=(0x[0-9a-fA-F]+) sockdepth=(\d+)"
)


def _stub_relative_hint(stub_hex: str, stub_size: int | None) -> bool:
    """Heuristic: does the copied prologue contain a likely relative-branch
    opcode at a token boundary? e8/e9/eb tokens can also appear inside
    immediates, so this is only an attention flag, not a verdict."""
    toks = stub_hex.split()
    if stub_size:
        # drop the appended FF25 jump (14 bytes) if present
        if len(toks) >= 14 and toks[-14:-12] == ["ff", "25"]:
            toks = toks[:-14]
    return any(t in ("e8", "e9", "eb") for t in toks)


def report_from_lines(source: str, lines: list[str]) -> RunReport:
    r = RunReport(source=source)
    for line in lines:
        if "client_start: Initializing shadNet Client" in line:
            r.found_client_start = True
            continue
        if "ProbeServer: server" in line:
            r.probe_line = line.strip()
            if "is reachable" in line:
                pass
            continue
        if "DoConnect: TCP connected" in line:
            r.tcp_line = line.strip()
            continue
        if "HandleStunEcho: STUN echo" in line:
            r.stun_echoes += 1
            continue
        if re.search(r"NpHttp: \w+ .* -> 200", line):
            r.webapi_200 += 1
            continue
        if "FireEvent: callback REQUEST" in line and "err=0x0" in line:
            r.matching2_events += 1
            if "GetWorldInfoList" in line or True:
                pass
            continue
        m = RE_HOOK_INSTALL.search(line)
        if m:
            name, target, stub, size, tramp, hook, diagbase = m.groups()
            rec = r.hooks.setdefault(name, HookRecord(name=name))
            rec.target, rec.stub, rec.stub_size = target, stub, int(size)
            rec.trampoline, rec.hook, rec.diagbase = tramp, hook, diagbase
            continue
        m = RE_HOOK_STUB_BYTES.search(line)
        if m:
            name, hexs = m.groups()
            rec = r.hooks.setdefault(name, HookRecord(name=name))
            rec.stub_bytes = hexs.strip()
            rec.stub_relative_hint = _stub_relative_hint(rec.stub_bytes, rec.stub_size)
            continue
        m = RE_HOOK_TARGET_AFTER.search(line)
        if m:
            name, hexs = m.groups()
            r.hooks.setdefault(name, HookRecord(name=name)).target_after = hexs.strip()
            continue
        m = RE_HOOK_TRAMP_BYTES.search(line)
        if m:
            name, hexs = m.groups()
            r.hooks.setdefault(name, HookRecord(name=name)).trampoline_bytes = hexs.strip()
            continue
        m = RE_SOCKET_RESULT.search(line)
        if m:
            depth, result, ert, ersp = m.groups()
            r.socket_results.append(
                SocketResult(depth=int(depth), result=result, entry_ret=ert, entry_rsp=ersp)
            )
            continue
        m = RE_JUNK_RAW64.search(line)
        if m:
            (rdi, rsi, rdx, rcx, r8, r9, rsp, rbp, rip, depth) = m.groups()
            # Merge with the immediately preceding raw entry (same logical call):
            # the raw64 line follows its raw line and adds full widths + depth.
            if r.resolver_junk and r.resolver_junk[-1].sock_depth is None:
                entry = r.resolver_junk[-1]
                entry.fields.update(
                    {
                        "rdi": rdi, "rsi": rsi, "rdx": rdx, "rcx": rcx, "r8": r8,
                        "r9": r9, "rsp": rsp, "rbp": rbp, "rip": rip,
                    }
                )
                entry.sock_depth = int(depth)
            else:
                r.resolver_junk.append(
                    ResolverJunk(
                        fields={
                            "rdi": rdi, "rsi": rsi, "rdx": rdx, "rcx": rcx, "r8": r8,
                            "r9": r9, "rsp": rsp, "rbp": rbp, "rip": rip,
                        },
                        sock_depth=int(depth),
                    )
                )
            continue
        m = RE_JUNK_RAW.search(line)
        if m:
            keys = ["rid", "hostname", "addr", "timeout", "retry", "flags", "caller", "code48"]
            r.resolver_junk.append(ResolverJunk(fields=dict(zip(keys, m.groups()))))
            continue
        if "GetWorldInfoList" in line:
            r.notes.append("world list request seen")
            continue

    # world-list success: a matching2 FireEvent err=0x0 preceded by GetWorldInfoList
    seen_world_request = any("GetWorldInfoList" in l for l in lines)
    r.world_list_ok = seen_world_request and any(
        "FireEvent: callback REQUEST" in l and "err=0x0" in l for l in lines
    )

    r.bootstrap_ok = bool(r.probe_line) and bool(r.tcp_line)

    # misroute classification
    confirmed = any(j.sock_depth is not None and j.sock_depth > 0 for j in r.resolver_junk)
    any_junk = bool(r.resolver_junk)
    r.misroute_confirmed = confirmed
    r.misroute_suspected = any_junk and not confirmed

    # completeness: init reached AND the run got past bootstrap attempt
    r.complete = r.found_client_start and bool(r.probe_line)

    # failures
    if not r.found_client_start:
        r.failures.append("no_client_start")
    if not r.complete:
        r.failures.append("incomplete_capture")
    if r.complete and not r.bootstrap_ok:
        r.failures.append("bootstrap_failed")
    if confirmed:
        r.failures.append("hook_misroute")
        r.failures.append("resolver_junk_call")
    elif any_junk:
        r.failures.append("resolver_junk_call")
    if any(s.is_error for s in r.socket_results):
        r.failures.append("socket_continuation_error")

    r.notes.append(
        "crossplay_verified requires peer/room/gameplay markers: not yet instrumented; "
        "always False for capture-only analysis"
    )
    return r


def analyze(path: Path) -> RunReport:
    text = path.read_text(errors="replace")
    return report_from_lines(str(path), text.splitlines())


def format_report(r: RunReport) -> str:
    out: list[str] = []
    out.append(f"== run report: {r.source}")
    out.append(f"client_start: {'yes' if r.found_client_start else 'NO'}")
    out.append(
        f"bootstrap:    {'ok' if r.bootstrap_ok else 'not ok'}"
        + (f"  [{r.probe_line.split('] ', 1)[-1][:90]}]" if r.probe_line else "")
    )
    out.append(f"complete:     {r.complete}")
    out.append(f"stun echoes:  {r.stun_echoes}   webapi 200s: {r.webapi_200}   world list: {r.world_list_ok}")
    out.append(f"crossplay verified: {r.crossplay_verified}")
    if r.hooks:
        out.append(f"hooks captured: {len(r.hooks)}")
        for name, h in sorted(r.hooks.items()):
            out.append(
                f"  - {name}: target={label_address(h.target)} stub={h.stub} "
                f"size={h.stub_size} reloc_hint={h.stub_relative_hint}"
            )
            if h.stub_bytes:
                out.append(f"      stub bytes: {h.stub_bytes}")
    if r.socket_results:
        out.append(f"socket results: {len(r.socket_results)}")
        for s in r.socket_results:
            flag = "ERROR" if s.is_error else "ok"
            out.append(f"  - depth={s.depth} result={s.result} ({flag}) ret={label_address(s.entry_ret)}")
    if r.resolver_junk:
        out.append(f"resolver junk entries: {len(r.resolver_junk)}")
        for j in r.resolver_junk:
            depth = f" sockdepth={j.sock_depth}" if j.sock_depth is not None else ""
            caller = j.fields.get("caller") or j.fields.get("rip") or "?"
            out.append(f"  - caller/rip={label_address(caller)}{depth}")
        out.append(
            f"  misroute: confirmed={r.misroute_confirmed} suspected={r.misroute_suspected}"
        )
    out.append(f"failures: {', '.join(r.failures) if r.failures else '(none)'}")
    for n in r.notes:
        out.append(f"note: {n}")
    return "\n".join(out)


def run_exit_code(r: RunReport) -> int:
    if not r.found_client_start or not r.complete:
        return 3
    if r.failures:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=Path, help="klog capture file to analyze")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    if not args.run.is_file():
        print(f"ERROR: {args.run} not found", file=sys.stderr)
        return 3
    r = analyze(args.run)
    if args.json:
        print(json.dumps(r.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_report(r))
    return run_exit_code(r)


if __name__ == "__main__":
    sys.exit(main())
