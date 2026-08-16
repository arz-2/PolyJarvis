from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "orchestration" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from protocol_policy import recovery_allowed, select_pressure_ladder  # noqa: E402


def test_configured_pressure_ladder_is_authoritative():
    selected = select_pressure_ladder([-500, 0, 5000], ced_mpa=310)

    assert selected.pressures_atm == (-500, 0, 5000)
    assert selected.reason == "class_protocol"


def test_ced_screens_tension_limit():
    selected = select_pressure_ladder(ced_mpa=310)

    assert selected.pressures_atm == (-600, 0, 3000, 7000, 15000)
    assert selected.reason == "ced_screened"
    assert selected.tension_limit_atm == -600


def test_missing_ced_uses_conservative_probe():
    selected = select_pressure_ladder()

    assert selected.pressures_atm[0] == -200
    assert selected.reason == "conservative_unscreened"


def test_recovery_is_bounded_to_two_attempts():
    assert recovery_allowed(0)
    assert recovery_allowed(1)
    assert not recovery_allowed(2)
