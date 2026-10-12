"""Tests for scripts/analyze-crossplay-run.py (plan Task 2).

Contract from the recovery plan:
  - bootstrap (login/world-list/STUN) is NOT crossplay success
  - a capture gap invalidates a round
  - a socket continuation entering the resolver hook is flagged as hook_misroute
Plus: hook-install snapshot parsing, socket-continuation errors, and the
no-start-marker case.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "runs"

_spec = importlib.util.spec_from_file_location(
    "analyze_crossplay_run", ROOT / "scripts" / "analyze-crossplay-run.py"
)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod  # dataclasses needs the module resolvable by name
_spec.loader.exec_module(mod)


class RunAnalysisTests(unittest.TestCase):
    def analyze_fixture(self, name: str):
        return mod.analyze(FIXTURES / name)

    def test_bootstrap_is_not_crossplay_success(self):
        run = self.analyze_fixture("login_worlds_stun_only.log")
        self.assertTrue(run.bootstrap_ok)
        self.assertTrue(run.complete)
        self.assertFalse(run.crossplay_verified)
        self.assertEqual(run.failures, [])

    def test_trace_gap_invalidates_a_round(self):
        run = self.analyze_fixture("capture_disconnect_during_launch.log")
        self.assertFalse(run.complete)
        self.assertIn("incomplete_capture", run.failures)
        self.assertEqual(mod.run_exit_code(run), 3)

    def test_socket_continuation_entering_resolver_is_flagged(self):
        run = self.analyze_fixture("socket_stub_enters_resolver.log")
        self.assertIn("hook_misroute", run.failures)
        self.assertTrue(run.misroute_confirmed)
        # raw + raw64 lines of one logical call merge into a single entry
        self.assertEqual(len(run.resolver_junk), 1)
        self.assertEqual(run.resolver_junk[0].sock_depth, 1)

    def test_socket_result_error_surfaces(self):
        run = self.analyze_fixture("socket_stub_enters_resolver.log")
        self.assertIn("socket_continuation_error", run.failures)
        self.assertTrue(any(s.is_error for s in run.socket_results))
        self.assertEqual(mod.run_exit_code(run), 2)

    def test_hook_install_snapshot_parsed(self):
        run = self.analyze_fixture("socket_stub_enters_resolver.log")
        self.assertIn("net.sceNetSocket", run.hooks)
        rec = run.hooks["net.sceNetSocket"]
        self.assertEqual(rec.target, "0x8002a1b40")
        self.assertEqual(rec.stub_size, 30)
        self.assertTrue(rec.stub_bytes)
        self.assertIn("net.sceNetResolverStartNtoa", run.hooks)

    def test_no_start_marker(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("[SceShellCore] Libc Heap Status: free 39%\n")
            path = Path(f.name)
        try:
            run = mod.analyze(path)
            self.assertFalse(run.found_client_start)
            self.assertIn("no_client_start", run.failures)
            self.assertEqual(mod.run_exit_code(run), 3)
        finally:
            path.unlink()

    def test_module_labeling_is_heuristic_only(self):
        # libSceNet range from the fw9.03 map
        self.assertIn("libSceNet", mod.label_address("0x8002a1b40"))
        self.assertEqual(mod.label_address("0x1234"), "0x1234")


if __name__ == "__main__":
    unittest.main()
