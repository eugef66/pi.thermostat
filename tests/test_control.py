import unittest

from thermostat import control as K
from tests.helpers import Sim, make_cfg, T0


class HeatTests(unittest.TestCase):
    def test_heat_on_below_deadband_and_off_at_target(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70)                       # first run boots
        s.run(69.5, 3)
        self.assertFalse(s.on("heat1"))  # inside deadband
        w = s.run(69, 3)
        self.assertTrue(w["heat1"])
        s.run(69.5, 5)
        self.assertTrue(s.on("heat1"))   # keeps heating until target
        w = s.run(70, 1)
        self.assertFalse(w["heat1"])

    def test_heat_minimum_run_time_defers_off(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10)
        s.run(68, 1)
        self.assertTrue(s.on("heat1"))
        s.run(71, 1)                    # only 1 min on, min is 2
        self.assertTrue(s.on("heat1"))
        s.run(71, 1)
        self.assertFalse(s.on("heat1"))

    def test_heat_minimum_off_time_blocks_restart(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10)
        s.run(68, 1); s.run(71, 3)
        self.assertFalse(s.on("heat1"))
        s.run(68, 1)                    # off for 1 min, min 2
        self.assertFalse(s.on("heat1"))
        s.run(68, 1)
        self.assertTrue(s.on("heat1"))

    def test_off_mode_is_immediate_even_inside_min_run(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10); s.run(65, 1)
        self.assertTrue(s.on("heat1"))
        s.st["mode"] = "OFF"
        s.run(65, 0.5)
        self.assertFalse(s.on("heat1"))
        self.assertFalse(s.on("heat2"))


class Stage2Tests(unittest.TestCase):
    def test_stage2_hysteresis_and_w1_held(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10)
        s.run(66, 1)                   # deficit 4 > 3
        self.assertTrue(s.on("heat1") and s.on("heat2"))
        s.run(67.5, 1)                 # deficit 2.5: between release and trigger
        self.assertTrue(s.on("heat2"))
        s.run(68.5, 1)                 # deficit 1.5 <= 2
        self.assertFalse(s.on("heat2"))
        self.assertTrue(s.on("heat1"))
        s.run(67.5, 1)                 # must not re-trigger at 2.5
        self.assertFalse(s.on("heat2"))

    def test_stage2_off_when_w1_stops(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10); s.run(66, 1)
        s.st["mode"] = "OFF"
        s.run(66, 1)
        self.assertFalse(s.on("heat1") or s.on("heat2"))

    def test_single_stage_install(self):
        s = Sim(cfg=make_cfg(heat2=False), mode="HEAT", target=70)
        s.run(70, 10); s.jump(60, 1)
        self.assertTrue(s.on("heat1"))
        self.assertFalse(s.on("heat2"))


class CoolAndAutoTests(unittest.TestCase):
    def test_cool_on_off_with_fan(self):
        s = Sim(mode="COOL", target=72)
        s.run(72, 10)
        s.run(72.5, 6); self.assertFalse(s.on("cool"))
        s.run(73, 1)
        self.assertTrue(s.on("cool") and s.on("fan"))
        s.run(72.5, 5); self.assertTrue(s.on("cool"))
        s.run(72, 1)
        self.assertFalse(s.on("cool") or s.on("fan"))

    def test_compressor_protection(self):
        s = Sim(mode="COOL", target=72)
        s.run(72, 10); s.run(74, 1)
        self.assertTrue(s.on("cool"))
        s.run(70, 1)                       # only 1 min on, min 3
        self.assertTrue(s.on("cool"))
        s.run(70, 2)
        self.assertFalse(s.on("cool"))
        s.run(74, 3); self.assertFalse(s.on("cool"))   # off 3 of 5 min
        s.run(74, 2); self.assertTrue(s.on("cool"))

    def test_auto_gap(self):
        s = Sim(mode="AUTO", target=70)
        s.run(70, 10)
        s.run(68.5, 5); self.assertFalse(s.on("heat1"))   # needs <= 68
        s.run(68, 1);   self.assertTrue(s.on("heat1"))
        s.run(68.5, 5); self.assertTrue(s.on("heat1"))    # off at >= 69
        s.run(69, 1);   self.assertFalse(s.on("heat1"))
        s.run(71.5, 6); self.assertFalse(s.on("cool"))    # needs >= 72
        s.run(72, 1);   self.assertTrue(s.on("cool"))

    def test_changeover_lockout(self):
        s = Sim(mode="AUTO", target=70)
        s.run(70, 10); s.jump(60, 1)
        self.assertTrue(s.on("heat1"))
        s.jump(75, 3)                         # heat off now; cool wants on
        self.assertFalse(s.on("heat1"))
        self.assertFalse(s.on("cool"))       # changeover 5 min
        s.run(75, 4); self.assertFalse(s.on("cool"))
        s.run(75, 2); self.assertTrue(s.on("cool"))

    def test_never_both(self):
        s = Sim(mode="AUTO", target=70)
        s.run(70, 10)
        import random
        random.seed(1)
        for _ in range(400):
            s.run(random.choice([55, 62, 68, 70, 72, 78, 90]) , random.choice([1, 1, 2]))
            self.assertFalse((s.on("heat1") or s.on("heat2")) and s.on("cool"))


