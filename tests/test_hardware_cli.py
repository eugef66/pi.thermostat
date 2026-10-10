from datetime import datetime, timedelta
import io, json, os, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout, redirect_stderr

from thermostat import cli, control, engine, hardware, logsetup, state as S
from thermostat.config import from_dict

ROOT = os.path.dirname(os.path.dirname(__file__))


def write_cfg(d, **hw):
    h = {"emulate": True, "heat1_pin": 2, "cool_pin": 3, "heat2_pin": 5, "fan_pin": 6}
    h.update(hw)
    path = os.path.join(d, "config.toml")
    lines = ["[hardware]"] + [f"{k} = {str(v).lower() if isinstance(v, bool) else v}"
                              for k, v in h.items()]
    lines += ["[control]", 'timezone = "UTC"']
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def run(d, *argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = cli.main(["-c", os.path.join(d, "config.toml"), *argv])
    return rc, out.getvalue(), err.getvalue()


def set_temp(d, t):
    json.dump({"temp": t, "humidity": 45}, open(os.path.join(d, "data", "emulated_sensor.json"), "w"))


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        write_cfg(self.d)
        os.makedirs(os.path.join(self.d, "data"))
        self.cfg = cli.load(os.path.join(self.d, "config.toml"))

    def test_active_low_levels_and_boot_off(self):
        hw = hardware.open_hardware(self.cfg)
        self.assertEqual(hw.read_relays(), {n: False for n in S.RELAY_NAMES})
        hw.set_relays({"heat1": True})
        self.assertEqual(hw.pins.level(2), 0)          # LOW = energized
        self.assertTrue(hw.read_relays()["heat1"])
        hw.all_off()
        self.assertEqual(hw.pins.level(2), 1)

    def test_active_high_board(self):
        write_cfg(self.d, relay_active_low=False)
        hw = hardware.open_hardware(cli.load(os.path.join(self.d, "config.toml")))
        hw.set_relays({"cool": True})
        self.assertEqual(hw.pins.level(3), 1)

    def test_unconfigured_relay_cannot_be_requested(self):
        write_cfg(self.d)  # then drop the cool pin
        cfg = from_dict({"hardware": {"emulate": True, "heat1_pin": 2}},
                        base_dir=self.d)
        hw = hardware.open_hardware(cfg)
        with self.assertRaises(ValueError):
            hw.set_relays({"cool": True})


class CliTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        write_cfg(self.d)
        os.makedirs(os.path.join(self.d, "data"))

    def pins(self):
        return json.load(open(os.path.join(self.d, "data", "emulated_pins.json")))

    def test_set_and_proc_drive_heat_across_processes(self):
        set_temp(self.d, 66)
        self.assertEqual(run(self.d, "set", "--mode", "heat", "--temp", "70")[0], 0)
        rc, out, _ = run(self.d, "proc")             # first cron run: reads 66, heat starts
        self.assertEqual(rc, 0)
        self.assertEqual(self.pins()["2"], 0)         # W1 energized
        self.assertEqual(self.pins()["3"], 1)         # cool off
        rc, out, _ = run(self.d, "get")
        self.assertIn("Relays on   : heat1", out)
        self.assertIn("HEAT  target 70", out)

    def test_sensor_failure_via_real_flow(self):
        # emulator never fails, so inject failures through the driver wrapper
        set_temp(self.d, 66)
        run(self.d, "set", "--mode", "heat", "--temp", "70"); run(self.d, "proc")
        cfg = cli.load(os.path.join(self.d, "config.toml"))
        hw = hardware.open_hardware(cfg)
        store = S.StateStore(cfg.paths.state_file, cfg.paths.lock_file)
        log = logsetup.setup(cfg.paths.log_file)
        for _ in range(5):
            engine.run_cycle(cfg, store, hw, log, samples=[None] * 3, humidity=[None] * 3)
        self.assertFalse(any(hw.read_relays().values()))
        self.assertIn("FAULT sensor", open(cfg.paths.log_file).read())

    def test_set_validation_exit_code(self):
        rc, _, err = run(self.d, "set", "--mode", "heat", "--temp", "99")
        self.assertEqual(rc, 2)
        self.assertIn("between", err)

    def test_set_does_not_read_sensor_and_off_is_immediate(self):
        set_temp(self.d, 60)
        run(self.d, "set", "--mode", "heat", "--temp", "70"); run(self.d, "proc")
        self.assertEqual(self.pins()["2"], 0)
        run(self.d, "set", "--mode", "off")
        self.assertEqual(self.pins()["2"], 1)

    def test_crash_in_cycle_drives_everything_off(self):
        cfg = cli.load(os.path.join(self.d, "config.toml"))
        hw = hardware.open_hardware(cfg)
        store = S.StateStore(cfg.paths.state_file, cfg.paths.lock_file)
        log = logsetup.setup(cfg.paths.log_file)
        hw.set_relays({"heat1": True})
        orig = control.cycle
        control.cycle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(RuntimeError):
                engine.run_cycle(cfg, store, hw, log, samples=[70] * 3, humidity=[40] * 3)
        finally:
            control.cycle = orig
        self.assertFalse(any(hw.read_relays().values()))

    def test_init_and_pending_cancel(self):
        run(self.d, "set", "--mode", "heat", "--temp", "70", "--start", (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"))
        self.assertIn("Pending", run(self.d, "get")[1])
        run(self.d, "cancel-pending")
        self.assertNotIn("Pending", run(self.d, "get")[1])
        self.assertEqual(run(self.d, "init")[0], 0)

    def test_test_relays_refuses_when_active(self):
        set_temp(self.d, 60)
        run(self.d, "set", "--mode", "heat", "--temp", "70"); run(self.d, "proc")
        rc, _, err = run(self.d, "test-relays")
        self.assertEqual(rc, 1)
        self.assertIn("Refusing", err)

    def test_closed_pipe_is_not_an_error(self):
        orig = cli.print_status
        cli.print_status = lambda *a, **k: (_ for _ in ()).throw(BrokenPipeError())
        try:
            self.assertEqual(run(self.d, "get")[0], 0)
        finally:
            cli.print_status = orig

    def test_bad_config_exit_code(self):
        open(os.path.join(self.d, "config.toml"), "w").write("[hardware]\nbogus = 1\n")
        self.assertEqual(run(self.d, "get")[0], 3)

    def test_module_entrypoint(self):
        r = subprocess.run([sys.executable, "-m", "thermostat", "-c",
                            os.path.join(self.d, "config.toml"), "get"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class EmulatorHelperTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        write_cfg(self.d)
        os.makedirs(os.path.join(self.d, "data"))

    def test_emu_temp_and_dev_loop_drive_relays(self):
        self.assertEqual(run(self.d, "emu-temp", "66", "--humidity", "50")[0], 0)
        run(self.d, "set", "--mode", "heat", "--temp", "70")
        rc, out, _ = run(self.d, "dev-loop", "--interval", "0.01", "--count", "3")
        self.assertEqual(rc, 0)
        self.assertEqual(len(out.strip().splitlines()), 4)           # banner + 3 passes
        self.assertIn("66.0F", out)
        self.assertIn("relays: heat1, heat2", out)
        rc, out, _ = run(self.d, "emu-pins")
        self.assertRegex(out, r"W1 heat stage 1\s+GPIO 2\s+level 0\s+ON")
        self.assertRegex(out, r"G fan\s+GPIO 6\s+level 1\s+off")

    def test_emu_temp_fail_reaches_fail_safe(self):
        run(self.d, "emu-temp", "66")
        run(self.d, "set", "--mode", "heat", "--temp", "70")
        run(self.d, "dev-loop", "--interval", "0.01", "--count", "1")
        run(self.d, "emu-temp", "--fail")
        rc, out, _ = run(self.d, "dev-loop", "--interval", "0.01", "--count", "5")
        self.assertIn("FAULT: sensor", out)
        self.assertIn("relays: none", out.strip().splitlines()[-1])
        run(self.d, "emu-temp", "66")                                   # sensor "reconnected"
        rc, out, _ = run(self.d, "dev-loop", "--interval", "0.01", "--count", "1")
        self.assertNotIn("FAULT", out)

    def test_emu_temp_arguments(self):
        self.assertEqual(run(self.d, "emu-temp")[0], 2)

    def test_emulator_commands_refuse_on_real_hardware_config(self):
        write_cfg(self.d, emulate=False)
        for cmd in (["emu-temp", "70"], ["emu-pins"], ["dev-loop", "--count", "1"]):
            rc, _, err = run(self.d, *cmd)
            self.assertEqual(rc, 2, cmd)
            self.assertIn("emulate = true", err)


class CachedCycleTests(unittest.TestCase):
    def test_cached_cycle_does_not_refresh_deadman(self):
        from tests.helpers import Sim
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10); s.jump(60, 1)
        before = s.st["last_proc_at"]
        res = control.cycle(s.cfg, s.st, None, None,
                            {n: s.st["relays"][n]["on"] for n in S.RELAY_NAMES}, s.now + 30)
        self.assertEqual(s.st["last_proc_at"], before)
        self.assertTrue(res.relays["heat1"])           # cached reading still drives it

    def test_stale_cache_holds(self):
        from tests.helpers import Sim
        s = Sim(mode="HEAT", target=70)
        s.run(70, 10); s.jump(60, 1)
        res = control.cycle(s.cfg, s.st, None, None,
                            {n: s.st["relays"][n]["on"] for n in S.RELAY_NAMES}, s.now + 600)
        self.assertTrue(res.relays["heat1"])           # held, not dropped, not decided


class LogTests(unittest.TestCase):
    def test_rotation(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "t.log")
        log = logsetup.setup(path, max_bytes=300, backups=3)
        for i in range(60):
            log.info("event number %d", i)
        names = sorted(os.listdir(d))
        self.assertIn("t.log.1", names)
        self.assertNotIn("t.log.4", names)
        self.assertLessEqual(os.path.getsize(path), 300)


if __name__ == "__main__":
    unittest.main()
