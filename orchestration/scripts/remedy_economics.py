#!/usr/bin/env python3
"""Decide whether a recovery rung is worth spending, before it is spent.

Implements the `remedy_economics` policy in orchestration/decision_policy.json,
which holds the thresholds this script reads at runtime. Callers transcribe the
verdict; they do not re-derive it.

A rung buys accuracy with wall time. That only works when the residual is a
sampling (variance) term. Every gate class except B is a bias term, where the
question is not "how long" but "can this lever reach the target at all, and is
the value converged if it does". This script answers both from the rungs
already spent.
"""

import argparse
import json
import math
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parent.parent / "decision_policy.json"


def load_thresholds(policy_path):
    policy = json.loads(Path(policy_path).read_text())
    return policy["policies"]["equilibration"]["remedy_economics"]["thresholds"]


def fit_log_linear(history):
    """metric = A + B*ln(lever). Returns (A, B, rss, n)."""
    xs = [math.log(lev) for lev, _ in history]
    ys = [m for _, m in history]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("all lever values identical - no slope is determined")
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    rss = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    return a, b, rss, n


def solve_lever(a, b, target):
    """Lever value at which the fit reaches `target`."""
    if b == 0:
        return None
    return math.exp((target - a) / b)


def cost_hours(last_lever, last_hours, lever, exponent):
    if last_hours is None or last_lever is None:
        return None
    return last_hours * (lever / last_lever) ** exponent


def parse_history(s):
    out = []
    for pair in s.split(","):
        lev, metric = pair.split(":")
        out.append((float(lev), float(metric)))
    return out


