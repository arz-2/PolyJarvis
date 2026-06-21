"""
PolyJarvis LAMMPS Engine - Script Generator
============================================
Parses RadonPy-generated LAMMPS .data files and fills template .in files
with system-specific and user-specified parameters.

Key design:
  - RadonPy always produces GAFF2/GAFF2_mod data files with a known
    set of force field styles (harmonic bonds, fourier dihedrals, etc.)
  - This generator reads the data file header to extract atom type count
    and box geometry, then injects all simulation parameters.
  - All tunable variables are exposed as named parameters with safe defaults.

Usage:
    gen = ScriptGenerator(data_file="/path/to/radon_md_lmp.data")
    info = gen.parse_data_file()
    script = gen.generate(
        template_name="nvt",
        output_path="/path/to/run_nvt.in",
        params={
            "T_START": 300, "T_FINAL": 700,
            "N_STEPS": 500000,
            "use_gpu": True,
        }
    )
"""

import os
import re
import random
from pathlib import Path
from typing import Optional

# ─── Path to templates ──────────────────────────────────────────────────────
TEMPLATES_DIR = Path(__file__).parent / "templates"

# ─── GAFF2 force field style constants ──────────────────────────────────────
# RadonPy always generates GAFF2/GAFF2_mod with these exact styles.
# These never change between polymer systems — only pair coefficients do.
GAFF2_STYLES = {
    "BOND_STYLE":      "harmonic",
    "ANGLE_STYLE":     "harmonic",
    "DIHEDRAL_STYLE":  "fourier",
    "IMPROPER_STYLE":  "cvff",
}

# Full PPPM pair style block (used for equilibration and production)
PAIR_STYLE_PPPM = (
    "pair_style lj/charmm/coul/long 8.0 12.0\n"
    "kspace_style pppm 1e-6"
)

# Short-range Coulomb pair style block (used during compression of low-density cells)
# lj/charmm/coul/charmm preserves short-range electrostatics without needing kspace,
# avoiding "out of range atoms" PPPM crashes at low initial density (~0.05 g/cm3).
PAIR_STYLE_CUTOFF = "pair_style lj/charmm/coul/charmm 8.0 12.0"

# GAFF2 amber special_bonds + arithmetic mixing (required for GAFF2/GAFF2_mod)
GAFF2_SPECIAL_BONDS = "special_bonds amber"
GAFF2_PAIR_MODIFY   = "mix arithmetic"
DEFAULT_NEIGHBOR    = "2.0"
DEFAULT_NEIGH_MODIFY = "delay 0 every 1 check yes"
DEFAULT_NEIGH_ONE    = "4000"

# ─── OPLS-AA force field style constants (EMC-generated cells) ──────────────
OPLS_STYLES = {
    "BOND_STYLE":      "harmonic",
    "ANGLE_STYLE":     "harmonic",
    "DIHEDRAL_STYLE":  "multi/harmonic",
    "IMPROPER_STYLE":  "none",
}

# OPLS-AA uses lj/cut/coul/long with geometric mixing and 1-4 scale 0.5
PAIR_STYLE_OPLS_PPPM = (
    "pair_style lj/cut/coul/long 9.5 9.5\n"
    "kspace_style pppm 1e-6"
)

# Short-range-only variant for compression stage — avoids PPPM "out of range atoms"
# crash at high pressure / rapidly shrinking box. Mirrors GAFF2's lj/charmm/coul/charmm
# compress path. Switch back to lj/cut/coul/long after reaching target density (stage 04+).
PAIR_STYLE_OPLS_CUTOFF = "pair_style lj/cut/coul/cut 9.5 9.5"

OPLS_SPECIAL_BONDS = "special_bonds lj/coul 0 0 0.5"
OPLS_PAIR_MODIFY   = "mix geometric tail yes"

# ─── PCFF class2 force field style constants (EMC-generated cells) ──────────
# EMC outputs cells at ~0.5× experimental density, so PPPM is safe throughout —
# no cutoff-only compression phase needed (unlike GAFF2 cells at 0.05 g/cm³).
PCFF_STYLES = {
    "BOND_STYLE":      "class2",
    "ANGLE_STYLE":     "class2",
    "DIHEDRAL_STYLE":  "class2",
    "IMPROPER_STYLE":  "class2",
}

PAIR_STYLE_PCFF_PPPM = (
    "pair_style lj/class2/coul/long 9.5 9.5\n"
    "kspace_style pppm 1e-6"
)

# Fallback for use_pppm=False (e.g. manual override); rarely needed for PCFF.
PAIR_STYLE_PCFF_CUTOFF = "pair_style lj/class2/coul/cut 9.5 9.5"

# PCFF uses full 1-4 nonbonded interactions and sixth-power combining rules.
PCFF_SPECIAL_BONDS = "special_bonds lj/coul 0 0 1"
PCFF_PAIR_MODIFY   = "mix sixthpower tail yes"

# ─── TraPPE-UA force field style constants (EMC-generated cells) ─────────────
# United-atom: no explicit H, no Coulomb interactions, no kspace.
# Dihedrals use 5-coefficient multi/harmonic (EMC TraPPE-UA output format).
TRAPPE_UA_STYLES = {
    "BOND_STYLE":      "harmonic",
    "ANGLE_STYLE":     "harmonic",
    "DIHEDRAL_STYLE":  "multi/harmonic",
    "IMPROPER_STYLE":  "none",
}

# TraPPE-UA: exclude all 1-2/1-3/1-4 LJ (bonded terms handle short-range); no Coulomb.
TRAPPE_SPECIAL_BONDS = "special_bonds lj 0 0 0"
TRAPPE_PAIR_MODIFY   = "mix arithmetic tail yes"


