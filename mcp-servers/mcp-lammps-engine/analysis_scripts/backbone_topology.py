"""Bond-topology backbone-path reconstruction, shared by every tool that needs a polymer chain's
true backbone: check_equilibration_comprehensive.py, mda_end_to_end.py, extract_thermal.py, and
derive_backbone_types.py.

Declared atom types cannot reliably select the backbone: a class can reuse one type between a
backbone atom and a pendant-branch atom (PACR/PMMA does), and even where types are unambiguous,
sorting the selection by atom INDEX silently assumes the backbone is a run of consecutively
numbered atoms -- true only for a straight aliphatic chain. The backbone is instead the graph
diameter of the chain's heavy-atom bond graph: BFS from any heavy atom to its farthest peer, then
BFS again from there. Both endpoints are chain termini and the walk between them is the backbone;
side groups are short branches off it, and hydrogens are excluded so they cannot extend the walk.
Needs only Masses + Bonds -- no atom types, no simulation trajectory.
"""

from collections import deque

import numpy as np

H_MASS_MAX = 4.0  # excludes H (~1) and D (~2) so neither can extend the backbone walk


def backbone_path(chain):
    """Return (positions, indices) of chain's backbone atoms, in BONDED order.

    `chain` is an MDAnalysis AtomGroup (e.g. `universe.select_atoms(f"resid {cid}")`).
    Returns (None, None) when there is no bond topology or fewer than two heavy atoms.
    """
    try:
        heavy = {int(a.index) for a in chain.atoms if float(a.mass) > H_MASS_MAX}
    except Exception:
        return None, None
    if len(heavy) < 2:
        return None, None

    adj = {i: [] for i in heavy}
    try:
        bonds = chain.bonds
    except Exception:
        return None, None
    for b in bonds:
        a1, a2 = int(b.atoms[0].index), int(b.atoms[1].index)
        if a1 in heavy and a2 in heavy:
            adj[a1].append(a2)
            adj[a2].append(a1)

    def _bfs(src):
        dist, prev = {src: 0}, {}
        queue = deque([src])
        while queue:
            node = queue.popleft()
            for nxt in adj[node]:
                if nxt not in dist:
                    dist[nxt] = dist[node] + 1
                    prev[nxt] = node
                    queue.append(nxt)
        return max(dist, key=dist.get), prev

    end_a, _ = _bfs(next(iter(heavy)))
    end_b, prev = _bfs(end_a)
    path = [end_b]
    while path[-1] != end_a:
        path.append(prev[path[-1]])
    path.reverse()

    if len(path) < 2:
        return None, None

    idx = np.array(path, dtype=int)
    return chain.universe.atoms[idx].positions, idx


def backbone_type_coverage(universe, path_idx, backbone_set):
    """Fraction of the reconstructed path carrying one of the declared backbone_types.

    Advisory only: the path itself comes from bond topology and does not depend on this. A low
    value means backbone_types under- or mis-describes this chain's actual backbone.
    """
    if path_idx is None or not backbone_set:
        return None
    types = np.array([int(t) for t in universe.atoms[path_idx].types])
    return float(np.isin(types, list(backbone_set)).mean())
