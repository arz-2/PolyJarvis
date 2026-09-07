#!/usr/bin/env python3
"""Does the class-derived protocol match the molecule's actual chemistry?

`polymer_class` is a BACKBONE taxonomy, and the constants it carries in
guides/polymer_rules.json -- notably `electrostatics` and `charge_method` -- are really
standing in for polarity. That proxy is exact on every polymer this repo has curated:
across all 43 `member_smiles`, the electrostatics implied by the molecule's own functional
groups agrees with its class's declared value 43/43. Which is precisely why a DISAGREEMENT
on a novel polymer is worth surfacing rather than shrugging at -- the proxy is not noisy,
so when it breaks, something real is going on.

It can break because `poly.polyinfo_classifier` matches on the extracted mainchain. A
pendant hydroxyl, nitrile or ester is invisible to it, so a molecule can land in a class
whose constants were written for a chemistry it does not actually have.

Everything here is ADVISORY. It emits findings; it never rewrites a class constant. That
split is the repo's standing discipline -- code owns decisions, advisories inform them --
and it matters more here than usual, because the class table is curated against real
validation runs while this is a rule over SMARTS.

Pure logic: takes the profile dict rdkit_cli's `chemistry` produces and a class entry, and
touches neither RDKit nor a conda env.
"""
from __future__ import annotations

from typing import Any

#: Severity vocabulary, matching how the rest of the plane talks about findings.
ADVISORY = "advisory"
WARNING = "warning"


def _fg_ids(profile: dict, location: str | None = None) -> list[str]:
    return [g["id"] for g in profile.get("functional_groups", [])
            if location is None or g.get("location") == location]


def check_electrostatics(profile: dict, class_entry: dict) -> dict | None:
    """The one that can be a physics error rather than a preference.

    `lj_cut` truncates Coulomb interactions. On an apolar aliphatic hydrocarbon that is
    correct and much cheaper; on anything carrying real partial charges it discards the
    interaction that dominates cohesive energy, and density and modulus come out low.

    The reverse -- `pppm` on a molecule with no charges to speak of -- is not wrong, only
    wasteful, so it is reported at a lower severity.
    """
    declared = class_entry.get("electrostatics")
    implied = profile.get("implied_electrostatics")
    if not declared or not implied or declared == implied:
        return None

    if declared == "lj_cut" and implied == "pppm":
        polar = [g for g in profile.get("functional_groups", [])
                 if g.get("polarity") in ("polar_protic", "polar_aprotic", "ionic")]
        where = ", ".join(f"{g['id']} ({g['location']})" for g in polar) or "heteroatoms present"
        return {
            "code": "CHEM_ELECTROSTATICS_UNDERSPECIFIED", "severity": WARNING,
            "declared": declared, "implied": implied,
            "detail": (
                f"the class declares lj_cut, but this repeat unit carries polar chemistry: "
                f"{where}. Truncating Coulomb here drops the interaction that dominates "
                f"cohesive energy, which shows up as low density and low modulus. The class "
                f"is a backbone taxonomy and polyinfo_classifier matches on the mainchain "
                f"only, so a pendant group can be missing from the label that set this "
                f"constant."),
            "suggested_override": {"electrostatics": "pppm"},
        }

    return {
        "code": "CHEM_ELECTROSTATICS_OVERSPECIFIED", "severity": ADVISORY,
        "declared": declared, "implied": implied,
        "detail": (
            "the class declares pppm, but this repeat unit is an apolar aliphatic "
            "hydrocarbon with no partial charges to speak of. Not wrong -- only more "
            "expensive than it needs to be; the long-range solver is the dominant per-step "
            "cost on a cell this size."),
        "suggested_override": None,
    }


