from thermostat import config as C, control as K, state as S

T0 = 1_700_000_000.0


def make_cfg(cool=True, fan=True, heat2=True, **control):
    hw = {"heat1_pin": 2}
    if cool: hw["cool_pin"] = 3
    if heat2: hw["heat2_pin"] = 5
    if fan: hw["fan_pin"] = 6
    return C.from_dict({"hardware": hw, "control": control})


class Sim:
    """Runs cycles against an in-memory state, like the cron job would."""

    def __init__(self, cfg=None, mode="OFF", target=70.0):
        self.cfg = cfg or make_cfg()
        self.st = S.new_state(70.0)
        self.st["mode"], self.st["target"] = mode, target
        self.now = T0
        self.events = []

    def run(self, temp, minutes=1.0, samples=None):
        """Advance time, then run one cycle with the relays as last commanded."""
        self.now += minutes * 60
        actual = {n: self.st["relays"][n]["on"] for n in S.RELAY_NAMES}
        s = samples if samples is not None else [temp, temp, temp]
        res = K.cycle(self.cfg, self.st, s, [40, 40, 40], actual, self.now)
        self.events += res.events
        return res.relays

    def on(self, name):
        return self.st["relays"][name]["on"]

    def jump(self, temp, minutes=1.0):
        """A big temperature change: first read is held for confirmation."""
        self.run(temp, minutes)
        return self.run(temp, 0.01)
