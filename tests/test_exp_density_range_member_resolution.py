"""Multi-member exp_density_gcm3 resolution for _exp_density_range.

`_exp_density_range` fed the equil-check density-in-band gate and run-summary's exp_density_range
from the class MEDIAN across every member of a multi-member `experimental_density_gcm3` dict
(e.g. PHYC's {PE: 0.855, PP: 0.91, PIB: 0.92}), ignoring which member the run's SMILES actually
is -- the same class-mean-averaging bug `_exp_tg_range`/`_exp_tg_point` were already fixed for.
A PE1 run got PP's median (0.91) banded to [0.864, 0.956] instead of PE's own [0.812, 0.898],
sitting PE's true ~0.855 g/cm3 right at the wrong band's edge.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))

from stage_params import _exp_density_range  # noqa: E402

PHYC = {
    "experimental_density_gcm3": {
        "PE": 0.855,
        "PP": 0.91,
        "PIB": 0.92,
        "note": "fully amorphous TraPPE-UA densities at 300K",
    }
}


def test_run_name_resolves_to_its_own_member_not_the_class_median():
    assert _exp_density_range(PHYC, run_name="PE1") == [round(0.855 * 0.95, 3), round(0.855 * 1.05, 3)]
    assert _exp_density_range(PHYC, run_name="PP2") == [round(0.91 * 0.95, 3), round(0.91 * 1.05, 3)]
    assert _exp_density_range(PHYC, run_name="PIB1") == [round(0.92 * 0.95, 3), round(0.92 * 1.05, 3)]


def test_no_run_name_falls_back_to_class_median_not_error():
    assert _exp_density_range(PHYC) == [round(0.91 * 0.95, 3), round(0.91 * 1.05, 3)]


def test_unmatched_run_name_falls_back_to_class_median():
    assert _exp_density_range(PHYC, run_name="UNKNOWN99") == [round(0.91 * 0.95, 3), round(0.91 * 1.05, 3)]


def test_single_value_class_unaffected():
    cls = {"experimental_density_gcm3": 1.19}
    assert _exp_density_range(cls, run_name="PMMA1") == [round(1.19 * 0.95, 3), round(1.19 * 1.05, 3)]
