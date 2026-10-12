#!/usr/bin/env python3
"""JSON Schemas for the two model nodes' structured output.

Both are deliberately narrow. What a node CANNOT return is the enforcement: `origin` is
absent from the adjudication schema because python stamps it, and `confidence` excludes
"unreviewed" because that value is the one thing standing between a scaffold plan and
execution. Anything a schema does not name cannot reach run_plan.json at all -- see
nodes.apply_adjudication, which touches exactly five keys.

The grounding schema tracks the shape documented in
.claude/agents/literature-grounding-worker.md ("Output JSON schema"), minus the fields the
driver stamps itself (generated_at, plan_reviewed).
"""
from __future__ import annotations

_SOURCE = {
    "type": "object",
    "required": ["doi", "claim"],
    "properties": {
        "doi": {"type": "string"},
        "claim": {"type": "string"},
        "trust_tier": {"type": "string",
                       "enum": ["peer_reviewed_doi", "preprint", "vendor", "educational"]},
        "verified": {"type": "boolean"},
        "origin_record_id": {"type": "string"},
    },
}

_RECOMMENDATION = {
    "type": "object",
    "properties": {
        "recommendation": {"type": ["string", "null"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "sources": {"type": "array", "items": _SOURCE},
    },
}

GROUNDING_SCHEMA: dict = {
    "type": "object",
    "required": ["polymer_class", "smiles", "md_studies", "critique", "dominant_uncertainty"],
    "properties": {
        "polymer_name": {"type": ["string", "null"]},
        "polymer_class": {"type": "string"},
        "smiles": {"type": "string"},
        "md_studies": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["doi", "title", "trust_tier", "verified", "lead_source"],
                "properties": {
                    "doi": {"type": "string",
                            "description": "bare DOI, not a https://doi.org/ URL"},
                    "url": {"type": ["string", "null"]},
                    "title": {"type": "string"},
                    "year": {"type": ["integer", "null"]},
                    "trust_tier": {"type": "string",
                                   "enum": ["peer_reviewed_doi", "preprint", "vendor",
                                            "educational"]},
                    "verified": {"type": "boolean"},
                    "lead_source": {"type": "string",
                                    "enum": ["polydatabase", "evidence_store", "websearch"]},
                    "force_field": {"type": ["string", "null"]},
                    "force_field_type": {"type": ["string", "null"]},
                    "electrostatics": {"type": ["string", "null"]},
                    "ensemble": {"type": ["string", "null"]},
                    "T_K": {"type": ["number", "null"]},
                    "P_atm": {"type": ["number", "null"]},
                    "system_type": {"type": ["string", "null"]},
                    "material_morphology": {"type": ["string", "null"]},
                    "chain_length_or_mw": {"type": ["string", "null"]},
                    "number_of_chains": {"type": ["string", "null"]},
                    "reported_properties": {
                        "type": "array",
                        "items": {"type": "object",
                                  "properties": {"property": {"type": "string"},
                                                 "value": {"type": ["number", "string", "null"]},
                                                 "unit": {"type": ["string", "null"]}}},
                    },
                    "note": {"type": ["string", "null"]},
                },
            },
        },
        "critique": {
            "type": "object",
            "properties": {
                "D-01_ff": {
                    "type": "object",
                    "required": ["autofilled_choice", "verdict", "confidence", "reason"],
                    "properties": {
                        "autofilled_choice": {"type": ["string", "null"]},
                        "verdict": {"type": "string",
                                    "enum": ["agrees", "disagrees", "no_evidence"]},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "reason": {"type": "string"},
                        "suggested_override": {"type": ["object", "null"]},
                        "supporting_dois": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
        "forcefield": _RECOMMENDATION,
        "electrostatics": _RECOMMENDATION,
        "tg_target_K": {
            "type": "object",
            "properties": {
                "range": {"type": ["array", "null"], "items": {"type": "number"}},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "sources": {"type": "array", "items": _SOURCE},
            },
        },
        "dominant_uncertainty": {"type": "string"},
        "notes": {"type": ["string", "null"]},
    },
}


def adjudication_schema(override_contract: dict) -> dict:
    """The adjudicator's contract. `override_contract` is scientific_control's live
    planning_parameter_contract(), inlined as the description of `overrides` so the model
    sees the allowlist and each numeric key's validated range rather than guessing at it.

    Note what is NOT here: no `origin` (python stamps it, so an autofill entry can be
    neither retagged nor deleted), no `choice` (read-only -- materialize_plan ignores it,
    so editing it would be a silent no-op), no experimental_* shortcuts beyond whatever the
    allowlist itself permits, and no free-form plan keys at all.
    """
    import json

    return {
        "type": "object",
        "required": ["confidence", "dominant_uncertainty", "overrides", "critic_evidence",
                     "findings"],
        "properties": {
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": ("Replaces 'unreviewed'. This is the only thing standing "
                                "between the plan and execution."),
            },
            "dominant_uncertainty": {
                "type": "string",
                "description": "One scalar phrase naming the gap that matters most.",
            },
            "overrides": {
                "type": "object",
                "description": ("decided_params overrides. ONLY keys in this contract are "
                                "accepted; anything else, or out of range, is rejected by "
                                "scientific_control.validate_overrides before it reaches "
                                "disk. Contract: " + json.dumps(override_contract)),
            },
            "critic_evidence": {
                "type": "array",
                "description": ("Sources that changed or materially strengthened the D-01 "
                                "force-field decision. Appended to that row's evidence[]; "
                                "the driver stamps origin='critic'."),
                "items": {
                    "type": "object",
                    "required": ["claim", "source_doi", "citation"],
                    "properties": {
                        "claim": {"type": "string"},
                        "source_doi": {"type": "string"},
                        "citation": {"type": "string"},
                    },
                },
            },
            "findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": ("Adjudication prose, e.g. why a 'disagrees' verdict was "
                                "declined. Appended to decisions[0].critique.findings."),
            },
        },
    }