class SensorFailSafe(unittest.TestCase):
    def test_hold_then_fail_safe_then_recover(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10); s.run(66, 1)
        self.assertTrue(s.on("heat1"))
        for _ in range(4):
            s.run(None, 1, samples=[None, None, None])
        self.assertTrue(s.on("heat1"))          # 4 misses: hold
        s.run(None, 1, samples=[None, None, None])
        self.assertFalse(s.on("heat1") or s.on("heat2"))
        self.assertEqual(s.st["fault"]["code"], "sensor")
        s.run(68, 1)
        self.assertIsNone(s.st["fault"])

    def test_median_and_range_filter(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10)
        res = s.run(None, 1, samples=[70.0, 999.0, 71.0])
        self.assertEqual(s.st["reading"]["temp"], 70.5)
        self.assertEqual(s.st["sensor"]["failures"], 0)

    def test_jump_rejected_then_confirmed(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10)
        s.run(85, 1)
        self.assertEqual(s.st["sensor"]["failures"], 1)
        self.assertEqual(s.st["reading"]["temp"], 70.0)
        s.run(85.5, 1)
        self.assertEqual(s.st["sensor"]["failures"], 0)
        self.assertEqual(s.st["reading"]["temp"], 85.5)

    def test_transient_spike_does_not_stick(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10); s.run(95, 1); s.run(70.5, 1)
        self.assertEqual(s.st["reading"]["temp"], 70.5)
        self.assertEqual(s.st["sensor"]["failures"], 0)

    def test_calibration(self):
        s = Sim(cfg=make_cfg(calibration=-2), mode="OFF")
        s.run(72, 1)
        self.assertEqual(s.st["reading"]["temp"], 70.0)


class BootAndConfig(unittest.TestCase):
    def test_reboot_restarts_timers(self):
        s = Sim(mode="COOL", target=72)
        s.run(72, 10); s.run(75, 1)
        self.assertTrue(s.on("cool"))
        # power loss: pins come up off, state file still says on
        res = K.cycle(s.cfg, s.st, [75] * 3, [40] * 3, {}, s.now + 600)
        self.assertFalse(res.relays["cool"])      # compressor restart delayed
        self.assertTrue(any("timer restarted" in e for e in res.events))

    def test_heat_only_install(self):
        cfg = make_cfg(cool=False, fan=False)
        self.assertEqual(cfg.modes, ("OFF", "HEAT"))
        self.assertFalse(cfg.capabilities()["cool"])
        s = Sim(cfg=cfg, mode="HEAT", target=70)
        s.run(70, 10); s.jump(60, 1)
        self.assertTrue(s.on("heat1"))

    def test_fan_only_mode(self):
        s = Sim(mode="FAN")
        s.run(70, 1)
        self.assertTrue(s.on("fan"))
        self.assertFalse(s.on("heat1") or s.on("cool"))

    def test_fan_mode_works_without_a_reading(self):
        s = Sim(mode="FAN")
        res = K.cycle(s.cfg, s.st, None, None, {}, s.now)     # no reading ever taken
        self.assertTrue(res.relays["fan"])

    def test_off_works_without_a_reading(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10); s.jump(60, 1)
        s.st["mode"] = "OFF"
        res = K.cycle(s.cfg, s.st, None, None, {"heat1": True}, s.now + 1)
        self.assertFalse(any(res.relays.values()))

    def test_no_fan_pin_means_no_fan_mode(self):
        cfg = make_cfg(fan=False)
        self.assertNotIn("FAN", cfg.modes)

    def test_removed_mode_falls_back_to_off(self):
        s = Sim(cfg=make_cfg(cool=False), mode="COOL")
        res = s.run(80, 1)
        self.assertEqual(s.st["mode"], "OFF")

    def test_deadman(self):
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10); s.jump(60, 1)
        self.assertFalse(K.deadman_expired(s.cfg, s.st, s.now + 299))
        self.assertTrue(K.deadman_expired(s.cfg, s.st, s.now + 301))
        ev = K.force_off(s.st, s.now + 301, "deadman")
        self.assertTrue(ev)
        self.assertFalse(K.deadman_expired(s.cfg, s.st, s.now + 900))


