#!/usr/bin/env python3
"""Integrator helper for the two-machine PolyJarvis revision workflow.

Two modes:

  * Guard-only (no --source-ref): scan the current checkout for foreign
    ``/home/<user>/...`` paths and (optionally) fix them. Cheap pre-commit check.

  * Integrate (--source-ref origin/<branch>): create an isolated worktree off
    ``origin/main``, merge the source ref (conflict-checked first), run the
    foreign-home guard, run the test suite, and print PR + cleanup commands.

Paths are derived from this file's location (REPO_ROOT), so the script is itself
machine-agnostic. The only legitimately machine-specific paths are the LAMMPS /
KOKKOS binaries (env-gated via LAMBDA_LAMMPS*), which the guard ignores.

Examples:
    python3 scripts/integrate.py                       # guard the current tree
    python3 scripts/integrate.py --fix                 # ...and rewrite foreign homes
    python3 scripts/integrate.py --source-ref origin/feature-x
"""
from __future__ import annotations

import argparse
import getpass
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Foreign /home/<user>/ paths matching these substrings are legitimately
# machine-specific (env-gated binaries / user-local toolchains) — not chores.
GUARD_IGNORE = ("lammps-install", "miniforge", "miniconda", "/.conda/", "/.cache/")
HOME_RE = re.compile(r"/home/([A-Za-z0-9_.-]+)/")


def git(*args: str, check: bool = True, capture: bool = True) -> str:
    """Run a git command rooted at REPO_ROOT and return stdout."""
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return (r.stdout or "").strip()


def find_foreign_paths(root: Path, user: str) -> list[tuple[str, str]]:
    """Return (file:line, text) for tracked lines with a /home/<other-user>/ path."""
    out = subprocess.run(
        ["git", "-C", str(root), "grep", "-nIE", r"/home/[A-Za-z0-9_.-]+/"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ).stdout or ""
    offenders: list[tuple[str, str]] = []
    for line in out.splitlines():
        if any(ig in line for ig in GUARD_IGNORE):
            continue
        users = {m.group(1) for m in HOME_RE.finditer(line)}
        if users - {user}:                       # at least one foreign user
            parts = line.split(":", 2)           # git grep -n format: file:lineno:text
            loc = ":".join(parts[:2]) if len(parts) >= 2 else parts[0]
            text = parts[2].strip() if len(parts) == 3 else ""
            offenders.append((loc, text))
    return offenders


def run_guard(root: Path, user: str, fix: bool) -> int:
    offenders = find_foreign_paths(root, user)
    if not offenders:
        print(f"✓ foreign-home guard: clean (no /home/<other> paths; current user '{user}')")
        return 0
    print(f"✗ foreign-home guard: {len(offenders)} line(s) reference a non-'{user}' home:")
    for loc, text in offenders[:40]:
        print(f"    {loc}: {text}")
    if len(offenders) > 40:
        print(f"    ... and {len(offenders) - 40} more")
    if not fix:
        print("\n  These should be genericized at the source (REPO_ROOT / repo-relative /"
              " env-gated), not sed-swapped. Re-run with --fix only as a build-it-now safety net.")
        return 1
    # --fix: rewrite each distinct foreign user -> current user, in offending files only.
    foreign_users = {u for _loc, _t in offenders
                     for u in (set(HOME_RE.findall(f"{_loc}:{_t}")) - {user})}
    files = sorted({loc.split(":")[0] for loc, _ in offenders})
    for f in files:
        p = root / f
        s = p.read_text()
        for fu in foreign_users:
            s = s.replace(f"/home/{fu}/", f"/home/{user}/")
        p.write_text(s)
    print(f"\n  --fix applied: rewrote {sorted(foreign_users)} → '{user}' in {len(files)} file(s).")
    return 0


def integrate(source_ref: str, branch: str, worktree: Path, user: str,
              fix: bool, run_tests: bool) -> int:
    git("fetch", "origin", "--prune", capture=False)

    # Conflict pre-check (read-only, in-memory merge).
    mt = git("merge-tree", "--write-tree", "origin/main", source_ref, check=False)
    if not re.match(r"^[0-9a-f]{40}$", mt.splitlines()[0] if mt else ""):
        print(f"✗ merge of {source_ref} into origin/main has CONFLICTS:\n{mt[:2000]}")
        return 2
    print(f"✓ {source_ref} merges into origin/main cleanly")

    if worktree.exists():
        print(f"✗ worktree path already exists: {worktree} (remove it first)")
        return 2
    git("worktree", "add", "-b", branch, str(worktree), "origin/main", capture=False)
    subprocess.run(["git", "-C", str(worktree), "merge", "--no-edit", source_ref], check=True)

    rc = run_guard(worktree, user, fix)
    if rc != 0 and not fix:
        print("  (resolve the guard before continuing; worktree left in place)")
        return rc

    if run_tests:
        print("\n=== running test suite ===")
        t = subprocess.run(["python3", "-m", "pytest", "tests/",
                            "mcp-servers/mcp-lammps-engine/tests/", "-q"], cwd=str(worktree))
        if t.returncode != 0:
            print("✗ tests FAILED — do not open the PR; investigate in the worktree.")
            return 3
        print("✓ tests passed")

    print("\n=== next steps ===")
    print(f"  cd {worktree} && git push -u origin {branch}")
    print(f"  open PR: https://github.com/arz-2/PolyJarvis/pull/new/{branch}")
    print("  squash-merge, then clean up:")
    print(f"    git -C {REPO_ROOT} worktree remove {worktree}")
    print(f"    git -C {REPO_ROOT} branch -D {branch}")
    print(f"    git -C {REPO_ROOT} push origin --delete {branch}")
    print("  finally: run /ingest-memory over the combined memory queue.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-ref", help="branch/ref to integrate, e.g. origin/feature-x. "
                                         "Omit to run the guard on the current checkout only.")
    ap.add_argument("--branch", help="integration branch name (default: integrate/<ref>-<date>)")
    ap.add_argument("--worktree", type=Path,
                    default=Path.home() / "pj-integrate",
                    help="isolated worktree path (default: ~/pj-integrate)")
    ap.add_argument("--fix", action="store_true",
                    help="rewrite foreign /home/<user>/ paths to the current user (safety net)")
    ap.add_argument("--no-tests", action="store_true", help="skip pytest in integrate mode")
    args = ap.parse_args()

    user = getpass.getuser()
    if not args.source_ref:
        return run_guard(REPO_ROOT, user, args.fix)

    ref_slug = re.sub(r"[^A-Za-z0-9]+", "-", args.source_ref).strip("-")
    branch = args.branch or f"integrate/{ref_slug}-{date.today().isoformat()}"
    return integrate(args.source_ref, branch, args.worktree, user,
                     args.fix, run_tests=not args.no_tests)


if __name__ == "__main__":
    sys.exit(main())
