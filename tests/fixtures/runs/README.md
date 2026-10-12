# Run fixtures

Input fixtures for `scripts/analyze-crossplay-run.py` (tests: `tests/test_run_analysis.py`).

- `login_worlds_stun_only.log` — **real slice** of `private/logs/klog-round22.log`
  (v26, 2026-10-12), sanitized: credentials/NPIDs/IPs replaced. Contains
  init → login → server features → STUN echo → world-list round trip.
  Contract: `bootstrap_ok=True`, `crossplay_verified=False`, no recorded failures.
  The junk-resolver block is intentionally excluded (see next file).
- `capture_disconnect_during_launch.log` — **synthetic, format-accurate**:
  shell launch lines + plugin init start, then the capture ends (klog client
  disconnected mid-launch). Contract: `complete=False`, `incomplete_capture`.
- `socket_stub_enters_resolver.log` — **synthetic, format-accurate** (v27 log
  shape): hook-install snapshots for the two net hooks, a P2P socket creation
  whose continuation returns `0x80410116`, and a resolver junk-path entry with
  `raw64 … sockdepth=1` (i.e. the resolver hook entered from inside the socket
  continuation). Contract: `hook_misroute` + `socket_continuation_error`
  failures, both hook records parsed.

These are **not** evidence of any run; real evidence lives in `private/logs/`
(untracked). Keep fixtures small and format-faithful when updating.
