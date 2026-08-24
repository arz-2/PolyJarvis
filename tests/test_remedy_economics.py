"""Regression guard for remedy_economics.py -- the rung-pricing check.

Locks in the five verdicts calibrated on the 2026-08-11 runs, where every residual was
bias rather than variance and each stopping call had to be made by a human because the
ladder priced nothing:

  PMMA1 rung 2   -- the ~60/40 bet the human refused. The script must independently
                    reproduce the recovery-agent's own hand arithmetic (break-even
                    83.6 K/ns, ~1.3x margin, physical target ~2 orders out of reach).
  PMMA1 rung 1   -- one point determines no slope; the first rung is an information
                    purchase and must be authorised.
  PEEK1          -- Class A finite_size, the one rung that WAS worth paying. The rule
                    that stops PMMA1 must never suppress this one.
  cis-PBD1       -- one Tg rate measured; buy the multirate slope, do not stop.
  Class B + bias -- a Class B gate whose gap is bias has been mis-classified; EXTEND is
                    the wrong lever no matter how long it runs.

Plus guards for two defects found by testing the flag paths: lever direction was
inferred from --cost-exponent (a +1 exponent silently made current_lever the OLDER rung
and flipped margin 1.33 -> 0.75), and Class C calls missing --target-floor died with a
bare TypeError. Also asserts the script reads its thresholds from decision_policy.json
rather than carrying a second copy.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import remedy_economics  # noqa: E402

POLICY = REPO_ROOT / "orchestration" / "decision_policy.json"
THRESHOLDS = remedy_economics.load_thresholds(POLICY)


def call(**kw):
    args = SimpleNamespace(
        failing_gate="g", gate_class="C", lever="lev", lever_direction="lower",
        history="", next_lever=None, target_floor=None, physical_target=None,
        sem=None, last_rung_hours=None, cost_exponent=-1.0,
    )
    for k, v in kw.items():
        setattr(args, k, v)
    return remedy_economics.decide(args, THRESHOLDS)


# ─── the five calibrated verdicts ──────────────────────────────────────────────

def test_pmma1_rung2_is_a_marginal_bet_and_stops():
    r = call(failing_gate="density_value_binding", gate_class="C",
             lever="cooling_rate_K_per_ns", lever_direction="lower",
             history="250:1.118369,125:1.1257", next_lever=62.5,
             target_floor=1.130, physical_target=1.19, sem=0.0003, last_rung_hours=5.73)
    assert r["verdict"] == "STOP_ANNOTATE"
    assert r["residual_type"] == "bias"
    # reproduces the recovery-agent's own numbers, derived independently
    assert r["break_even_lever"] == pytest.approx(83.2, abs=0.5)
    assert r["margin_factor"] == pytest.approx(1.33, abs=0.02)
    assert r["predicted_at_next_rung"] == pytest.approx(1.133, abs=0.001)
    # and the convergence test: the true value is ~2.6 decades out of reach
    assert r["decades_to_physical_target"] == pytest.approx(2.64, abs=0.05)
    assert r["cost_to_physical_target_hours"] > THRESHOLDS["converged_cost_ceiling_hours"]
    assert "annotation_required" in r


def test_pmma1_rung1_buys_the_slope():
    r = call(gate_class="C", history="250:1.118369", next_lever=125,
             target_floor=1.130, physical_target=1.19, sem=0.0003)
    assert r["verdict"] == "SPEND"
    assert r["spend_limit"] == "one rung"


def test_peek1_class_a_is_always_worth_paying():
    r = call(failing_gate="finite_size", gate_class="A", lever="nchain",
             lever_direction="higher", history="8:0.822", target_floor=1.0)
    assert r["verdict"] == "SPEND_STRUCTURAL"


def test_cispbd1_single_rate_buys_the_multirate_slope():
    r = call(failing_gate="tg_vs_exp", gate_class="C", lever="cooling_rate_K_per_ns",
             lever_direction="lower", history="40:220.2", next_lever=4,
             target_floor=183, physical_target=174, sem=8.9)
    assert r["verdict"] == "SPEND"
    assert r["spend_limit"] == "one rung"


def test_class_b_gate_with_a_bias_gap_is_the_wrong_lever():
    r = call(failing_gate="density_drift", gate_class="B", lever="trajectory_ns",
             lever_direction="higher", cost_exponent=1.0, history="15:1.1257",
             next_lever=20, target_floor=1.130, sem=0.0003)
    assert r["residual_type"] == "bias"
    assert r["verdict"] == "WRONG_LEVER"


def test_class_b_gate_with_a_variance_gap_extends():
    r = call(gate_class="B", lever="trajectory_ns", lever_direction="higher",
             cost_exponent=1.0, history="15:1.1299", next_lever=20,
             target_floor=1.130, sem=0.0003)
    assert r["residual_type"] == "variance"
    assert r["verdict"] == "SPEND"


# ─── D-07: prospective (non-recovery) pricing of a Murnaghan sampling-factor rung ──────────
#
# extract_bulk_modulus_murnaghan.py now emits a real, autocorrelation-corrected per-point
# volume SEM (vol_sem_A3_per_point). This machinery prices whether a SECOND, longer
# mechanical_sampling_factor rung is worth spending BEFORE spending it -- reusing decide()
# as-is (Class C is the only path that reaches the log-linear/margin-factor machinery; Class B
# returns immediately after the residual-type test). mechanical_sampling_factor is
# "lever_direction=higher" (stage_params.py multiplies bm_npt_steps by it) with
# cost_exponent=+1 (linear in wall time, unlike cooling rate's -1). --sem/--physical-target
# are omitted: the metric here IS an SEM, so test 1 would be circular, and no "true SEM"
# target exists to converge toward.

def test_murnaghan_sampling_factor_one_rung_buys_the_slope():
    """Only the sampling_factor=1 rung has run -- one point determines no slope, so the
    verdict must be the same 'buy the slope first' SPEND as cis-PBD1's single Tg rate."""
    r = call(failing_gate="murnaghan_sampling_precision", gate_class="C",
             lever="mechanical_sampling_factor", lever_direction="higher",
             cost_exponent=1.0, history="1:0.20", next_lever=2.0, target_floor=0.14)
    assert r["verdict"] == "SPEND"
    assert r["spend_limit"] == "one rung"


