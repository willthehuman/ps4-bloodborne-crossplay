#!/usr/bin/env python3
"""Unit tests for the Task 5 deployment tooling (config + plugins.ini logic).

Pure host-side tests — no console access required:
    python3 -m unittest discover -s tests -p 'test_*.py' -v

Covers the plan's Task 5 checklist items that are host-testable:
  * config schema mirrors the plugin structs (src/shadnet/config.h)
  * absent-user / disabled / multi-user semantics of generated configs
  * generated configs never carry public default endpoints
  * plugins.ini merge/remove is narrow, idempotent and preserves other stanzas
  * validation rejects malformed inputs (the tooling can never deploy them)
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

WS = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, WS / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = _load("deploy_plugin", "scripts/deploy-plugin.py")
rb = _load("rollback_plugin", "scripts/rollback-plugin.py")

PRX = "/data/GoldHEN/plugins/shadNet-PS4.prx"
TITLE = "CUSA03173"


class BuildConfigTest(unittest.TestCase):
    def test_schema_matches_plugin_structs(self):
        cfg = dp.build_config("289813409", "crowps4", "pw", "192.168.50.233:31313",
                              "http://192.168.50.233:31315")
        self.assertEqual(set(cfg["289813409"]),
                         {"shadnet_appear_offline", "shadnet_enabled",
                          "shadnet_npid", "shadnet_password"})
        self.assertEqual(set(cfg["Server"]),
                         {"shadnet_enable_upnp", "shadnet_server",
                          "shadnet_webapi_server", "shadnet_signaling_info"})

    def test_disabled_by_default(self):
        cfg = dp.build_config("289813409", "crowps4", "pw", "h:1", "http://h:2")
        self.assertFalse(cfg["289813409"]["shadnet_enabled"])

    def test_enabled_flag_respected(self):
        cfg = dp.build_config("289813409", "crowps4", "pw", "h:1", "http://h:2", enabled=True)
        self.assertTrue(cfg["289813409"]["shadnet_enabled"])

    def test_absent_users_are_not_enabled_implicitly(self):
        # only the explicitly listed user may ever be enabled
        cfg = dp.build_config("289813409", "crowps4", "pw", "h:1", "http://h:2", enabled=True)
        others = [k for k in cfg if k != "Server"]
        self.assertEqual(others, ["289813409"])

    def test_multiple_users(self):
        cfg = dp.build_config(
            "289813409", "crowps4", "pw", "h:1", "http://h:2", enabled=True,
            extra_users=[{"user_id": "114633a4", "npid": "x", "password": "y"}])
        # second user defaults to disabled
        self.assertFalse(cfg["114633a4"]["shadnet_enabled"])

    def test_no_public_endpoint_leaks(self):
        cfg = dp.build_config("289813409", "crowps4", "pw",
                              "192.168.50.233:31313", "http://192.168.50.233:31315",
                              enabled=True)
        text = dp.config_to_json(cfg)
        self.assertNotIn("shadps4.net", text)
        json.loads(text)  # must be valid JSON

    def test_upnp_disabled(self):
        cfg = dp.build_config("289813409", "crowps4", "pw", "h:1", "http://h:2")
        self.assertFalse(cfg["Server"]["shadnet_enable_upnp"])


class ValidationTest(unittest.TestCase):
    def test_user_id_ok(self):
        self.assertEqual(dp.validate_user_id("289813409"), "289813409")

    def test_user_id_rejects(self):
        for bad in ("0", "-1", "0x114633a1", "abc", "", "1" * 11):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    dp.validate_user_id(bad)

    def test_npid(self):
        self.assertEqual(dp.validate_npid("crowps4"), "crowps4")
        for bad in ("ab", "bad name", "x" * 17, ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    dp.validate_npid(bad)

    def test_hostport(self):
        dp.validate_hostport("192.168.50.233:31313")
        for bad in ("nohost", "h:0", "h:70000", "h:", ":31313", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    dp.validate_hostport(bad)

    def test_webapi(self):
        dp.validate_webapi("http://192.168.50.233:31315")
        for bad in ("ftp://x", "192.168.50.233:31315", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    dp.validate_webapi(bad)


class AccountsFileTest(unittest.TestCase):
    def test_parse_found(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "accounts.env"
            p.write_text("# comment\nSHADNET_TEST_PW_CROWPS4=secret-pw\nOTHER=1\n")
            self.assertEqual(dp.parse_accounts_file(p, "crowps4"), "secret-pw")

    def test_parse_missing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "accounts.env"
            p.write_text("OTHER=1\n")
            self.assertIsNone(dp.parse_accounts_file(p, "crowps4"))
        self.assertIsNone(dp.parse_accounts_file("/nonexistent/file", "crowps4"))


class MergeIniTest(unittest.TestCase):
    def test_creates_section(self):
        new, changed = dp.merge_plugins_ini("", TITLE, PRX)
        self.assertTrue(changed)
        self.assertEqual(new, f"[{TITLE}]\n{PRX}\n")

    def test_preserves_other_sections_and_order(self):
        src = "[CUSA00004]\n/foo/other.prx\n"
        new, changed = dp.merge_plugins_ini(src, TITLE, PRX)
        self.assertTrue(changed)
        self.assertTrue(new.startswith("[CUSA00004]\n/foo/other.prx\n"))
        self.assertIn(f"[{TITLE}]\n{PRX}\n", new)

    def test_idempotent(self):
        once, _ = dp.merge_plugins_ini("", TITLE, PRX)
        twice, changed = dp.merge_plugins_ini(once, TITLE, PRX)
        self.assertFalse(changed)
        self.assertEqual(once, twice)

    def test_replaces_stale_path_same_filename(self):
        src = f"[{TITLE}]\n/mnt/usb0/shadNet-PS4.prx\n"
        new, _ = dp.merge_plugins_ini(src, TITLE, PRX)
        self.assertIn(PRX, new)
        self.assertNotIn("/mnt/usb0/shadNet-PS4.prx", new)

    def test_inserts_into_existing_empty_section(self):
        src = f"[{TITLE}]\n\n[CUSA00004]\n/x.prx\n"
        new, _ = dp.merge_plugins_ini(src, TITLE, PRX)
        idx_title = new.index(f"[{TITLE}]")
        idx_other = new.index("[CUSA00004]")
        self.assertLess(idx_title, new.index(PRX))
        self.assertLess(new.index(PRX), idx_other)

    def test_comment_lines_preserved(self):
        src = "; my plugins\n[CUSA00004]\n/x.prx\n"
        new, _ = dp.merge_plugins_ini(src, TITLE, PRX)
        self.assertTrue(new.startswith("; my plugins\n"))


class RemoveIniTest(unittest.TestCase):
    def test_removes_and_drops_empty_stanza(self):
        src = f"[{TITLE}]\n{PRX}\n"
        new, changed = dp.remove_prx_from_ini(src, TITLE)
        self.assertTrue(changed)
        self.assertNotIn("shadNet-PS4", new)
        self.assertNotIn(f"[{TITLE}]", new)

    def test_keeps_other_entries_in_stanza(self):
        src = f"[{TITLE}]\n{PRX}\n/foo/keep.prx\n"
        new, changed = dp.remove_prx_from_ini(src, TITLE)
        self.assertTrue(changed)
        self.assertIn(f"[{TITLE}]", new)
        self.assertIn("/foo/keep.prx", new)
        self.assertNotIn("shadNet-PS4", new)

    def test_keeps_other_stanzas(self):
        src = f"[CUSA00004]\n/a.prx\n[{TITLE}]\n{PRX}\n"
        new, _ = dp.remove_prx_from_ini(src, TITLE)
        self.assertIn("[CUSA00004]\n/a.prx\n", new)

    def test_noop_when_absent(self):
        src = "[CUSA00004]\n/a.prx\n"
        new, changed = dp.remove_prx_from_ini(src, TITLE)
        self.assertFalse(changed)
        self.assertEqual(new, src)


class RollbackModuleTest(unittest.TestCase):
    def test_module_loads_and_reuses_helper(self):
        self.assertTrue(hasattr(rb, "main"))
        # rollback uses the same removal helper semantics
        src = f"[{TITLE}]\n{PRX}\n"
        new, changed = dp.remove_prx_from_ini(src, TITLE)
        self.assertTrue(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