# ─── Template parameter catalogs ─────────────────────────────────────────────
# Default parameters for each template. All can be overridden by caller.
TEMPLATE_DEFAULTS = {
    "minimize": {
        "LOG_FILE":        "minimize.log",
        "DUMP_FILE":       "minimize.dump",
        "WRITE_DATA_FILE": "minimized.data",
        "LAST_DUMP_FILE":  "minimize_last.dump",
        "MIN_STYLE":       "cg",
        "ETOL":            1e-6,
        "FTOL":            1e-6,
        "MAXITER":         50000,
        "MAXEVAL":         100000,
        "THERMO_FREQ":     500,
        "DUMP_FREQ":       1000,
        "use_gpu":         False,
        "use_pppm":        True,
    },
    "nvt": {
        "LOG_FILE":         "nvt.log",
        "LOG_APPEND":       False,
        "DUMP_FILE":        "nvt.dump",
        "LAST_DUMP_FILE":   "nvt_last.dump",
        "WRITE_DATA_FILE":  "nvt_out.data",
        "RESTART_FILE_1":   "nvt_1.rst",
        "RESTART_FILE_2":   "nvt_2.rst",
        "RESTART_FREQ":     10000,
        "T_START":          300.0,
        "T_FINAL":          300.0,
        "T_DAMP":           100.0,
        "TIMESTEP":         1.0,
        "N_STEPS":          500000,
        "THERMO_FREQ":      1000,
        "DUMP_FREQ":        1000,
        "use_restart":      False,
        "use_shake":        True,
        "init_velocity":    None,  # None = don't set; float = temperature (K)
        "write_restart":    True,
        "use_gpu":          False,
        "use_pppm":         True,
    },
    "npt": {
        "LOG_FILE":         "npt.log",
        "LOG_APPEND":       False,
        "DUMP_FILE":        "npt.dump",
        "LAST_DUMP_FILE":   "npt_last.dump",
        "WRITE_DATA_FILE":  "npt_out.data",
        "RESTART_FILE_1":   "npt_1.rst",
        "RESTART_FILE_2":   "npt_2.rst",
        "RESTART_FREQ":     10000,
        "T_START":          300.0,
        "T_FINAL":          300.0,
        "T_DAMP":           100.0,
        "P_START":          1.0,
        "P_FINAL":          1.0,
        "P_DAMP":           1000.0,
        "TIMESTEP":         1.0,
        "N_STEPS":          500000,
        "THERMO_FREQ":      1000,
        "DUMP_FREQ":        1000,
        "use_restart":      False,
        "use_shake":        True,
        "init_velocity":    None,
        "write_restart":    True,
        "use_gpu":          False,  # CPU default: NPT + restart safe
        "use_pppm":         True,
    },
    "npt_compress": {
        "LOG_FILE":         "compress.log",
        "LOG_APPEND":       False,
        "DUMP_FILE":        "compress.dump",
        "LAST_DUMP_FILE":   "compress_last.dump",
        "WRITE_DATA_FILE":  "compressed.data",
        "RESTART_FILE_1":   "compress_1.rst",
        "RESTART_FILE_2":   "compress_2.rst",
        "RESTART_FREQ":     10000,
        "T_START":          600.0,
        "T_FINAL":          600.0,
        "T_DAMP":           100.0,
        "P_START":          1.0,
        "P_FINAL":          50000.0,
        "P_DAMP":           1000.0,
        "TIMESTEP":         1.0,
        "N_STEPS":          500000,
        "THERMO_FREQ":      1000,
        "DUMP_FREQ":        2000,
        "use_restart":      False,
        "use_shake":        True,
        "init_velocity":    600.0,   # set velocities at max_temp
        "write_restart":    True,
        "use_gpu":          False,
        "use_pppm":         False,   # lj/cut during compression
    },
    "npt_tg_step": {
        "LOG_FILE":         "tg_step.log",
        "LOG_APPEND":       True,    # append to shared log for the sweep
        "DUMP_FILE":        "tg_step.dump",
        "LAST_DUMP_FILE":   "tg_step_last.dump",
        "WRITE_DATA_FILE":  "tg_step_out.data",
        "T_TARGET":         300.0,
        "T_DAMP":           100.0,
        "P_TARGET":         1.0,
        "P_DAMP":           1000.0,
        "TIMESTEP":         1.0,
        "N_STEPS":          100000,
        "THERMO_FREQ":      500,
        "DUMP_FREQ":        2000,
        "use_restart":      False,
        "use_shake":        True,
        "init_velocity":    None,    # caller sets T_TARGET for velocity rescale
        "use_gpu":          True,    # no restarts so GPU is safe
        "use_pppm":         True,
    },
    # ── Müller-Plathe RNEMD (standard, single cell) ─────────────────────
    "nemd_thermal": {
        "LOG_FILE":         "nemd_mp.log",
        "LOG_APPEND":       False,
        "DUMP_FILE":        "nemd_mp.dump",
        "LAST_DUMP_FILE":   "nemd_mp_last.dump",
        "WRITE_DATA_FILE":  "nemd_mp_out.data",
        "TPROF_FILE":       "slabtemp.profile",
        "T_TARGET":         300.0,
        "T_DAMP":           100.0,
        "TIMESTEP":         0.2,     # 0.2 fs — SHAKE must be OFF for MP-RNEMD
        "N_STEPS":          5000000, # 1 ns at 0.2 fs
        "THERMO_FREQ":      1000,
        "DUMP_FREQ":        5000,
        "NEMD_N_SLABS":     20,      # even number; slab 0=cold, slab N/2=hot
        "NEMD_SWAP_FREQ":   1000,    # steps between KE swaps
        "NEMD_AXIS":        "z",
        # These are auto-calculated from system_info in _build_substitutions:
        "NEMD_INVSLAB":     None,    # 1/N_SLABS, auto from n_slabs
        "NEMD_AREA":        None,    # cross-section Ang^2, auto from box dims
        "use_restart":      False,
        "use_shake":        False,   # MUST be False — SHAKE corrupts MP swap
        "use_gpu":          False,
        "use_pppm":         True,
    },
    # ── Müller-Plathe RNEMD (replicated supercell) ───────────────────────
    "nemd_supercell": {
        "LOG_FILE":         "nemd_sc.log",
        "LOG_APPEND":       False,
        "DUMP_FILE":        "nemd_sc.dump",
        "LAST_DUMP_FILE":   "nemd_sc_last.dump",
        "WRITE_DATA_FILE":  "nemd_sc_out.data",
        "TPROF_FILE":       "slabtemp_sc.profile",
        "T_TARGET":         300.0,
        "T_DAMP":           100.0,
        "TIMESTEP":         0.2,
        "N_STEPS":          5000000,
        "THERMO_FREQ":      1000,
        "DUMP_FREQ":        5000,
        "NEMD_N_SLABS":     20,
        "NEMD_SWAP_FREQ":   1000,
        "NEMD_AXIS":        "z",
        "NEMD_INVSLAB":     None,
        "NEMD_AREA":        None,
        "NEMD_REP":         3,       # replication factor along NEMD_AXIS
        "NEMD_REP_OTHER":   1,       # replication along other axes
        "SUPERCELL_NOTE":   "Supercell pre-built by RadonPy poly.super_cell()",
        "use_restart":      False,
        "use_shake":        False,
        "use_gpu":          False,
        "use_pppm":         True,
    },
    # ── SLLOD shear viscosity NEMD ──────────────────────────────────────
    "nemd_shear": {
        "LOG_FILE":         "nemd_shear.log",
        "LOG_APPEND":       False,
        "DUMP_FILE":        "nemd_shear.dump",
        "LAST_DUMP_FILE":   "nemd_shear_last.dump",
        "WRITE_DATA_FILE":  "nemd_shear_out.data",
        "VPROF_FILE":       "velprofile_shear.profile",
        "T_START":          300.0,   # pre-equil NVT temperature (K)
        "T_FINAL":          300.0,   # SLLOD production temperature (K)
        "T_DAMP":           100.0,   # thermostat damping (fs)
        "TIMESTEP":         1.0,     # fs — SHAKE must be OFF
        "N_PRE_STEPS":      500000,  # 0.5 ns pre-equil at 1 fs
        "N_STEPS":          5000000, # 5 ns production at 1 fs
        "THERMO_FREQ":      1000,
        "DUMP_FREQ":        5000,
        # SHEAR_RATE in units of 1/fs (LAMMPS real units)
        # 1e-5 /fs = 1e10 s^-1 (typical polymer NEMD range)
        # 1e-4 /fs = 1e11 s^-1 (fast / non-Newtonian)
        # 1e-6 /fs = 1e9 s^-1  (slow / closer to Newtonian)
        "SHEAR_RATE":       1e-5,    # 1/fs = 1e10 s^-1 in SI
        "SHEAR_PLANE":      "xy",   # tilt component (xy, xz, or yz)
        "VPROF_N_BINS":     20,      # y-bins for velocity profile
        "VPROF_INVSLAB":    None,    # auto: 1/VPROF_N_BINS
        "VPROF_AXIS":       "y",    # gradient direction (y for xy shear)
        "use_restart":      False,
        "use_shake":        False,   # MUST be False — SLLOD incompatible with SHAKE
        "write_restart":    True,
        "use_gpu":          False,   # no restart GPU issues but SLLOD+GPU needs testing
        "use_pppm":         True,
    },
    # ── NVT Born matrix (Stage 8: glassy bulk modulus) ──────────────────
    "nvt_born": {
        "LOG_FILE":          "nvt_born.log",
        "LOG_APPEND":        False,
        "DUMP_FILE":         "nvt_born.dump",
        "LAST_DUMP_FILE":    "nvt_born_last.dump",
        "WRITE_DATA_FILE":   "nvt_born_out.data",
        "RESTART_FILE_1":    "nvt_born_1.rst",
        "RESTART_FILE_2":    "nvt_born_2.rst",
        "RESTART_FREQ":      50000,
        "T_START":           300.0,
        "T_FINAL":           300.0,
        "T_DAMP":            100.0,
        "TIMESTEP":          1.0,
        "N_STEPS":           4000000,   # 4 ns at 1 fs
        "THERMO_FREQ":       1000,
        "DUMP_FREQ":         5000,
        "BORN_NUMDIFF_DELTA": 0.0001,  # finite-diff displacement [Å]
        "BORN_EVERY":        10,        # sample Born every N steps
        "BORN_REPEAT":       100,       # samples per average block
        "BORN_FREQ":         1000,      # output period [steps]
        "BORN_MATRIX_FILE":  "born_matrix.dat",
        "use_restart":       False,
        "use_shake":         True,
        "init_velocity":     None,
        "write_restart":     True,
        "use_gpu":           False,     # long NVT + restart → CPU safe
        "use_pppm":          True,
    },
    # ── Uniaxial deformation (Stage 5b: elastic constants) ───────────────
    "npt_deform": {
        "LOG_FILE":         "npt_deform.log",
        "LOG_APPEND":       False,
        "DUMP_FILE":        "",           # disabled by default — log is sufficient
        "LAST_DUMP_FILE":   "npt_deform_last.dump",
        "WRITE_DATA_FILE":  "npt_deform_out.data",
        "T_TARGET":         300.0,
        "T_DAMP":           100.0,
        # STRAIN_RATE in 1/fs (LAMMPS real units).
        # K_deform_rate_inv_s = 1e8 s^-1 → 1e-7 /fs.
        "STRAIN_RATE":      1e-7,
        # N_STEPS = STRAIN_MAX / (STRAIN_RATE * TIMESTEP)
        # = 0.03 / (1e-7 * 1.0) = 300000 steps for 3% strain at 1e8 s^-1, 1 fs dt
        "N_STEPS":          300000,
        "N_EQ_STEPS":       200000,  # 0.2 ns NVT pre-equilibration
        "TIMESTEP":         1.0,
        "THERMO_FREQ":      100,     # ~3000 data points for stress-strain fit
        "DUMP_FREQ":        0,
        "use_shake":        True,
        "init_velocity":    None,    # velocities inherited from starting .data
        "use_gpu":          True,    # no restarts — GPU-safe
        "use_pppm":         True,
    },
    # ── Langevin direct-thermostat NEMD ──────────────────────────────────
    "nemd_langevin": {
        "LOG_FILE":         "nemd_lang.log",
        "LOG_APPEND":       False,
        "DUMP_FILE":        "nemd_lang.dump",
        "LAST_DUMP_FILE":   "nemd_lang_last.dump",
        "WRITE_DATA_FILE":  "nemd_lang_out.data",
        "TPROF_FILE":       "slabtemp_lang.profile",
        "T_TARGET":         300.0,   # mean temperature = (T_HOT+T_COLD)/2
        "T_HOT":            315.0,   # hot slab T (K)
        "T_COLD":           285.0,   # cold slab T (K)
        "T_DAMP_NVT":       100.0,   # pre-equil NVT damp (fs)
        "T_DAMP_LANGEVIN":  200.0,   # Langevin damp (fs) — looser than NVT
        "TIMESTEP":         1.0,     # 1.0 fs OK — SHAKE is allowed with Langevin
        "N_STEPS":          5000000,
        "THERMO_FREQ":      1000,
        "DUMP_FREQ":        5000,
        "NEMD_N_SLABS":     20,
        "NEMD_SWAP_FREQ":   1000,    # used only for tprof ave/chunk frequency
        "NEMD_AXIS":        "z",
        "NEMD_INVSLAB":     None,
        "NEMD_AREA":        None,
        # These are auto-calculated from system_info:
        "NEMD_AXIS_LO":     None,
        "NEMD_AXIS_MID":    None,
        "NEMD_AXIS_HI":     None,
        "SEED_HOT":         None,    # auto-generated random seed
        "SEED_COLD":        None,    # auto-generated random seed
        "use_restart":      False,
        "use_shake":        True,    # OK with Langevin
        "init_velocity":    300.0,
        "use_gpu":          False,
        "use_pppm":         True,
    },
}