def check_hbond_network(profile: dict, class_entry: dict) -> dict | None:
    """Inter-chain hydrogen bonding the class may not have anticipated.

    An H-bond network is what makes polyamides stiff and high-Tg, and it is also what EMC
    cannot type -- all three measured moiety rules block on `[NX3][CX3]=[OX1]`, which is why
    PAMD routes to RadonPy/GAFF2 rather than PCFF. A donor-bearing repeat unit in a class
    whose prior assumes none is worth flagging before the build, not after.
    """
    donors = profile.get("hbond_donors", 0)
    if donors < 1:
        return None
    protic = [g for g in profile.get("functional_groups", [])
              if g.get("polarity") == "polar_protic"]
    if not protic:
        return None
    return {
        "code": "CHEM_HBOND_NETWORK", "severity": ADVISORY,
        "detail": (
            f"{donors} hydrogen-bond donor(s) from "
            f"{', '.join(f'{g['id']} ({g['location']})' for g in protic)}. Inter-chain "
            "H-bonding raises Tg and modulus and slows equilibration; if any of these sit "
            "off the backbone, the class label was assigned without seeing them."),
        "groups": [g["id"] for g in protic],
        "suggested_override": None,
    }


def check_pendant_chemistry(profile: dict, class_entry: dict) -> dict | None:
    """Chemistry the class label could not have accounted for, stated plainly.

    Not a defect on its own -- PMMA's pendant ester is exactly what makes it an acrylic --
    but it is the context a critic needs in order to judge whether class constants written
    for a backbone apply to this molecule.
    """
    pendant = [g for g in profile.get("functional_groups", [])
               if g.get("location") == "pendant"
               and g.get("polarity") in ("polar_protic", "polar_aprotic", "ionic")]
    if not pendant:
        return None
    return {
        "code": "CHEM_PENDANT_POLAR_GROUPS", "severity": ADVISORY,
        "detail": (
            "polar groups sit OFF the backbone: "
            f"{', '.join(g['id'] for g in pendant)}. polyinfo_classifier matches on the "
            "extracted mainchain, so none of these informed the class label, and any class "
            "constant that assumes a backbone chemistry should be read with that in mind."),
        "groups": [g["id"] for g in pendant],
        "suggested_override": None,
    }


def check_ionic(profile: dict, class_entry: dict) -> dict | None:
    """Formal charges are outside every class prior in this repo.

    None of the 21 classes describes a polyelectrolyte, and the charge methods on offer
    (bond-increment, embedded, opls-library, RESP) all assume a neutral repeat unit. A
    charged one needs a human before it needs a force field.
    """
    if profile.get("polarity_class") != "ionic" and not profile.get("formal_charge"):
        return None
    return {
        "code": "CHEM_IONIC_SPECIES", "severity": WARNING,
        "detail": (
            f"formal charge {profile.get('formal_charge', 0)} and/or ionic groups "
            f"({', '.join(_fg_ids(profile)) or 'none named'}). No class in "
            "polymer_rules.json describes a polyelectrolyte, and every charge_method on "
            "offer assumes a neutral repeat unit -- counter-ions, screening and the "
            "long-range solver all need deciding by hand."),
        "suggested_override": None,
    }


#: Measured EMC trial-build failure rates over the 735 PI1070 repeat units that contain NO
#: N-carbonyl group (that family -- amide/imide/urea/urethane -- already has its own screen in
#: guides/ff_moiety_rules.json and blocks all 9 fields, so leaving it in confounds everything
#: else). Baseline failure on that subset is 14.6%. Derived 2026-09-07 from
#: docs/ff_coverage_sweep/arm0.jsonl; see check_build_risk for what this is and is not.
BUILD_RISK_GROUPS = {
    "alkene": {"fail_rate": 0.596, "lift": 4.1, "n": 57,
               "why": ("aliphatic C=C. Corroborated by the sweep's own recorded causes -- "
                       "missing_torsion_row and stereo_slash_breaks_esh_parser, both "
                       "spanning PDIE/PHYC -- and by EMC discarding SMILES double-bond "
                       "stereo outright.")},
    "fluoroalkyl": {"fail_rate": 0.254, "lift": 1.74, "n": 67,
                    "why": "C-F typing gaps outside the OPLS route."},
    "sulfone": {"fail_rate": 0.229, "lift": 1.57, "n": 35,
                "why": "sulfone typing is thinner than the aryl-ether backbone around it."},
}

BUILD_RISK_BASELINE = 0.146