class SetAndPending(unittest.TestCase):
    def setUp(self):
        self.s = Sim(cfg=make_cfg(timezone="America/New_York"))

    def test_validation(self):
        v = lambda **k: K.validate_set(self.s.cfg, self.s.st, k.get("mode", "HEAT"),
                                       k.get("target"), k.get("start_at"), T0)
        for bad in (dict(mode="BOGUS"), dict(target=40), dict(target=99),
                    dict(target="70"), dict(target=True),
                    dict(start_at="nonsense"), dict(start_at="2001-01-01T00:00:00+00:00")):
            with self.assertRaises(K.ValidationError, msg=str(bad)):
                v(**bad)
        self.assertEqual(v(target=70)["target"], 70)
        with self.assertRaises(K.ValidationError):
            K.validate_set(make_cfg(cool=False), self.s.st, "COOL", 70, None, T0)

    def test_immediate_and_pending_flow(self):
        s = self.s
        req = K.validate_set(s.cfg, s.st, "HEAT", 70, None, s.now)
        K.apply_set(s.st, req)
        self.assertEqual((s.st["mode"], s.st["target"]), ("HEAT", 70))
        start = "2023-11-15T01:00:00Z"            # T0 is 2023-11-14 22:13 UTC
        req = K.validate_set(s.cfg, s.st, "COOL", 74, start, s.now)
        K.apply_set(s.st, req)
        self.assertEqual(s.st["mode"], "HEAT")    # unchanged until due
        self.assertEqual(s.st["pending"]["mode"], "COOL")
        self.assertIn("-05:00", s.st["pending"]["start_at"])
        s.run(72, 1)
        self.assertEqual(s.st["mode"], "HEAT")
        s.run(72, 60 * 3)
        self.assertEqual(s.st["mode"], "COOL")
        self.assertIsNone(s.st["pending"])

    def test_cancel_and_replace(self):
        s = self.s
        for m in ("COOL", "HEAT"):
            K.apply_set(s.st, K.validate_set(s.cfg, s.st, m, 70, "2023-11-15T01:00:00Z", s.now))
        self.assertEqual(s.st["pending"]["mode"], "HEAT")
        K.cancel_pending(s.st)
        self.assertIsNone(s.st["pending"])

    def test_naive_time_uses_configured_zone_and_dst(self):
        dt = K.parse_time("2023-11-05T01:30:00", "America/New_York")
        self.assertEqual(dt.utcoffset().total_seconds(), -4 * 3600)  # still EDT
        dt = K.parse_time("2023-11-06T01:30:00", "America/New_York")
        self.assertEqual(dt.utcoffset().total_seconds(), -5 * 3600)

    def test_target_clamped_if_limits_tighten(self):
        s = Sim(cfg=make_cfg(setpoint_max=75), mode="HEAT", target=80)
        s.run(70, 1)
        self.assertEqual(s.st["target"], 75)


if __name__ == "__main__":
    unittest.main()
