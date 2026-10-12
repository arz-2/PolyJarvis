"""diffusion_regime must never assert a "kinetically trapped" verdict on its own.

kinetic_trap_flag (msd_max_A2 vs mean_Rg2_A2, the Auhl/Kremer/Grest chain-displaced-its-own-size
criterion) is the only field that tests trapping. diffusion_regime is a pure MSD power-law
exponent classification -- alpha < 0.4 also covers ordinary Rouse-regime sub-diffusion that
hasn't crossed over to Fickian behavior within the trajectory window. PE1's real equilibration
data is the counterexample that exposed the bug: alpha=0.371, kinetic_trap_flag=False (chains
displaced 2x their own Rg^2), yet diffusion_regime read "sub-diffusive / kinetically trapped".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis_scripts"))

from check_equilibration_comprehensive import _classify_diffusion_regime  # noqa: E402


def test_low_alpha_does_not_assert_trapped_verdict():
    # PE1's real value: alpha=0.371, but kinetic_trap_flag was False for this run.
    regime = _classify_diffusion_regime(0.371)
    assert "kinetically trapped" not in regime
    assert "sub-diffusive" in regime


def test_mid_alpha_is_rouse_reptation():
    assert _classify_diffusion_regime(0.6) == "sub-diffusive (Rouse/reptation)"


def test_near_one_alpha_is_fickian():
    assert _classify_diffusion_regime(1.0) == "Fickian diffusion"


def test_high_alpha_is_super_diffusive():
    assert _classify_diffusion_regime(1.3) == "super-diffusive (non-equilibrated)"


def test_none_alpha_is_insufficient_data():
    assert _classify_diffusion_regime(None) == "insufficient data"