def check_build_risk(profile: dict, class_entry: dict) -> dict | None:
    """Groups measured to correlate with an EMC trial-build failure.

    This is CORRELATION on one population, not a measured per-field blocking rule, and the
    distinction is why it lives here rather than in guides/ff_moiety_rules.json. That file
    carries a per-field `tried`/`failed`/`fail_rate` for every one of the 9 EMC fields and is
    what decides whether to probe; earning a place in it means being measured that way.
    These groups have not been, so they produce an advisory that recommends paying for the
    probe -- `--with-ff-probe` -- rather than pre-empting its answer.

    The strongest of them, aliphatic C=C at 4.1x baseline, is not represented in the moiety
    rules at all today.
    """
    hits = [(g["id"], BUILD_RISK_GROUPS[g["id"]])
            for g in profile.get("functional_groups", [])
            if g["id"] in BUILD_RISK_GROUPS]
    if not hits:
        return None
    worst = max(hits, key=lambda h: h[1]["lift"])
    return {
        "code": "CHEM_BUILD_RISK", "severity": ADVISORY,
        "detail": (
            "; ".join(f"{gid} failed {v['fail_rate']:.0%} of {v['n']} measured EMC trial "
                      f"builds ({v['lift']:.1f}x the {BUILD_RISK_BASELINE:.0%} baseline) -- "
                      f"{v['why']}" for gid, v in hits)
            + ". Correlation over one population, not a per-field blocking measurement, so "
              "this recommends running the force-field probe rather than pre-judging it."),
        "groups": [gid for gid, _ in hits],
        "worst_group": worst[0],
        "recommend": "run make_deterministic_plan run-plan --with-ff-probe",
        "suggested_override": None,
    }


# NOTE -- a melt-margin check was written here and REMOVED after measurement.
#
# The reasoning that motivated it was wrong: T_equil_K is not simply a class constant.
# stage_params.temperature_schedule already derives it per SMILES -- for a novel repeat unit
# with a trustworthy Tg it uses max(Tg + 200, 1.5 * Tg), the additive term for low-Tg
# polymers and Boyer's Tm/Tg ~ 1.5 ratio for high-Tg ones where +200 K undershoots. The class
# constant is a FLOOR that can only be raised, because it carries melting-point knowledge
# group contribution cannot see (PE's Tg is 195 K and it melts near 410 K).
#
# So a check comparing the class floor against the estimated Tg duplicates that logic while
# reading the wrong number. Measured over all 1077 PI1070 repeat units it fired exactly once,
# and in that one case the Tg estimate was `very_low` confidence -- precisely the input
# _tg_is_trustworthy_for_scheduling refuses to size a protocol from, because >30% of heavy
# atoms matched no motif (true of 59% of that set). It never fired on a polymer whose Tg was
# trustworthy, i.e. never where the schedule would actually have acted.
#
# The Tg estimate itself is still carried in the chemistry profile: it is useful evidence for
# the adjudicator, just not the basis for a warning the scheduler already handles better.

CHECKS = (check_electrostatics, check_hbond_network, check_pendant_chemistry, check_ionic,
          check_build_risk)


def consistency(profile: dict, class_entry: dict) -> dict[str, Any]:
    """Every chemistry finding for this repeat unit against its class's constants.

    Returns {"findings": [...], "n_warnings": int, "verdict": "consistent"|"review"}.
    `review` never blocks anything by itself -- it is what the graph records as plan
    evidence and hands the adjudicating critic as context.
    """
    if not profile or "error" in profile:
        return {"findings": [], "n_warnings": 0, "verdict": "unavailable",
                "detail": (profile or {}).get("error", "no chemistry profile")}

    findings = [f for f in (check(profile, class_entry) for check in CHECKS) if f]
    warnings = sum(1 for f in findings if f["severity"] == WARNING)
    return {
        "findings": findings,
        "n_warnings": warnings,
        "verdict": "review" if warnings else "consistent",
        "polarity_class": profile.get("polarity_class"),
        "backbone_groups": _fg_ids(profile, "backbone"),
        "pendant_groups": _fg_ids(profile, "pendant"),
    }