TEMPLATE_DOCS = {
    "minimize":       "Energy minimization (CG). Use on fresh amorphous cell.",
    "nvt":            "NVT constant-volume dynamics. Use for heating/cooling ramps or fixed-T production.",
    "npt":            "NPT constant-pressure dynamics. Use for density equilibration. CPU+restart safe.",
    "npt_compress":   "NPT compression from low density. Uses lj/charmm/coul/charmm (short-range Coulomb, no PPPM). Compress to ~0.8 g/cm3.",
    "npt_tg_step":    "Single NPT step for Tg sweep. GPU-safe (no restarts). Chain for full T sweep.",
    "nemd_thermal":   "NEMD Muller-Plathe RNEMD thermal conductivity (single cell). SHAKE=OFF, dt=0.2fs.",
    "nemd_supercell": "NEMD Muller-Plathe on pre-replicated supercell (for short boxes). SHAKE=OFF, dt=0.2fs.",
    "nemd_langevin":  "NEMD direct Langevin thermostat method. SHAKE=OK, dt=1.0fs. Needs longer box.",
    "nemd_shear":     "NEMD SLLOD shear viscosity. fix deform xy + fix nvt/sllod. SHAKE=OFF, dt=1.0fs. Extracts eta, N1, N2.",
    "npt_deform":     "Uniaxial x-strain at constant rate (Stage 5b). NVT, no barostat. Records pxx/pyy/pzz for C11/C12 → K, G, E. GPU-safe (no restarts).",
    "nvt_born":       "NVT Born matrix (Stage 8, glassy only). compute born/matrix numdiff + stress-fluctuation → K_T. Requires EXTRA-COMPUTE. CPU run, 3–5 ns. Formula: K_T = K_Born + NkT/V − (V/kT)·Var(P).",
}


