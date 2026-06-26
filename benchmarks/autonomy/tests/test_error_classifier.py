"""error_classifier maps recover.md error strings; keeps inferred cases inferred."""
from error_classifier import CATALOG, EXPECTED_ROWS, classify_error


def test_catalog_matches_recover_md_row_count():
    assert len(CATALOG) == EXPECTED_ROWS  # 15 rows


def test_prescripted_log_strings_map_correctly():
    cases = {
        "ERROR: Lost atoms: original 1000 current 993": "lost_atoms",
        "ERROR: Out of range atoms - cannot compute PPPM (pppm.cpp:1934)": "pppm_out_of_range",
        "ERROR: Unknown pair_style lj/charmm": "ff_style_mismatch",
        "CUDA error: out of memory": "gpu_oom",
        "Pressure is nan at step 50": "energy_nan",
    }
    for text, expected in cases.items():
        res = classify_error(text)
        assert res["error_class"] == expected, (text, res)
        assert res["prescripted"] is True


def test_unsupported_increment_stays_inferred():
    # The discriminator: a genuinely unsupported field increment has NO scripted fix.
    res = classify_error("EMC field error: increment 'n_2,hn' not found in pcff field")
    assert res["error_class"] == "unknown"
    assert res["prescripted"] is False


def test_unknown_text_is_inferred():
    res = classify_error("something nobody anticipated happened here")
    assert res["error_class"] == "unknown"
    assert res["prescripted"] is False
