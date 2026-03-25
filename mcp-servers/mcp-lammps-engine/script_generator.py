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
GAFF2_SPECIAL_BONDS = "amber"
GAFF2_PAIR_MODIFY   = "mix arithmetic"
DEFAULT_NEIGHBOR    = "2.0"
DEFAULT_NEIGH_MODIFY = "delay 0 every 1 check yes"
DEFAULT_NEIGH_ONE    = "4000"


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

        # ── Force field styles (always GAFF2 for RadonPy) ─────────────────
        subs["BOND_STYLE"]      = GAFF2_STYLES["BOND_STYLE"]
        subs["ANGLE_STYLE"]     = GAFF2_STYLES["ANGLE_STYLE"]
        subs["DIHEDRAL_STYLE"]  = GAFF2_STYLES["DIHEDRAL_STYLE"]
        subs["IMPROPER_STYLE"]  = GAFF2_STYLES["IMPROPER_STYLE"]

        # ── Pair style block (PPPM or cutoff) ────────────────────────────
        use_pppm = cfg.get("use_pppm", True)
        subs["PAIR_STYLE_BLOCK"] = PAIR_STYLE_PPPM if use_pppm else PAIR_STYLE_CUTOFF

        # ── GPU package ───────────────────────────────────────────────────
        if cfg.get("use_gpu", False):
            subs["GPU_PACKAGE"] = "package gpu 1 neigh no"
        else:
            subs["GPU_PACKAGE"] = "# GPU disabled (CPU run)"

        # ── Read command ──────────────────────────────────────────────────
        if cfg.get("use_restart", False):
            subs["READ_COMMAND"] = "read_restart"
        else:
            subs["READ_COMMAND"] = "read_data"

        # ── Restart block ─────────────────────────────────────────────────
        if cfg.get("write_restart", True) and template_name not in ("npt_tg_step", "nemd_thermal", "minimize"):
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
        if cfg.get("use_shake", True):
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
        subs["SPECIAL_BONDS"]  = cfg.get("SPECIAL_BONDS", GAFF2_SPECIAL_BONDS)
        subs["PAIR_MODIFY"]    = cfg.get("PAIR_MODIFY",   GAFF2_PAIR_MODIFY)
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