def test_murnaghan_sampling_factor_two_rungs_prices_a_third():
    """sampling_factor=1 and =2 have both run (SEM 0.20 -> 0.16 as n_eff grew) -- enough to
    fit the real log-linear closure and decide whether a sampling_factor=6 rung clears the
    SEM floor with adequate margin."""
    r = call(failing_gate="murnaghan_sampling_precision", gate_class="C",
             lever="mechanical_sampling_factor", lever_direction="higher",
             cost_exponent=1.0, history="1:0.20,2:0.16", next_lever=6.0,
             target_floor=0.14, last_rung_hours=2.0)
    assert r["residual_type"] == "unknown"  # --sem omitted: would be circular for an SEM metric
    assert r["current_lever"] == 2.0  # most recently spent rung
    assert r["break_even_lever"] == pytest.approx(2.828, abs=0.01)
    assert r["margin_factor"] == pytest.approx(2.12, abs=0.01)
    assert r["cost_next_rung_hours"] == pytest.approx(6.0, abs=0.01)
    assert r["verdict"] == "SPEND"


# ─── guards for the two flag-path defects ──────────────────────────────────────

@pytest.mark.parametrize("cost_exponent", [-1.0, 1.0])
def test_lever_direction_is_independent_of_cost_exponent(cost_exponent):
    """The Case-C regression: direction drove which rung counted as 'current'."""
    r = call(gate_class="C", lever="rate", lever_direction="lower",
             cost_exponent=cost_exponent, history="250:1.118369,125:1.1257",
             next_lever=62.5, target_floor=1.130, sem=0.0003)
    assert r["current_lever"] == 125.0, "most recent rung is the furthest along the lever"
    assert r["margin_factor"] == pytest.approx(1.33, abs=0.02)


def test_higher_is_better_picks_the_other_end():
    r = call(gate_class="C", lever="trajectory_ns", lever_direction="higher",
             cost_exponent=1.0, history="15:1.118369,30:1.1257", next_lever=60,
             target_floor=1.130, sem=0.0003)
    assert r["current_lever"] == 30.0


def test_class_c_missing_target_floor_names_the_precondition():
    r = call(gate_class="C", history="250:1.118,125:1.126", next_lever=62.5)
    assert r["verdict"] == "PRECONDITION_UNMET"
    assert "--target-floor" in r["reason"]


def test_class_c_missing_next_lever_names_the_precondition():
    r = call(gate_class="C", history="250:1.118,125:1.126", target_floor=1.130)
    assert r["verdict"] == "PRECONDITION_UNMET"
    assert "--next-lever" in r["reason"]


# ─── policy is the single source of truth for the numbers ──────────────────────

def test_thresholds_come_from_the_policy_not_a_second_copy():
    policy = json.loads(POLICY.read_text())
    block = policy["policies"]["equilibration"]["remedy_economics"]
    assert set(block["thresholds"]) == {
        "variance_limited_sigma", "min_margin_factor", "converged_cost_ceiling_hours"}
    # every threshold the script reads is declared in the policy, and nowhere else
    src = (REPO_ROOT / "orchestration" / "scripts" / "remedy_economics.py").read_text()
    for name in block["thresholds"]:
        assert f'thresholds["{name}"]' in src
    assert "VARIANCE_LIMITED_SIGMA" not in src and "MIN_MARGIN_FACTOR" not in src


def test_policy_declares_the_class_a_carve_out():
    policy = json.loads(POLICY.read_text())
    block = policy["policies"]["equilibration"]["remedy_economics"]
    assert "class_A_is_always_worth_paying" in block
    assert block["default_source"].endswith("remedy_economics.py")