def decide(args, thresholds):
    lower_is_better = args.lever_direction == "lower"
    r = {
        "failing_gate": args.failing_gate,
        "gate_class": args.gate_class,
        "lever": args.lever,
        "lever_direction": args.lever_direction,
    }

    history = parse_history(args.history)
    # the most recently spent rung is the one furthest along the lever
    current_lever, current_metric = (
        min(history, key=lambda p: p[0]) if lower_is_better else max(history, key=lambda p: p[0])
    )
    r["current_value"] = current_metric
    r["current_lever"] = current_lever

    # --- Test 1: is the residual variance or bias? ---
    if args.target_floor is not None:
        gap_to_floor = args.target_floor - current_metric
        r["gap_to_floor"] = round(gap_to_floor, 6)
        if args.sem and args.sem > 0:
            r["gap_over_sem"] = round(abs(gap_to_floor) / args.sem, 1)
            r["residual_type"] = (
                "variance"
                if abs(gap_to_floor) <= thresholds["variance_limited_sigma"] * args.sem
                else "bias"
            )
        else:
            r["residual_type"] = "unknown"
    else:
        r["residual_type"] = "unknown"

    # --- Test 2: is this lever able to address this gate class at all? ---
    if args.gate_class == "A":
        r["verdict"] = "SPEND_STRUCTURAL"
        r["reason"] = (
            "Class A admissibility: a physical/geometric defect no trajectory length fixes. "
            "The class's own structural remedy (rebuild/re-route) removes the bias completely "
            "and costs once - pay it. Never spend EXTEND or RE-ANNEAL rungs here."
        )
        return r
    if args.gate_class == "D":
        r["verdict"] = "WRONG_LEVER"
        r["reason"] = "Class D advisory: unattainable within accessible MD by construction. Log, never block."
        return r
    if args.gate_class == "B":
        if r["residual_type"] == "bias":
            r["verdict"] = "WRONG_LEVER"
            r["reason"] = (
                f"Gate is Class B (remedy EXTEND) but the gap is {r.get('gap_over_sem')}x SEM - "
                "the residual is bias, not undersampling. Re-classify before extending."
            )
            return r
        r["verdict"] = "SPEND"
        r["reason"] = (
            "Class B convergence with a variance-limited residual: more sampling at the same "
            "state is exactly the remedy."
        )
        return r

    # --- Class C: distance from experiment. Bias by definition; price the lever. ---
    missing = [
        flag
        for flag, val in (
            ("--target-floor", args.target_floor),
            ("--next-lever", args.next_lever),
        )
        if val is None
    ]
    if missing:
        r["verdict"] = "PRECONDITION_UNMET"
        r["reason"] = (
            f"Class C pricing needs {' and '.join(missing)} - the closure forecast cannot be "
            "computed without it. --target-floor is the gate threshold the metric must clear; "
            "--next-lever is the lever value the proposed rung would deliver."
        )
        return r

    if len(history) < 2:
        r["verdict"] = "SPEND"
        r["reason"] = (
            "Only one point on this lever - its slope is not yet measured, so no closure "
            "forecast is possible. Spend exactly one rung to establish the slope, then re-run "
            "this check before spending a second."
        )
        r["spend_limit"] = "one rung"
        return r

    a, b, rss, n = fit_log_linear(history)
    r["fit"] = {"intercept": round(a, 6), "slope_per_ln_lever": round(b, 6), "n_points": n}
    if n > 2:
        r["fit"]["residual_sd"] = round(math.sqrt(rss / (n - 2)), 6)

    r["predicted_at_next_rung"] = round(a + b * math.log(args.next_lever), 6)

    break_even = solve_lever(a, b, args.target_floor)
    r["break_even_lever"] = round(break_even, 4) if break_even else None

    if break_even:
        margin = (break_even / args.next_lever) if lower_is_better else (args.next_lever / break_even)
        r["margin_factor"] = round(margin, 2)
    else:
        margin = 0.0
        r["margin_factor"] = None

    r["cost_next_rung_hours"] = (
        round(cost_hours(current_lever, args.last_rung_hours, args.next_lever, args.cost_exponent), 1)
        if args.last_rung_hours else None
    )

    # --- Test 3: converged, or merely lever-dependent? ---
    physical_lever = solve_lever(a, b, args.physical_target) if args.physical_target else None
    if physical_lever:
        r["lever_for_physical_target"] = float(f"{physical_lever:.4g}")
        r["decades_to_physical_target"] = round(abs(math.log10(physical_lever / current_lever)), 2)
        ch = cost_hours(current_lever, args.last_rung_hours, physical_lever, args.cost_exponent)
        if ch:
            r["cost_to_physical_target_hours"] = float(f"{ch:.4g}")
            r["cost_to_physical_target_days"] = round(ch / 24.0, 1)

    unreachable = (
        r.get("cost_to_physical_target_hours") is not None
        and r["cost_to_physical_target_hours"] > thresholds["converged_cost_ceiling_hours"]
    )
    min_margin = thresholds["min_margin_factor"]

    if margin < 1.0:
        r["verdict"] = "STOP_ANNOTATE"
        r["reason"] = (
            f"Forecast fails: predicted {r['predicted_at_next_rung']} vs floor {args.target_floor}. "
            f"Break-even needs lever {r['break_even_lever']}, this rung delivers {args.next_lever}."
        )
    elif margin < min_margin:
        r["verdict"] = "STOP_ANNOTATE"
        r["reason"] = (
            f"Marginal bet: only {r['margin_factor']}x headroom in {args.lever} against a required "
            f"{min_margin}x (break-even {r['break_even_lever']} vs delivered {args.next_lever}). "
            f"Costs {r.get('cost_next_rung_hours')} h for an outcome the forecast cannot call."
        )
    elif unreachable:
        r["verdict"] = "STOP_ANNOTATE"
        r["reason"] = (
            f"Would clear the gate but not converge: reaching the physical target "
            f"{args.physical_target} needs {r.get('decades_to_physical_target')} more decades of "
            f"{args.lever} (~{r.get('cost_to_physical_target_days')} days). A rung that buys a "
            "passing but lever-dependent number is worse than an annotated failing one."
        )
    else:
        r["verdict"] = "SPEND"
        r["reason"] = (
            f"{r['margin_factor']}x headroom over break-even at {r.get('cost_next_rung_hours')} h, "
            "and the physical target is reachable within budget."
        )

    if unreachable and r["verdict"] == "STOP_ANNOTATE":
        r["annotation_required"] = (
            f"{args.failing_gate}: {r['current_value']} vs target {args.physical_target}; "
            f"{args.lever}-limited, not converged - closing the gap needs "
            f"~{r.get('decades_to_physical_target')} decades of {args.lever}."
        )
    return r


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--failing-gate", required=True)
    p.add_argument("--gate-class", required=True, choices=["A", "B", "C", "D"])
    p.add_argument("--lever", required=True,
                   help="the variable the rung buys, e.g. cooling_rate_K_per_ns, trajectory_ns, nchain")
    p.add_argument("--lever-direction", required=True, choices=["lower", "higher"],
                   help="which direction of the lever is the improvement: 'lower' for cooling rate, "
                        "'higher' for trajectory length or nchain. Independent of --cost-exponent")
    p.add_argument("--history", required=True,
                   help="lever:metric pairs from rungs already spent, e.g. '250:1.1184,125:1.1257'")
    p.add_argument("--next-lever", type=float, help="lever value the proposed rung would deliver")
    p.add_argument("--target-floor", type=float, help="gate threshold the metric must clear")
    p.add_argument("--physical-target", type=float,
                   help="the experimental/true value, not the band edge - used for the convergence test")
    p.add_argument("--sem", type=float, help="statistical uncertainty on the current metric")
    p.add_argument("--last-rung-hours", type=float, help="measured wall time of the most recent rung")
    p.add_argument("--cost-exponent", type=float, default=-1.0,
                   help="cost scales as lever**exponent; -1 for cooling rate (slower=longer), "
                        "+1 for trajectory length")
    p.add_argument("--policy", default=str(POLICY_PATH))
    args = p.parse_args()

    try:
        result = decide(args, load_thresholds(args.policy))
    except Exception as e:  # noqa: BLE001
        result = {"error": str(e)}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
