import json, os, tempfile, threading, time, unittest

from thermostat import config as C, state as S


class StateTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.store = S.StateStore(os.path.join(self.d, "s.json"),
                                  os.path.join(self.d, "s.lock"), lock_timeout=0.3)

    def test_roundtrip(self):
        with self.store.locked() as st:
            st["mode"] = "HEAT"
        with self.store.locked() as st:
            self.assertEqual(st["mode"], "HEAT")

    def test_exception_discards_changes(self):
        with self.assertRaises(RuntimeError):
            with self.store.locked() as st:
                st["mode"] = "HEAT"
                raise RuntimeError
        with self.store.locked() as st:
            self.assertEqual(st["mode"], "OFF")

    def test_corrupt_file_recovers_safely(self):
        with open(self.store.path, "w") as f:
            f.write("{not json")
        with self.store.locked() as st:
            self.assertEqual(st["mode"], "OFF")
            self.assertTrue(st["recovered_from_corruption"])
        self.assertTrue(any(".corrupt-" in n for n in os.listdir(self.d)))

    def test_legacy_db_migrates(self):
        with open(self.store.path, "w") as f:
            json.dump({"mode": "HEAT", "target_temperature": 68,
                       "schedule": "2021-02-12 13:00"}, f)
        with self.store.locked() as st:
            self.assertEqual((st["mode"], st["target"]), ("HEAT", 68.0))
            self.assertIsNone(st["pending"])

    def test_lock_is_exclusive(self):
        got = []
        with self.store.locked():
            def other():
                try:
                    with self.store.locked():
                        got.append("entered")
                except S.LockTimeout:
                    got.append("timeout")
            t = threading.Thread(target=other); t.start(); t.join()
        self.assertEqual(got, ["timeout"])


class ConfigTests(unittest.TestCase):
    def test_example_loads(self):
        cfg = C.load(os.path.join(os.path.dirname(__file__), "..", "config.example.toml"))
        self.assertEqual(cfg.modes, ("OFF", "HEAT", "COOL", "AUTO", "FAN"))
        self.assertTrue(cfg.has_heat2)
        self.assertTrue(os.path.isabs(cfg.paths.state_file))

    def test_rejects_bad_values(self):
        bad = [
            {"hardware": {"heat1_pin": 2, "cool_pin": 2}},
            {"hardware": {"heat1_pin": 40}},
            {"hardware": {"bogus": 1}},
            {"control": {"setpoint_min": 90}},
            {"hardware": {"cool_pin": 3}, "control": {"auto_gap": 2}},
            {"control": {"timezone": "Not/AZone"}},
            {"control": {"stage2_off_deficit": 5}},
        ]
        for raw in bad:
            with self.assertRaises(C.ConfigError, msg=str(raw)):
                C.from_dict(raw)

    def test_missing_file(self):
        with self.assertRaises(C.ConfigError):
            C.load("/nonexistent.toml")


if __name__ == "__main__":
    unittest.main()