class ScriptGenerator:
    """
    Parses a RadonPy LAMMPS data file and generates filled-in .in scripts.
    """

    def __init__(self, data_file: str, templates_dir: Optional[str] = None):
        """
        Args:
            data_file:     Path to RadonPy-generated .data file (local or remote path).
            templates_dir: Override template directory (defaults to ./templates/).
        """
        self.data_file = data_file
        self.templates_dir = Path(templates_dir) if templates_dir else TEMPLATES_DIR
        self.system_info = {}   # populated by parse_data_file()

    # ─────────────────────────────────────────────────────────────────────────
    # Data File Parser
    # ─────────────────────────────────────────────────────────────────────────

    def parse_data_file(self, content: Optional[str] = None) -> dict:
        """
        Parse the header of a RadonPy LAMMPS data file to extract system info.

        Args:
            content: File content as string (if already loaded). If None,
                     reads self.data_file from disk.

        Returns:
            dict with keys:
                n_atoms, n_bonds, n_angles, n_dihedrals, n_impropers
                n_atom_types, n_bond_types, n_angle_types,
                n_dihedral_types, n_improper_types
                box_x, box_y, box_z  (full box lengths in Angstrom)
                atom_type_names      (list of strings, e.g. ['hc', 'c3', 'ca'])
                has_charges          (bool)
                generated_by         (str)
        """
        if content is None:
            with open(self.data_file, "r") as f:
                content = f.read()

        info = {}
        lines = content.splitlines()

        # Header comment
        info["generated_by"] = lines[0].strip() if lines else "unknown"

        # Count lines (integers before keywords)
        count_patterns = {
            "n_atoms":          r"(\d+)\s+atoms",
            "n_bonds":          r"(\d+)\s+bonds",
            "n_angles":         r"(\d+)\s+angles",
            "n_dihedrals":      r"(\d+)\s+dihedrals",
            "n_impropers":      r"(\d+)\s+impropers",
            "n_atom_types":     r"(\d+)\s+atom types",
            "n_bond_types":     r"(\d+)\s+bond types",
            "n_angle_types":    r"(\d+)\s+angle types",
            "n_dihedral_types": r"(\d+)\s+dihedral types",
            "n_improper_types": r"(\d+)\s+improper types",
        }
        for key, pattern in count_patterns.items():
            m = re.search(pattern, content)
            info[key] = int(m.group(1)) if m else 0

        # Box dimensions
        xm = re.search(r"([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+xlo xhi", content)
        ym = re.search(r"([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+ylo yhi", content)
        zm = re.search(r"([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+zlo zhi", content)
        info["box_x"] = float(xm.group(2)) - float(xm.group(1)) if xm else 0.0
        info["box_y"] = float(ym.group(2)) - float(ym.group(1)) if ym else 0.0
        info["box_z"] = float(zm.group(2)) - float(zm.group(1)) if zm else 0.0

        # Atom type names from Masses section comments (e.g. "# hc,0")
        atom_type_names = []
        in_masses = False
        for line in lines:
            if line.strip() == "Masses":
                in_masses = True
                continue
            if in_masses:
                if line.strip() == "" and atom_type_names:
                    break
                m = re.match(r"\s*\d+\s+[\d.]+\s+#\s*(\w+)", line)
                if m:
                    # Strip trailing ",0" or similar suffixes
                    raw_name = m.group(1).split(",")[0]
                    atom_type_names.append(raw_name)
        info["atom_type_names"] = atom_type_names

        # Detect if system has charges (atom style full -> column 4 is charge)
        info["has_charges"] = True  # RadonPy always uses atom_style full

        # Estimate H mass atoms for SHAKE
        h_types = [i+1 for i, name in enumerate(atom_type_names)
                   if name.startswith("h")]
        info["h_type_ids"] = h_types

        self.system_info = info
        return info

    def validate_data_file(
        self,
        content: Optional[str] = None,
        h_type_ids: Optional[list] = None,
        backbone_types: Optional[list] = None,
        atom_type_pairs: Optional[list] = None,
        lj_cutoff: float = 12.0,
        charge_tol: float = 0.01,
    ) -> dict:
        """
        Systematic pre-simulation validation of a LAMMPS data file.

        Runs parse_data_file first (or uses cached system_info), then performs
        a second pass over the full file content to check sections that the
        header parser skips: Atoms (charges), and all Coeffs sections.

        Args:
            content:         File content as string. If None, reads self.data_file.
            h_type_ids:      User-supplied SHAKE H type IDs to validate.
            backbone_types:  User-supplied backbone atom type IDs to validate.
            atom_type_pairs: User-supplied RDF atom type pairs to validate.
            lj_cutoff:       LJ cutoff in Å (default 12.0 for GAFF2 lj/charmm).
            charge_tol:      Maximum allowed |net charge| in e (default 0.01).

        Returns:
            dict with:
                errors   — list of blocking issues (submission should be refused)
                warnings — list of non-blocking concerns
                stats    — computed values used in checks (net_charge, density, etc.)
                valid    — bool: True only when errors is empty
        """
        if content is None:
            if self.data_file:
                with open(self.data_file, "r") as f:
                    content = f.read()
            else:
                return {"errors": ["No content or data_file provided"], "warnings": [], "valid": False}

        # Ensure header is parsed
        if not self.system_info:
            self.parse_data_file(content=content)
        info = self.system_info

        errors   = []
        warnings = []
        stats    = {}

        lines = content.splitlines()
        n_atom_types = info.get("n_atom_types", 0)
        atom_type_names = info.get("atom_type_names", [])

        # ── 1. Header sanity ──────────────────────────────────────────────────
        if info.get("n_atoms", 0) == 0:
            errors.append("n_atoms = 0 — data file is empty or unparseable")
        if n_atom_types == 0:
            errors.append("n_atom_types = 0 — Masses section missing or unreadable")

        box_min = min(info.get("box_x", 0), info.get("box_y", 0), info.get("box_z", 0))
        if box_min <= 0:
            errors.append(f"Box dimension <= 0 — file may be truncated")
        elif box_min < 2 * lj_cutoff:
            errors.append(
                f"Minimum box side {box_min:.1f} Å < 2×cutoff ({2*lj_cutoff:.1f} Å). "
                f"LAMMPS requires box > 2×cutoff in all periodic directions."
            )
        stats["box_min_A"] = round(box_min, 2)
        stats["lj_cutoff_A"] = lj_cutoff

        n_bonds = info.get("n_bonds", 0)
        n_atoms = info.get("n_atoms", 0)
        if n_atoms > 0 and n_bonds > 0:
            ratio = n_bonds / n_atoms
            stats["bond_atom_ratio"] = round(ratio, 3)
            if ratio < 0.5:
                warnings.append(
                    f"bond/atom ratio = {ratio:.2f} (expected ≥ 0.8 for polymers) — "
                    f"possible disconnected atoms or missing bonds section"
                )
            elif ratio > 3.0:
                warnings.append(
                    f"bond/atom ratio = {ratio:.2f} (expected ≤ 2.5 for organic polymers) — "
                    f"possible duplicate bonds"
                )

        # ── 2. Coeff section completeness ─────────────────────────────────────
        coeff_checks = [
            ("Pair Coeffs",     "n_atom_types",     info.get("n_atom_types", 0)),
            ("Bond Coeffs",     "n_bond_types",     info.get("n_bond_types", 0)),
            ("Angle Coeffs",    "n_angle_types",    info.get("n_angle_types", 0)),
            ("Dihedral Coeffs", "n_dihedral_types", info.get("n_dihedral_types", 0)),
            ("Improper Coeffs", "n_improper_types", info.get("n_improper_types", 0)),
        ]
        data_line_re = re.compile(r"^\s*\d+\s+[\d.eE+\-]")
        current_section = None
        section_counts = {}

        for line in lines:
            stripped = line.strip()
            # Detect section headers (e.g. "Pair Coeffs", "Bond Coeffs # harmonic")
            matched_section = None
            for sec_name, _, _ in coeff_checks:
                if stripped.startswith(sec_name):
                    matched_section = sec_name
                    break
            if matched_section:
                current_section = matched_section
                section_counts[current_section] = 0
                continue
            # Blank line ends current coeff section
            if stripped == "" and current_section:
                if section_counts[current_section] > 0:
                    current_section = None
                continue
            if current_section and data_line_re.match(line):
                section_counts[current_section] = section_counts.get(current_section, 0) + 1

        for sec_name, count_key, expected in coeff_checks:
            if expected == 0:
                continue  # no such connectivity in this system
            found = section_counts.get(sec_name, 0)
            stats[f"{sec_name.replace(' ', '_')}_found"] = found
            if found == 0:
                errors.append(
                    f"'{sec_name}' section missing or empty — "
                    f"expected {expected} entries"
                )
            elif found != expected:
                errors.append(
                    f"'{sec_name}' has {found} entries but header says {expected} types — "
                    f"force field is incomplete"
                )

        # ── 3. Charge neutrality (parse Atoms section) ────────────────────────
        in_atoms = False
        atoms_seen_data = False
        net_charge = 0.0
        charge_parse_ok = False
        type_counts: dict = {}
        masses_by_type: dict = {}

        # Build mass lookup from Masses section
        in_masses_sec = False
        masses_seen_data = False
        for line in lines:
            stripped = line.strip()
            if stripped == "Masses":
                in_masses_sec = True
                masses_seen_data = False
                continue
            if in_masses_sec:
                if stripped == "" and masses_seen_data:
                    in_masses_sec = False
                    continue
                m = re.match(r"^\s*(\d+)\s+([\d.]+)", line)
                if m:
                    masses_seen_data = True
                    masses_by_type[int(m.group(1))] = float(m.group(2))

        for line in lines:
            stripped = line.strip()
            if stripped == "Atoms" or stripped.startswith("Atoms #"):
                in_atoms = True
                atoms_seen_data = False
                continue
            if in_atoms:
                if stripped == "" and atoms_seen_data:
                    in_atoms = False
                    continue
                if stripped == "" or stripped.startswith("#"):
                    continue
                parts = stripped.split()
                if len(parts) >= 4:
                    try:
                        atype = int(parts[2])
                        charge = float(parts[3])
                        net_charge += charge
                        type_counts[atype] = type_counts.get(atype, 0) + 1
                        atoms_seen_data = True
                        charge_parse_ok = True
                    except (ValueError, IndexError):
                        pass

        stats["net_charge_e"] = round(net_charge, 4)
        stats["charge_parse_ok"] = charge_parse_ok

        if not charge_parse_ok:
            warnings.append("Could not parse Atoms section — charge neutrality not verified")
        elif abs(net_charge) > charge_tol:
            errors.append(
                f"Net charge = {net_charge:+.4f} e (tolerance ±{charge_tol} e). "
                f"PPPM requires a charge-neutral cell. "
                f"Check RESP convergence or add a neutralising counterion."
            )

        # ── 4. Density plausibility ───────────────────────────────────────────
        if type_counts and masses_by_type:
            total_mass_amu = sum(
                type_counts.get(t, 0) * masses_by_type.get(t, 0.0)
                for t in masses_by_type
            )
            box_vol_A3 = (
                info.get("box_x", 0) * info.get("box_y", 0) * info.get("box_z", 0)
            )
            if box_vol_A3 > 0 and total_mass_amu > 0:
                # 1 amu/Å³ = 1.66054 g/cm³
                density = total_mass_amu / box_vol_A3 * 1.66054
                stats["density_g_cm3"] = round(density, 4)
                if density < 0.1:
                    warnings.append(
                        f"Density = {density:.3f} g/cm³ — unusually low. "
                        f"Cell may be over-expanded or have vacuum voids."
                    )
                elif density > 2.5:
                    warnings.append(
                        f"Density = {density:.3f} g/cm³ — unusually high. "
                        f"Cell may be over-compressed or overlapping atoms."
                    )

        # ── 5. User-supplied type ID validation ───────────────────────────────
        def _check_type_ids(ids, label):
            if not ids:
                return
            bad = [t for t in ids if not (1 <= t <= n_atom_types)]
            if bad:
                errors.append(
                    f"{label} contains type IDs out of range: {bad}. "
                    f"Valid range is [1, {n_atom_types}]."
                )

        _check_type_ids(h_type_ids, "h_type_ids (SHAKE)")
        _check_type_ids(backbone_types, "backbone_types")
        if atom_type_pairs:
            flat = [t for pair in atom_type_pairs for t in pair]
            _check_type_ids(flat, "atom_type_pairs")

        # ── 6. h_type_ids mass check (should be H ≈ 1.008 amu) ───────────────
        if h_type_ids and masses_by_type:
            for tid in h_type_ids:
                m = masses_by_type.get(tid)
                if m is not None and m > 2.5:
                    name = atom_type_names[tid - 1] if tid - 1 < len(atom_type_names) else "?"
                    warnings.append(
                        f"h_type_ids includes type {tid} ({name}, mass={m:.3f} amu) "
                        f"which is heavier than H (< 2.5 amu). SHAKE constraint may be wrong."
                    )

        # ── 7. backbone_types — warn if pointing at H atoms ───────────────────
        if backbone_types and atom_type_names:
            for tid in backbone_types:
                if 1 <= tid <= len(atom_type_names):
                    name = atom_type_names[tid - 1]
                    if name.startswith("h"):
                        warnings.append(
                            f"backbone_types includes type {tid} ({name}) which looks like "
                            f"a hydrogen (name starts with 'h'). "
                            f"End-to-end vectors and P2 order will be wrong."
                        )

        return {
            "valid":    len(errors) == 0,
            "errors":   errors,
            "warnings": warnings,
            "stats":    stats,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Script Generator
    # ─────────────────────────────────────────────────────────────────────────

    def generate(
        self,
        template_name: str,
        output_path: str,
        params: dict,
        data_file_override: Optional[str] = None,
    ) -> str:
        """
        Generate a filled LAMMPS .in script from a template.

        Args:
            template_name:      One of: minimize, nvt, npt, npt_compress,
                                npt_tg_step, nemd_thermal, nemd_supercell,
                                nemd_langevin.
            output_path:        Where to write the generated script (local path).
            params:             Dict of parameter overrides (merged with defaults).
            data_file_override: If provided, use this path in the DATA_FILE field
                                instead of self.data_file (useful for remote paths).

        Returns:
            The rendered script as a string.
        """
        if template_name not in TEMPLATE_DEFAULTS:
            raise ValueError(
                f"Unknown template '{template_name}'. "
                f"Available: {list(TEMPLATE_DEFAULTS.keys())}"
            )

        # Merge defaults with caller overrides
        cfg = {**TEMPLATE_DEFAULTS[template_name], **params}

        # Data file path
        data_file = data_file_override or self.data_file

        # Build all substitution blocks
        subs = self._build_substitutions(template_name, cfg, data_file)

        # Staircase expansion: npt_tg_step + T_END + T_STEP → full cooling loop
        if (template_name == "npt_tg_step"
                and "T_END" in params and "T_STEP" in params):
            script = self._generate_tg_staircase(cfg, subs, output_path)
            return script

        # Load template
        tpl_path = self.templates_dir / f"{template_name}.in"
        with open(tpl_path, "r") as f:
            template = f.read()

        # Fill template (simple format-style substitution)
        script = self._fill_template(template, subs)

        # Write output
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(script)

        return script

    def _generate_tg_staircase(self, cfg: dict, subs: dict, output_path: str) -> str:
        """
        Generate a full Tg cooling staircase script using a LAMMPS variable-index loop.
        Triggered when T_END and T_STEP are both present in the caller's params.
        Velocities are initialized once at T_START; subsequent steps inherit momenta.
        """
        t_start    = float(cfg.get("T_START",       450.0))
        t_end      = float(cfg.get("T_END",         100.0))
        t_step     = float(cfg.get("T_STEP",         20.0))
        n_steps    = int(cfg.get("N_STEPS_PER_T",
                         cfg.get("N_STEPS",         500000)))
        p_target   = cfg.get("P_TARGET",   1.0)
        p_damp     = cfg.get("P_DAMP",  1000.0)
        t_damp     = cfg.get("T_DAMP",   100.0)
        timestep   = cfg.get("TIMESTEP",    1.0)
        thermo_freq = int(cfg.get("THERMO_FREQ", 500))
        log_file   = subs["LOG_FILE"]
        write_per_t_dump = bool(cfg.get("WRITE_PER_T_DUMP", False))
        per_t_dump_file  = str(cfg.get("PER_T_DUMP_FILE", "per_t_structs.dump"))

        # Build temperature list: T_START down to T_END, always include T_END
        temps: list[float] = []
        t = t_start
        while t > t_end + 1e-6:
            temps.append(t)
            t -= t_step
        if not temps or abs(temps[-1] - t_end) > 1e-6:
            temps.append(t_end)

        temp_list_str = " ".join(str(int(t) if t == int(t) else t) for t in temps)

        seed = random.randint(10000, 999999)

        if write_per_t_dump:
            per_t_dump_block = (
                f"  dump per_t_snap all atom 1 {per_t_dump_file}\n"
                f"  dump_modify per_t_snap append yes\n"
                f"  run 0\n"
                f"  undump per_t_snap\n"
            )
        else:
            per_t_dump_block = ""

        script = f"""\
# ============================================================
# PolyJarvis LAMMPS Engine - Tg Sweep Staircase
# T_START={t_start} → T_END={t_end} K, step={t_step} K
# {len(temps)} temperature points × {n_steps} steps/T
# ============================================================

log {log_file} append
units real
atom_style full
boundary p p p

# --- Force Field Styles ---
{subs["PAIR_STYLE_BLOCK"]}
dielectric 1.000000
bond_style {subs["BOND_STYLE"]}
angle_style {subs["ANGLE_STYLE"]}
dihedral_style {subs["DIHEDRAL_STYLE"]}
improper_style {subs["IMPROPER_STYLE"]}
{subs["SPECIAL_BONDS"]}
pair_modify {subs["PAIR_MODIFY"]}
neighbor 2.0 bin
neigh_modify delay 0 every 1 check yes
neigh_modify one 4000
{subs["GPU_PACKAGE"]}

read_data {subs["DATA_FILE"]}
{subs["INCLUDE_PARAMS_BLOCK"]}

# --- Thermo Output ---
thermo_style custom step time temp press enthalpy etotal ke pe ebond eangle edihed eimp evdwl ecoul elong etail vol lx ly lz density pxx pyy pzz
thermo_modify flush yes
thermo {thermo_freq}

# --- Velocity initialization at T_START (once only — Rule A) ---
velocity all create {t_start} {seed} mom yes rot yes dist gaussian

# --- Temperature staircase (inherits momenta across steps — Rule A) ---
variable temps index {temp_list_str}
label TEMP_LOOP
  timestep {timestep}
  fix npt_tg all npt temp ${{temps}} ${{temps}} {t_damp} iso {p_target} {p_target} {p_damp}
  run {n_steps}
  unfix npt_tg
{per_t_dump_block}  print "STAGE COMPLETE: Tg step T=${{temps}}K P={p_target}atm steps={n_steps}"
  next temps
  jump SELF TEMP_LOOP

write_data tg_step_out.data
"""

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(script)

        return script

    def _build_substitutions(self, template_name: str, cfg: dict, data_file: str) -> dict:
        """Build the full substitution dictionary for the given template and config."""
        subs = {}

        # ── File paths ────────────────────────────────────────────────────
        subs["DATA_FILE"]        = data_file
        subs["LOG_FILE"]         = cfg.get("LOG_FILE", f"{template_name}.log")
        subs["LOG_APPEND"]       = "append" if cfg.get("LOG_APPEND", False) else ""
        subs["DUMP_FILE"]        = cfg.get("DUMP_FILE", f"{template_name}.dump")
        subs["LAST_DUMP_FILE"]   = cfg.get("LAST_DUMP_FILE", f"{template_name}_last.dump")
        subs["WRITE_DATA_FILE"]  = cfg.get("WRITE_DATA_FILE", f"{template_name}_out.data")

        # ── Force field styles ────────────────────────────────────────────
        use_pcff = cfg.get("use_pcff", False)
        use_opls   = cfg.get("use_opls",   False)
        use_trappe = cfg.get("use_trappe", False)
        if use_pcff:
            ff_styles = PCFF_STYLES
        elif use_opls:
            ff_styles = OPLS_STYLES
        elif use_trappe:
            ff_styles = TRAPPE_UA_STYLES
        else:
            ff_styles = GAFF2_STYLES
        subs["BOND_STYLE"]      = cfg.get("BOND_STYLE",     ff_styles["BOND_STYLE"])
        subs["ANGLE_STYLE"]     = cfg.get("ANGLE_STYLE",    ff_styles["ANGLE_STYLE"])
        subs["DIHEDRAL_STYLE"]  = cfg.get("DIHEDRAL_STYLE", ff_styles["DIHEDRAL_STYLE"])
        subs["IMPROPER_STYLE"]  = cfg.get("IMPROPER_STYLE", ff_styles["IMPROPER_STYLE"])

        # ── Pair style block (PPPM or cutoff) ────────────────────────────
        use_pppm = cfg.get("use_pppm", True)
        if use_trappe:
            cutoff = cfg.get("LJ_CUTOFF", 14.0)
            subs["PAIR_STYLE_BLOCK"] = f"pair_style lj/cut {cutoff}"
        elif use_pcff:
            subs["PAIR_STYLE_BLOCK"] = PAIR_STYLE_PCFF_PPPM if use_pppm else PAIR_STYLE_PCFF_CUTOFF
        elif use_opls:
            subs["PAIR_STYLE_BLOCK"] = PAIR_STYLE_OPLS_PPPM if use_pppm else PAIR_STYLE_OPLS_CUTOFF
        else:
            subs["PAIR_STYLE_BLOCK"] = PAIR_STYLE_PPPM if use_pppm else PAIR_STYLE_CUTOFF

        # ── EMC params file include block ─────────────────────────────────
        params_file = cfg.get("params_file", "")
        if params_file:
            subs["INCLUDE_PARAMS_BLOCK"] = f"include {params_file}"
        else:
            subs["INCLUDE_PARAMS_BLOCK"] = ""

        # ── GPU package ───────────────────────────────────────────────────
        # engine selects how the deck loads the accelerator. Absent → derive from use_gpu so
        # existing callers stay byte-identical (gpu ⇒ "package gpu 1 neigh no", else CPU).
        #   gpu    : GPU package — pairwise forces on GPU, bonded/kspace/neigh on CPU.
        #            EXCEPT TraPPE-UA (lj/cut, no kspace): neighbor build is ~71% of the loop, so
        #            it offloads to the GPU too (`neigh yes`, arm A1 → 3.7x vs CPU). PPPM classes
        #            keep `neigh no` (the parity-validated A0 baseline; KOKKOS handles their offload).
        #   kokkos : NO `package gpu` line; the KOKKOS package is loaded by `-pk kokkos` on the
        #            command line and `-sf kk` rewrites pair/bonded/kspace/neigh to /kk. The deck
        #            keeps plain style names (e.g. `kspace_style pppm`) so the suffix machinery
        #            rewrites them — an explicit `/kk` style here would conflict with `-sf kk`.
        #   cpu    : no accelerator package.
        # use_gpu=False stages (NPT+restart, born numdiff) stay CPU regardless of engine — those
        # are intentionally off-GPU. Only GPU-enabled stages honor the engine choice.
        engine = cfg.get("engine", "gpu") if cfg.get("use_gpu", False) else "cpu"
        if engine == "kokkos":
            subs["GPU_PACKAGE"] = "# KOKKOS: package loaded via -pk kokkos on the command line"
        elif engine == "gpu":
            neigh = "yes" if cfg.get("use_trappe", False) else "no"
            subs["GPU_PACKAGE"] = f"package gpu 1 neigh {neigh}"
        else:
            subs["GPU_PACKAGE"] = "# GPU disabled (CPU run)"

        # ── Read command ──────────────────────────────────────────────────
        if cfg.get("use_restart", False):
            subs["READ_COMMAND"] = "read_restart"
        else:
            subs["READ_COMMAND"] = "read_data"

        # ── Restart block ─────────────────────────────────────────────────
        if cfg.get("write_restart", True) and template_name not in ("npt_tg_step", "nemd_thermal", "minimize", "npt_deform"):
            rst1 = cfg.get("RESTART_FILE_1", f"{template_name}_1.rst")
            rst2 = cfg.get("RESTART_FILE_2", f"{template_name}_2.rst")
            freq = cfg.get("RESTART_FREQ", 10000)
            subs["RESTART_BLOCK"] = f"restart {freq} {rst1} {rst2}"
            subs["RESTART_FILE_1"] = rst1
            subs["RESTART_FILE_2"] = rst2
            subs["RESTART_FREQ"]   = freq
        else:
            subs["RESTART_BLOCK"]  = "# No restart checkpointing"
            subs["RESTART_FILE_1"] = ""
            subs["RESTART_FILE_2"] = ""
            subs["RESTART_FREQ"]   = 0

        # ── SHAKE block ───────────────────────────────────────────────────
        if cfg.get("use_trappe") and cfg.get("use_shake"):
            # TraPPE-UA has no explicit H atoms; constrain C-C bond types by ID
            bond_ids = cfg.get("shake_bond_type_ids", [cfg.get("shake_bond_type_id", 1)])
            b_args = " ".join(f"b {bid}" for bid in bond_ids)
            subs["SHAKE_BLOCK"]   = f"fix shake_fix all shake 1e-4 1000 0 {b_args}"
            subs["UNSHAKE_BLOCK"] = "unfix shake_fix"
        elif cfg.get("use_shake", True):
            # SHAKE constrains H-X bonds (m 1.008 targets all hydrogen mass)
            subs["SHAKE_BLOCK"]   = "fix shake_fix all shake 1e-4 1000 0 m 1.008"
            subs["UNSHAKE_BLOCK"] = "unfix shake_fix"
        else:
            subs["SHAKE_BLOCK"]   = "# SHAKE disabled"
            subs["UNSHAKE_BLOCK"] = ""

        # ── Initial velocity ──────────────────────────────────────────────
        init_v = cfg.get("init_velocity", None)
        if init_v is not None:
            seed = random.randint(10000, 999999)
            subs["INIT_VELOCITY_BLOCK"] = (
                f"velocity all create {init_v} {seed} mom yes rot yes dist gaussian"
            )
        else:
            subs["INIT_VELOCITY_BLOCK"] = "# Velocities read from data file"

        # ── Thermodynamic parameters ───────────────────────────────────────
        subs["TIMESTEP"]    = cfg.get("TIMESTEP",    1.0)
        subs["N_STEPS"]     = cfg.get("N_STEPS",     500000)
        subs["THERMO_FREQ"] = cfg.get("THERMO_FREQ", 1000)
        subs["DUMP_FREQ"]   = cfg.get("DUMP_FREQ",   1000)

        # ── NVT / NPT thermostat/barostat ─────────────────────────────────
        subs["T_START"]  = cfg.get("T_START",  cfg.get("T_TARGET", 300.0))
        subs["T_FINAL"]  = cfg.get("T_FINAL",  cfg.get("T_TARGET", 300.0))
        subs["T_TARGET"] = cfg.get("T_TARGET", cfg.get("T_START",  300.0))
        subs["T_DAMP"]   = cfg.get("T_DAMP",   100.0)
        subs["P_START"]  = cfg.get("P_START",  cfg.get("P_TARGET", 1.0))
        subs["P_FINAL"]  = cfg.get("P_FINAL",  cfg.get("P_TARGET", 1.0))
        subs["P_TARGET"] = cfg.get("P_TARGET", cfg.get("P_START",  1.0))
        subs["P_DAMP"]   = cfg.get("P_DAMP",   1000.0)

        # ── Minimization ──────────────────────────────────────────────────
        subs["MIN_STYLE"] = cfg.get("MIN_STYLE", "cg")
        subs["ETOL"]      = cfg.get("ETOL",      1e-6)
        subs["FTOL"]      = cfg.get("FTOL",      1e-6)
        subs["MAXITER"]   = cfg.get("MAXITER",   50000)
        subs["MAXEVAL"]   = cfg.get("MAXEVAL",   100000)

        # ── NEMD shared ────────────────────────────────────────────────────
        n_slabs    = cfg.get("NEMD_N_SLABS",   20)
        axis       = cfg.get("NEMD_AXIS",      "z")
        swap_freq  = cfg.get("NEMD_SWAP_FREQ", 1000)

        subs["NEMD_N_SLABS"]   = n_slabs
        subs["NEMD_SWAP_FREQ"] = swap_freq
        subs["NEMD_AXIS"]      = axis
        subs["TPROF_FILE"]     = cfg.get("TPROF_FILE", "slabtemp.profile")

        # Auto-calculate invslab (1/N_SLABS for reduced-coord bin width)
        invslab = cfg.get("NEMD_INVSLAB") or round(1.0 / n_slabs, 6)
        subs["NEMD_INVSLAB"] = invslab

        # Auto-calculate cross-sectional area perpendicular to heat flux axis
        box_x = self.system_info.get("box_x", 0.0)
        box_y = self.system_info.get("box_y", 0.0)
        box_z = self.system_info.get("box_z", 0.0)
        if cfg.get("NEMD_AREA") is not None:
            area = cfg["NEMD_AREA"]
        elif axis == "z" and box_x > 0 and box_y > 0:
            area = round(box_x * box_y, 4)
        elif axis == "y" and box_x > 0 and box_z > 0:
            area = round(box_x * box_z, 4)
        elif axis == "x" and box_y > 0 and box_z > 0:
            area = round(box_y * box_z, 4)
        else:
            area = 0.0  # caller must provide if box not parsed
        subs["NEMD_AREA"] = area

        # Supercell-specific
        subs["NEMD_REP"]       = cfg.get("NEMD_REP",       3)
        subs["NEMD_REP_OTHER"] = cfg.get("NEMD_REP_OTHER", 1)
        subs["SUPERCELL_NOTE"] = cfg.get("SUPERCELL_NOTE", "Supercell pre-built by RadonPy poly.super_cell()")

        # Langevin-specific temperatures and region bounds
        t_target = cfg.get("T_TARGET", 300.0)
        subs["T_HOT"]           = cfg.get("T_HOT",  t_target + 15.0)
        subs["T_COLD"]          = cfg.get("T_COLD", t_target - 15.0)
        subs["T_DAMP_NVT"]      = cfg.get("T_DAMP_NVT",      100.0)
        subs["T_DAMP_LANGEVIN"] = cfg.get("T_DAMP_LANGEVIN", 200.0)

        # Auto-calculate box bounds along NEMD_AXIS for Langevin region definitions
        # These map to {NEMD_AXIS_LO}, {NEMD_AXIS_MID}, {NEMD_AXIS_HI}
        # We need the actual lo/hi values, not just box length.
        # Use 0.0 as lo (RadonPy boxes typically start near 0), mid = box/2, hi = box
        if axis == "z":
            box_len = box_z
        elif axis == "y":
            box_len = box_y
        else:
            box_len = box_x

        axis_lo  = cfg.get("NEMD_AXIS_LO")  or 0.0
        axis_hi  = cfg.get("NEMD_AXIS_HI")  or round(box_len, 4)
        axis_mid = cfg.get("NEMD_AXIS_MID") or round(box_len / 2.0, 4)
        subs["NEMD_AXIS_LO"]  = axis_lo
        subs["NEMD_AXIS_MID"] = axis_mid
        subs["NEMD_AXIS_HI"]  = axis_hi

        # Random seeds for Langevin thermostats
        subs["SEED_HOT"]  = cfg.get("SEED_HOT")  or random.randint(10000, 999999)
        subs["SEED_COLD"] = cfg.get("SEED_COLD") or random.randint(10000, 999999)

        # Legacy placeholder kept for backward compat (old nemd_thermal used these)
        subs["NEMD_BIN_WIDTH"] = cfg.get("NEMD_BIN_WIDTH", round(box_len / n_slabs, 4) if box_len > 0 else 2.0)
        subs["NEMD_HEAT_RATE"] = cfg.get("NEMD_HEAT_RATE", 0.0)

        # ── Born matrix NVT specifics (nvt_born) ─────────────────────────────
        subs["BORN_NUMDIFF_DELTA"] = cfg.get("BORN_NUMDIFF_DELTA", 0.0001)
        subs["BORN_EVERY"]         = cfg.get("BORN_EVERY",         10)
        subs["BORN_REPEAT"]        = cfg.get("BORN_REPEAT",        100)
        subs["BORN_FREQ"]          = cfg.get("BORN_FREQ",          1000)
        subs["BORN_MATRIX_FILE"]   = cfg.get("BORN_MATRIX_FILE",   "born_matrix.dat")

        # ── Uniaxial deformation specifics (npt_deform) ──────────────────────
        subs["STRAIN_RATE"]  = cfg.get("STRAIN_RATE", 1e-7)
        subs["N_EQ_STEPS"]   = cfg.get("N_EQ_STEPS",  200000)

        # ── SLLOD shear viscosity specifics ──────────────────────────────────
        subs["SHEAR_RATE"]    = cfg.get("SHEAR_RATE",   1e-5)
        subs["SHEAR_PLANE"]   = cfg.get("SHEAR_PLANE",  "xy")
        subs["N_PRE_STEPS"]   = cfg.get("N_PRE_STEPS",  500000)
        subs["VPROF_FILE"]    = cfg.get("VPROF_FILE",   "velprofile_shear.profile")
        subs["VPROF_N_BINS"]  = cfg.get("VPROF_N_BINS", 20)
        subs["VPROF_AXIS"]    = cfg.get("VPROF_AXIS",   "y")
        # Auto VPROF_INVSLAB from VPROF_N_BINS
        vprof_n_bins = cfg.get("VPROF_N_BINS", 20)
        subs["VPROF_INVSLAB"] = cfg.get("VPROF_INVSLAB") or round(1.0 / vprof_n_bins, 6)

        # ── Conditional dump block (for npt_tg_step and future templates) ──
        # When DUMP_FREQ=0 or DUMP_FILE="", omit dump/undump/write_dump entirely.
        # LAMMPS rejects dump frequency=0; thermo-only runs must skip the command.
        dump_freq = int(cfg.get("DUMP_FREQ", 1000))
        dump_file = str(subs.get("DUMP_FILE", "")).strip()
        last_dump_file = str(subs.get("LAST_DUMP_FILE", f"{template_name}_last.dump")).strip()
        if dump_freq > 0 and dump_file:
            subs["DUMP_BLOCK"] = (
                f"dump dump_tg all custom {dump_freq} {dump_file} "
                f"id type mol x y z ix iy iz vx vy vz"
            )
            subs["UNDUMP_BLOCK"]    = "undump dump_tg"
            subs["LAST_DUMP_BLOCK"] = (
                f"write_dump all custom {last_dump_file} "
                f"id type mol x y z xu yu zu vx vy vz modify sort id"
            )
        else:
            subs["DUMP_BLOCK"]      = "# Dump disabled (thermo-only run)"
            subs["UNDUMP_BLOCK"]    = ""
            subs["LAST_DUMP_BLOCK"] = ""

        # ── Common placeholders present in all templates ───────────────────
        if use_pcff:
            default_sb, default_pm = PCFF_SPECIAL_BONDS, PCFF_PAIR_MODIFY
        elif use_opls:
            default_sb, default_pm = OPLS_SPECIAL_BONDS, OPLS_PAIR_MODIFY
        elif use_trappe:
            default_sb, default_pm = TRAPPE_SPECIAL_BONDS, TRAPPE_PAIR_MODIFY
        else:
            default_sb, default_pm = GAFF2_SPECIAL_BONDS, GAFF2_PAIR_MODIFY
        subs["SPECIAL_BONDS"]  = cfg.get("SPECIAL_BONDS", default_sb)
        subs["PAIR_MODIFY"]    = cfg.get("PAIR_MODIFY",   default_pm)
        subs["NEIGHBOR_SKIN"]  = cfg.get("NEIGHBOR_SKIN", DEFAULT_NEIGHBOR)
        subs["NEIGH_MODIFY"]   = cfg.get("NEIGH_MODIFY",  DEFAULT_NEIGH_MODIFY)
        subs["NEIGH_ONE"]      = cfg.get("NEIGH_ONE",     DEFAULT_NEIGH_ONE)

        return subs

    def _fill_template(self, template: str, subs: dict) -> str:
        """Simple string substitution of {KEY} placeholders."""
        result = template
        for key, value in subs.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Introspection helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def list_templates() -> dict:
        """Return all available templates with their descriptions."""
        return TEMPLATE_DOCS

    @staticmethod
    def get_template_defaults(template_name: str) -> dict:
        """Return the default parameter set for a given template."""
        if template_name not in TEMPLATE_DEFAULTS:
            raise ValueError(f"Unknown template '{template_name}'")
        return dict(TEMPLATE_DEFAULTS[template_name])

    def get_system_info(self) -> dict:
        """Return parsed system info (call parse_data_file first)."""
        return self.system_info
