---
name: feedback-rdkit-env-for-atom-count
description: The base python3 lacks rdkit; the D-08 atom-count one-liner must use a conda env python
metadata:
  type: feedback
---

The D-08 hardware step's atom-count one-liner (`python3 -c "from rdkit import Chem; ..."`) FAILS under the default `python3` on this host — `ModuleNotFoundError: No module named 'rdkit'`. None of the `which -a python3` interpreters have rdkit.

**Why:** rdkit only lives in the conda/miniforge envs. `conda env list` shows envs at `/home/alexzhao/miniforge3/envs/{mol-builder,radonpy}` (and base, which also lacks it).

**How to apply:** for the atom-count estimate, call a conda env python directly with an absolute path:
`/home/alexzhao/miniforge3/envs/mol-builder/bin/python -c "from rdkit import Chem; ..."` (radonpy env works too). Don't burn a call on the bare `python3` first. (Username in the path varies per machine — derive from `conda env list` rather than hard-coding.)
