"""run-summary Tg grading band must prefer polymer_rules.json over a raw DB aggregate.

`_resolve_run_summary_params` used to prefer query_best_match.py's pooled DB median over
polymer_rules.json's own cited, class/member-specific experimental_tg_K. For PHYC/PE this pools
PE's own documented sub-Tg gamma-relaxation rows (~145 K, explicitly called out as NOT the true
Tg in polymer_rules.json's own notes) in with the real ~195 K glass transition -- name-resolving
the DB lookup doesn't fix this, since the contaminating rows are filed under the correctly
name-matched polymer_id. polymer_rules.json's own run-name-resolved value must win whenever it
resolves to real numbers; the DB stays a fallback only for classes with no such curated value.

`do_summary` (run_campaign.py) no longer auto-applies its DB CLI shell-out into
args.exp_tg_min/max at all (that path also incorrectly bypassed the exp_K min==max single-point
guard) -- exp_lookup.json is written for human review only, so args.exp_tg_min/max/exp_K_min/max
stay None from a real run and this same priority chain governs.
"""
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from stage_params import _resolve_run_summary_params  # noqa: E402
from run_campaign import _base_args  # noqa: E402

PHYC = {
    "preferred_ff": "trappe-ua",
    "charge_method": "none",
    "electrostatics": "lj_cut",
    "dp_typical": 120,
    "nchain": 20,
    "experimental_tg_K": {"PE": 195, "PP": 258, "PIB": 205},
}

# The real, observed contamination: DB pools PE's own gamma-relaxation rows into the median.
_CONTAMINATED_DB = {"tg_median_K": 191.6, "density_gcm3": None, "K_range_GPa": None}


def _args():
    args = _base_args("PE1", "PHYC", "/tmp/plan.json")
    args.output_dir = "/tmp/pe1_raw/"
    return args


def test_polymer_rules_wins_over_db_when_both_available():
    with patch("stage_params._db_exp_lookup", return_value=_CONTAMINATED_DB):
        sp = _resolve_run_summary_params(_args(), PHYC)
    assert sp["exp_tg_range"] == [175, 215]  # 195 +/- 20, not [172, 212] from the DB median


def test_db_still_used_when_class_has_no_curated_tg():
    cls = dict(PHYC)
    del cls["experimental_tg_K"]
    with patch("stage_params._db_exp_lookup", return_value=_CONTAMINATED_DB):
        sp = _resolve_run_summary_params(_args(), cls)
    assert sp["exp_tg_range"] == [172, 212]  # 191.6 +/- 20, DB is the only source


def test_explicit_cli_override_still_wins_over_polymer_rules():
    args = _args()
    args.exp_tg_min, args.exp_tg_max = 180, 210
    with patch("stage_params._db_exp_lookup", return_value=_CONTAMINATED_DB):
        sp = _resolve_run_summary_params(args, PHYC)
    assert sp["exp_tg_range"] == [180, 210]


def test_no_data_anywhere_falls_back_to_placeholder_sentinel():
    with patch("stage_params._db_exp_lookup", return_value={"tg_median_K": None, "density_gcm3": None, "K_range_GPa": None}):
        sp = _resolve_run_summary_params(_args(), {})
    assert sp["exp_tg_range"] == ["<exp_tg_min>", "<exp_tg_max>"]
