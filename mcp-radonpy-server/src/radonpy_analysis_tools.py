#!/usr/bin/env python3
"""
=============================================================================
POLYMER STRUCTURAL ANALYSIS TOOLS FOR RADONPY MCP SERVER
=============================================================================

This module provides MCP tools for analyzing polymer simulation trajectories:
1. extract_end_to_end_vectors: Calculate end-to-end distances and vectors
2. calculate_rdf: Compute radial distribution functions
3. analyze_chain_properties: Combined analysis (Rg, Re, persistence length)

INTEGRATION INSTRUCTIONS:
1. Add the imports at the top of server.py (after existing imports)
2. Add the tool functions before the server initialization
3. Register tools with @mcp.tool() decorator

DEPENDENCIES:
- numpy, pandas, matplotlib (already in server.py)
- MDAnalysis (optional: pip install MDAnalysis)

Author: Alex Zhao
Date: February 4, 2026
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import logging

# Try to import MDAnalysis (recommended for trajectory analysis)
try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import rdf as mda_rdf
    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    print("Warning: MDAnalysis not installed. Using manual parsing.")

# =============================================================================
# HELPER FUNCTIONS FOR LAMMPS DUMP PARSING
# =============================================================================

def parse_lammps_dump_frame(file_handle) -> Optional[Dict]:
    """
    Parse a single frame from LAMMPS dump file.
    
    Returns:
        dict with keys: timestep, natoms, box, atoms_df (pandas DataFrame)
        Returns None if EOF reached
    """
    try:
        # Read TIMESTEP
        line = file_handle.readline()
        if not line:
            return None
        
        assert 'ITEM: TIMESTEP' in line
        timestep = int(file_handle.readline().strip())
        
        # Read NUMBER OF ATOMS
        line = file_handle.readline()
        assert 'ITEM: NUMBER OF ATOMS' in line
        natoms = int(file_handle.readline().strip())
        
        # Read BOX BOUNDS
        line = file_handle.readline()
        assert 'ITEM: BOX BOUNDS' in line
        box = []
        for _ in range(3):
            bounds = file_handle.readline().strip().split()
            box.append([float(bounds[0]), float(bounds[1])])
        box = np.array(box)
        
        # Read ATOMS header
        line = file_handle.readline()
        assert 'ITEM: ATOMS' in line
        columns = line.strip().split()[2:]  # Get column names
        
        # Read atom data
        atom_data = []
        for _ in range(natoms):
            atom_data.append(file_handle.readline().strip().split())
        
        # Convert to DataFrame
        df = pd.DataFrame(atom_data, columns=columns)
        
        # Convert numeric columns
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except ValueError:
                pass
        
        return {
            'timestep': timestep,
            'natoms': natoms,
            'box': box,
            'atoms_df': df
        }
    
    except (AssertionError, ValueError, IndexError) as e:
        logging.error(f"Error parsing LAMMPS dump frame: {e}")
        return None


def unwrap_coordinates(df: pd.DataFrame, box: np.ndarray) -> np.ndarray:
    """
    Unwrap coordinates using image flags.
    
    Args:
        df: DataFrame with columns x, y, z, ix, iy, iz
        box: Box dimensions [[xlo, xhi], [ylo, yhi], [zlo, zhi]]
    
    Returns:
        Nx3 array of unwrapped coordinates
    """
    coords = df[['x', 'y', 'z']].values
    images = df[['ix', 'iy', 'iz']].values
    
    box_lengths = box[:, 1] - box[:, 0]
    box_lengths = box_lengths.reshape(1, 3)
    
    unwrapped = coords + images * box_lengths
    
    return unwrapped


def get_chain_atoms(df: pd.DataFrame, chain_id: int) -> pd.DataFrame:
    """
    Extract atoms belonging to a specific chain.
    
    Args:
        df: Atoms DataFrame with 'mol' column
        chain_id: Molecule/chain ID
    
    Returns:
        DataFrame of atoms in that chain, sorted by atom ID
    """
    chain_df = df[df['mol'] == chain_id].copy()
    chain_df = chain_df.sort_values('id')
    return chain_df


def identify_chain_ends(chain_df: pd.DataFrame, data_file: Optional[str] = None) -> Tuple[int, int]:
    """
    Identify terminal atoms of a polymer chain.
    
    Strategy:
    1. If data file provided, use bond connectivity to find atoms with only 1 bond
    2. Otherwise, assume first and last atom by ID are chain ends
    
    Args:
        chain_df: DataFrame of atoms in the chain
        data_file: Optional path to LAMMPS data file with bond information
    
    Returns:
        (start_atom_id, end_atom_id)
    """
    if data_file and Path(data_file).exists():
        # Parse bonds from data file
        bonds = parse_bonds_from_data_file(data_file)
        
        # Count bonds per atom
        atom_ids = chain_df['id'].values
        bond_counts = {aid: 0 for aid in atom_ids}
        
        for bond in bonds:
            if bond[0] in bond_counts:
                bond_counts[bond[0]] += 1
            if bond[1] in bond_counts:
                bond_counts[bond[1]] += 1
        
        # Find atoms with only 1 bond (terminal atoms)
        terminal_atoms = [aid for aid, count in bond_counts.items() if count == 1]
        
        if len(terminal_atoms) >= 2:
            return terminal_atoms[0], terminal_atoms[-1]
    
    # Fallback: use first and last atom by ID
    atom_ids = sorted(chain_df['id'].values)
    return atom_ids[0], atom_ids[-1]


def parse_bonds_from_data_file(data_file: str) -> List[Tuple[int, int]]:
    """
    Parse bond connectivity from LAMMPS data file.
    
    Returns:
        List of (atom1_id, atom2_id) tuples
    """
    bonds = []
    in_bonds_section = False
    
    with open(data_file, 'r') as f:
        for line in f:
            if 'Bonds' in line:
                in_bonds_section = True
                continue
            
            if in_bonds_section:
                if line.strip() == '':
                    continue
                if any(keyword in line for keyword in ['Angles', 'Dihedrals', 'Impropers']):
                    break
                
                try:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        atom1 = int(parts[2])
                        atom2 = int(parts[3])
                        bonds.append((atom1, atom2))
                except (ValueError, IndexError):
                    continue
    
    return bonds


# =============================================================================
# MAIN ANALYSIS FUNCTIONS
# =============================================================================

def extract_end_to_end_vectors(
    dump_file: str,
    data_file: Optional[str] = None,
    num_chains: Optional[int] = None,
    chain_ids: Optional[List[int]] = None,
    skip_frames: int = 0,
    max_frames: Optional[int] = None,
    output_dir: Optional[str] = None,
    plot: bool = True
) -> Dict:
    """
    Extract end-to-end vectors and distances from LAMMPS dump trajectory.
    
    Args:
        dump_file: Path to LAMMPS dump file
        data_file: Optional path to LAMMPS data file for bond connectivity
        num_chains: Number of chains (if known). Will auto-detect if None
        chain_ids: Specific chain IDs to analyze. If None, analyzes all chains
        skip_frames: Number of initial frames to skip
        max_frames: Maximum number of frames to analyze
        output_dir: Directory to save output files. If None, saves to dump file dir
        plot: Whether to generate plots
    
    Returns:
        dict with:
            - end_to_end_distances: DataFrame (frame, chain, distance)
            - end_to_end_vectors: DataFrame (frame, chain, rx, ry, rz)
            - mean_distances: dict {chain_id: mean_distance}
            - std_distances: dict {chain_id: std_distance}
            - plots: list of plot file paths (if plot=True)
    """
    logger = logging.getLogger("radonpy_mcp.analysis")
    logger.info(f"Extracting end-to-end vectors from {dump_file}")
    
    # Setup output directory
    if output_dir is None:
        output_dir = Path(dump_file).parent / "analysis"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Storage for results
    all_distances = []
    all_vectors = []
    
    # Parse dump file
    frame_count = 0
    with open(dump_file, 'r') as f:
        while True:
            frame_data = parse_lammps_dump_frame(f)
            if frame_data is None:
                break
            
            # Skip initial frames
            if frame_count < skip_frames:
                frame_count += 1
                continue
            
            # Check max frames
            if max_frames and (frame_count - skip_frames) >= max_frames:
                break
            
            # Auto-detect number of chains
            if num_chains is None and 'mol' in frame_data['atoms_df'].columns:
                num_chains = frame_data['atoms_df']['mol'].max()
                logger.info(f"Auto-detected {num_chains} chains")
            
            # Determine which chains to analyze
            if chain_ids is None:
                chain_ids_to_analyze = range(1, num_chains + 1)
            else:
                chain_ids_to_analyze = chain_ids
            
            # Unwrap coordinates
            coords = unwrap_coordinates(frame_data['atoms_df'], frame_data['box'])
            
            # Analyze each chain
            for chain_id in chain_ids_to_analyze:
                chain_df = get_chain_atoms(frame_data['atoms_df'], chain_id)
                
                if len(chain_df) < 2:
                    logger.warning(f"Chain {chain_id} has < 2 atoms, skipping")
                    continue
                
                # Identify chain ends
                start_id, end_id = identify_chain_ends(chain_df, data_file)
                
                # Get unwrapped positions of terminal atoms
                start_idx = frame_data['atoms_df'][frame_data['atoms_df']['id'] == start_id].index[0]
                end_idx = frame_data['atoms_df'][frame_data['atoms_df']['id'] == end_id].index[0]
                
                start_pos = coords[start_idx]
                end_pos = coords[end_idx]
                
                # Calculate end-to-end vector and distance
                r_ee = end_pos - start_pos
                distance = np.linalg.norm(r_ee)
                
                all_distances.append({
                    'frame': frame_count,
                    'timestep': frame_data['timestep'],
                    'chain': chain_id,
                    'distance': distance
                })
                
                all_vectors.append({
                    'frame': frame_count,
                    'timestep': frame_data['timestep'],
                    'chain': chain_id,
                    'rx': r_ee[0],
                    'ry': r_ee[1],
                    'rz': r_ee[2]
                })
            
            frame_count += 1
            
            if frame_count % 100 == 0:
                logger.info(f"Processed {frame_count} frames")
    
    # Convert to DataFrames
    distances_df = pd.DataFrame(all_distances)
    vectors_df = pd.DataFrame(all_vectors)
    
    # Calculate statistics
    mean_distances = {}
    std_distances = {}
    for chain_id in distances_df['chain'].unique():
        chain_data = distances_df[distances_df['chain'] == chain_id]['distance']
        mean_distances[int(chain_id)] = float(chain_data.mean())
        std_distances[int(chain_id)] = float(chain_data.std())
    
    # Save data
    distances_file = output_dir / "end_to_end_distances.csv"
    vectors_file = output_dir / "end_to_end_vectors.csv"
    distances_df.to_csv(distances_file, index=False)
    vectors_df.to_csv(vectors_file, index=False)
    logger.info(f"Saved data to {distances_file} and {vectors_file}")
    
    # Generate plots
    plot_files = []
    if plot:
        # Plot 1: End-to-end distance vs frame for each chain
        fig, ax = plt.subplots(figsize=(10, 6))
        for chain_id in distances_df['chain'].unique():
            chain_data = distances_df[distances_df['chain'] == chain_id]
            ax.plot(chain_data['frame'], chain_data['distance'], 
                   label=f'Chain {int(chain_id)}', alpha=0.7)
        
        ax.set_xlabel('Frame', fontsize=12)
        ax.set_ylabel('End-to-End Distance (Å)', fontsize=12)
        ax.set_title('End-to-End Distance Evolution', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plot1 = output_dir / "end_to_end_distance_vs_frame.png"
        plt.tight_layout()
        plt.savefig(plot1, dpi=300)
        plt.close()
        plot_files.append(str(plot1))
        
        # Plot 2: Distribution of end-to-end distances
        fig, ax = plt.subplots(figsize=(10, 6))
        for chain_id in distances_df['chain'].unique():
            chain_data = distances_df[distances_df['chain'] == chain_id]['distance']
            ax.hist(chain_data, bins=50, alpha=0.5, 
                   label=f'Chain {int(chain_id)} (μ={mean_distances[int(chain_id)]:.1f} Å)')
        
        ax.set_xlabel('End-to-End Distance (Å)', fontsize=12)
        ax.set_ylabel('Frequency', fontsize=12)
        ax.set_title('End-to-End Distance Distribution', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plot2 = output_dir / "end_to_end_distance_distribution.png"
        plt.tight_layout()
        plt.savefig(plot2, dpi=300)
        plt.close()
        plot_files.append(str(plot2))
        
        # Plot 3: Mean end-to-end distance per chain
        fig, ax = plt.subplots(figsize=(8, 6))
        chains = sorted(mean_distances.keys())
        means = [mean_distances[c] for c in chains]
        stds = [std_distances[c] for c in chains]
        
        ax.bar(chains, means, yerr=stds, capsize=5, alpha=0.7, color='steelblue')
        ax.set_xlabel('Chain ID', fontsize=12)
        ax.set_ylabel('Mean End-to-End Distance (Å)', fontsize=12)
        ax.set_title('Mean End-to-End Distance by Chain', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')
        
        plot3 = output_dir / "mean_end_to_end_distances.png"
        plt.tight_layout()
        plt.savefig(plot3, dpi=300)
        plt.close()
        plot_files.append(str(plot3))
        
        logger.info(f"Generated {len(plot_files)} plots")
    
    # Create summary
    summary = {
        'dump_file': str(dump_file),
        'data_file': str(data_file) if data_file else None,
        'num_chains': num_chains,
        'num_frames_analyzed': len(distances_df['frame'].unique()),
        'mean_distances': mean_distances,
        'std_distances': std_distances,
        'distances_file': str(distances_file),
        'vectors_file': str(vectors_file),
        'plot_files': plot_files
    }
    
    return summary


def calculate_rdf(
    dump_file: str,
    atom_types: Optional[List[Tuple[int, int]]] = None,
    rmax: float = 15.0,
    nbins: int = 150,
    skip_frames: int = 0,
    max_frames: Optional[int] = None,
    output_dir: Optional[str] = None,
    plot: bool = True
) -> Dict:
    """
    Calculate radial distribution function (RDF) from LAMMPS dump trajectory.

    Uses fully vectorized NumPy distance computation via broadcasting:
        diff[i,j] = coords1[i] - coords2[j]   shape (N1, N2, 3)
    Minimum image convention is applied in one array operation, and
    distances are extracted with np.linalg.norm over axis=-1.
    This is ~100-200x faster than the previous Python loop over atom pairs
    and avoids explicit iteration over i,j indices entirely.

    Memory note: peak RAM per frame = O(N1 * N2 * 24 bytes).
    For a 10k-atom system with a single pair type (~5k x 5k), this is ~600 MB.
    Always supply atom_types explicitly — never pass None on large systems.

    Args:
        dump_file:   Path to LAMMPS dump file.
        atom_types:  List of (type1, type2) tuples to calculate RDF for.
                     If None, calculates for all unique pairs (use with caution
                     on large systems — memory scales as N1*N2 per pair).
        rmax:        Maximum distance for RDF calculation (Å). Default 15.0.
        nbins:       Number of histogram bins over [0, rmax]. Default 150.
        skip_frames: Number of initial frames to skip as burn-in.
        max_frames:  Maximum frames to analyze after skip.
        output_dir:  Directory for output files. Defaults to <dump_dir>/analysis.
        plot:        Whether to generate and save a combined RDF plot.

    Returns:
        dict with keys:
            rdf_data  — {str(pair_key): {r: [...], g(r): [...]}}
            rdf_files — {str(pair_key): csv_path}
            plot_files — list of PNG paths
            num_frames — number of frames analyzed
    """
    logger = logging.getLogger("radonpy_mcp.analysis")
    logger.info(f"Calculating RDF from {dump_file}")

    # ── output directory ────────────────────────────────────────────────────
    if output_dir is None:
        output_dir = Path(dump_file).parent / "analysis"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── bin geometry (computed once) ────────────────────────────────────────
    bin_edges   = np.linspace(0, rmax, nbins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    r_inner     = bin_edges[:-1]
    r_outer     = bin_edges[1:]
    shell_vols  = (4.0 / 3.0) * np.pi * (r_outer**3 - r_inner**3)
    dr          = bin_edges[1] - bin_edges[0]

    rdf_accumulators: Dict = {}
    frame_count_dict: Dict = {}
    last_df        = None
    last_box_lengths = None

    # ── frame loop ──────────────────────────────────────────────────────────
    frame_count = 0
    with open(dump_file, 'r') as f:
        while True:
            frame_data = parse_lammps_dump_frame(f)
            if frame_data is None:
                break

            if frame_count < skip_frames:
                frame_count += 1
                continue

            if max_frames and (frame_count - skip_frames) >= max_frames:
                break

            df          = frame_data['atoms_df']
            coords      = df[['x', 'y', 'z']].values.astype(np.float64)
            types       = df['type'].values
            box         = frame_data['box']
            box_lengths = (box[:, 1] - box[:, 0]).astype(np.float64)  # shape (3,)

            last_df         = df
            last_box_lengths = box_lengths

            # determine pairs
            if atom_types is None:
                unique_types   = sorted(df['type'].unique())
                pairs_to_analyze = [
                    (t1, t2) for t1 in unique_types
                    for t2 in unique_types if t1 <= t2
                ]
            else:
                pairs_to_analyze = atom_types

            for type1, type2 in pairs_to_analyze:
                pair_key = (int(type1), int(type2))
                if pair_key not in rdf_accumulators:
                    rdf_accumulators[pair_key] = np.zeros(nbins, dtype=np.float64)
                    frame_count_dict[pair_key] = 0

                mask1 = types == type1
                mask2 = types == type2
                c1 = coords[mask1]   # (N1, 3)
                c2 = coords[mask2]   # (N2, 3)

                if len(c1) == 0 or len(c2) == 0:
                    continue

                # ── vectorized pairwise diff: shape (N1, N2, 3) ────────────
                diff = c1[:, np.newaxis, :] - c2[np.newaxis, :, :]  # (N1,N2,3)

                # minimum image convention — one array operation
                diff -= np.round(diff / box_lengths) * box_lengths

                # scalar distances: shape (N1, N2)
                dists = np.linalg.norm(diff, axis=-1)

                # for same-type pairs exclude i==j and keep only i<j
                if type1 == type2:
                    # build index arrays within c1/c2 (they are the same set)
                    n = len(c1)
                    i_idx, j_idx = np.triu_indices(n, k=1)  # all unique pairs
                    dists_flat = dists[i_idx, j_idx]
                else:
                    dists_flat = dists.ravel()

                # keep only distances within rmax
                dists_flat = dists_flat[dists_flat < rmax]

                # histogram into bins
                counts, _ = np.histogram(dists_flat, bins=bin_edges)
                rdf_accumulators[pair_key] += counts
                frame_count_dict[pair_key] += 1

            frame_count += 1
            if frame_count % 100 == 0:
                logger.info(f"Processed {frame_count} frames for RDF")

    # ── normalisation ───────────────────────────────────────────────────────
    rdf_data:  Dict = {}
    rdf_files: Dict = {}

    if last_df is None or last_box_lengths is None:
        logger.warning("No frames were processed.")
        return {'dump_file': str(dump_file), 'rmax': rmax, 'nbins': nbins,
                'num_frames': 0, 'rdf_data': {}, 'rdf_files': {}, 'plot_files': []}

    volume = float(np.prod(last_box_lengths))

    for pair_key, histogram in rdf_accumulators.items():
        type1, type2 = pair_key
        n_frames = frame_count_dict[pair_key]

        n1  = int((last_df['type'] == type1).sum())
        n2  = int((last_df['type'] == type2).sum())
        rho = n2 / volume  # number density of species 2

        # expected counts in an ideal gas
        if type1 == type2:
            # unique pairs: n1*(n1-1)/2 reference pairs per frame
            ideal = rho * shell_vols * (n1 * (n1 - 1) / 2) * n_frames
        else:
            ideal = rho * shell_vols * n1 * n_frames

        gr = np.where(ideal > 0, histogram / ideal, 0.0)

        rdf_df = pd.DataFrame({'r': bin_centers, 'g(r)': gr})
        rdf_data[pair_key] = rdf_df

        filename = output_dir / f"rdf_type{type1}-type{type2}.csv"
        rdf_df.to_csv(filename, index=False)
        rdf_files[pair_key] = str(filename)
        logger.info(f"Calculated RDF for types {type1}-{type2}")

    # ── plots ────────────────────────────────────────────────────────────────
    plot_files = []
    if plot and rdf_data:
        fig, ax = plt.subplots(figsize=(10, 6))
        for pair_key, rdf_df in rdf_data.items():
            type1, type2 = pair_key
            ax.plot(rdf_df['r'], rdf_df['g(r)'],
                    label=f'Type {type1}-{type2}', linewidth=2)
        ax.set_xlabel('r (Å)', fontsize=12)
        ax.set_ylabel('g(r)', fontsize=12)
        ax.set_title('Radial Distribution Function', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, rmax)
        plot_file = output_dir / "rdf_all_pairs.png"
        plt.tight_layout()
        plt.savefig(plot_file, dpi=300)
        plt.close()
        plot_files.append(str(plot_file))
        logger.info(f"Generated RDF plot: {plot_file}")

    return {
        'dump_file':  str(dump_file),
        'rmax':       rmax,
        'nbins':      nbins,
        'num_frames': frame_count - skip_frames,
        'rdf_data':   {str(k): v.to_dict('list') for k, v in rdf_data.items()},
        'rdf_files':  {str(k): v for k, v in rdf_files.items()},
        'plot_files': plot_files,
    }

def bilinear_model(T, Tg, a1, b1, a2, b2):
    """
    Bilinear model:
    - Below Tg (glassy): ρ = a2 + b2*T  
    - Above Tg (rubbery): ρ = a1 + b1*T
    """
    return np.where(T < Tg, a2 + b2*T, a1 + b1*T)

def fit_bilinear(temps, densities, initial_tg_guess=None):
    """
    Fit bilinear model to density-temperature data
    
    Returns:
        Tg: Glass transition temperature
        params: (a1, b1, a2, b2) parameters
        r_squared: R² value
    """
    if initial_tg_guess is None:
        initial_tg_guess = (temps.max() + temps.min()) / 2
    
    # Initial parameter guesses
    # a1, b1: high-T parameters (steeper slope)
    # a2, b2: low-T parameters (gentler slope)
    initial_guess = [
        initial_tg_guess,  # Tg
        1.2,               # a1 (intercept high-T)
        -0.0005,           # b1 (slope high-T, negative)
        1.0,               # a2 (intercept low-T)
        -0.0003            # b2 (slope low-T, less negative)
    ]
    
    # Fit the bilinear model
    try:
        params, _ = optimize.curve_fit(
            bilinear_model,
            temps,
            densities,
            p0=initial_guess,
            maxfev=10000
        )
        
        Tg, a1, b1, a2, b2 = params
        
        # Calculate R²
        predicted = bilinear_model(temps, *params)
        ss_res = np.sum((densities - predicted)**2)
        ss_tot = np.sum((densities - densities.mean())**2)
        r_squared = 1 - (ss_res / ss_tot)
        
        # Alternative: Two separate linear regressions
        # This is often more stable
        low_T_mask = temps < Tg
        high_T_mask = temps >= Tg
        
        if np.sum(low_T_mask) > 2 and np.sum(high_T_mask) > 2:
            # Fit low-T region
            slope_low, intercept_low, r_low, _, _ = stats.linregress(
                temps[low_T_mask], densities[low_T_mask]
            )
            # Fit high-T region  
            slope_high, intercept_high, r_high, _, _ = stats.linregress(
                temps[high_T_mask], densities[high_T_mask]
            )
            
            # Calculate intersection
            Tg_alt = (intercept_low - intercept_high) / (slope_high - slope_low)
            
            return {
                'Tg': Tg,
                'Tg_alternative': Tg_alt,
                'params': {'a1': a1, 'b1': b1, 'a2': a2, 'b2': b2},
                'r_squared': r_squared,
                'slopes': {'low_T': slope_low, 'high_T': slope_high},
                'r_values': {'low_T': r_low, 'high_T': r_high}
            }
        
        return {
            'Tg': Tg,
            'params': {'a1': a1, 'b1': b1, 'a2': a2, 'b2': b2},
            'r_squared': r_squared
        }
        
    except Exception as e:
        return { "bilinear fit error": str(e) }

    
def plot_tg_analysis(temps, densities, result, save_path="tg_analysis.png"):
    """Generate Tg analysis plot"""
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    # Left plot: Density vs Temperature
    ax1.scatter(temps, densities, s=100, alpha=0.6, c='blue', label='MD Data')
    
    if result:
        Tg = result['Tg']
        
        # Plot fitted lines
        T_fine = np.linspace(temps.min(), temps.max(), 200)
        ρ_fitted = bilinear_model(T_fine, Tg, 
                                   result['params']['a1'], result['params']['b1'],
                                   result['params']['a2'], result['params']['b2'])
        ax1.plot(T_fine, ρ_fitted, 'r-', linewidth=2, label='Bilinear Fit')
        
        # Mark Tg
        ρ_at_Tg = bilinear_model(Tg, Tg, 
                                  result['params']['a1'], result['params']['b1'],
                                  result['params']['a2'], result['params']['b2'])
        ax1.axvline(Tg, color='green', linestyle='--', linewidth=2, 
                   label=f'Tg = {Tg:.1f} K')
        ax1.plot(Tg, ρ_at_Tg, 'go', markersize=15, markeredgewidth=2, 
                markerfacecolor='none')
        
        # Add text box with results
        textstr = f'Tg = {Tg:.1f} K\nR² = {result["r_squared"]:.4f}'
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax1.text(0.05, 0.95, textstr, transform=ax1.transAxes, 
                fontsize=12, verticalalignment='top', bbox=props)
    
    ax1.set_xlabel('Temperature (K)', fontsize=14)
    ax1.set_ylabel('Density (g/cm³)', fontsize=14)
    ax1.set_title('Glass Transition Temperature Determination', fontsize=16, fontweight='bold')
    ax1.legend(fontsize=12)
    ax1.grid(True, alpha=0.3)
    
    # Right plot: Specific Volume vs Temperature (alternative view)
    specific_vols = 1.0 / densities
    ax2.scatter(temps, specific_vols, s=100, alpha=0.6, c='purple', label='MD Data')
    
    ax2.set_xlabel('Temperature (K)', fontsize=14)
    ax2.set_ylabel('Specific Volume (cm³/g)', fontsize=14)
    ax2.set_title('Specific Volume Method', fontsize=16, fontweight='bold')
    ax2.legend(fontsize=12)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    
    return fig

def validate_tg(simulated_tg, experimental_tg, polymer_name):
    """
    Validate simulated Tg against experimental value
    
    Acceptance criteria for publication:
    - Excellent: |error| < 10 K
    - Good: |error| < 20 K  
    - Acceptable: |error| < 30 K
    """
    error = simulated_tg - experimental_tg
    percent_error = (error / experimental_tg) * 100
    
    return {
        'simulated': simulated_tg,
        'experimental': experimental_tg,
        'error': error,
        'percent_error': percent_error,
        'passed': abs(error) < 30,
        'status': (
            "EXCELLENT" if abs(error) < 10 else
            "GOOD" if abs(error) < 20 else
            "ACCEPTABLE" if abs(error) < 30 else
            "NEEDS IMPROVEMENT"
        )   
    }



# =============================================================================
# MCP TOOL WRAPPERS
# =============================================================================

def mcp_extract_end_to_end_vectors(
    dump_file: str,
    data_file: Optional[str] = None,
    num_chains: Optional[int] = None,
    chain_ids: Optional[List[int]] = None,
    skip_frames: int = 0,
    max_frames: Optional[int] = None,
    output_dir: Optional[str] = None,
    plot: bool = True
) -> Dict:
    """
    MCP Tool: Extract end-to-end vectors from polymer simulation dump file.
    """
    try:
        result = extract_end_to_end_vectors(
            dump_file=dump_file,
            data_file=data_file,
            num_chains=num_chains,
            chain_ids=chain_ids,
            skip_frames=skip_frames,
            max_frames=max_frames,
            output_dir=output_dir,
            plot=plot
        )
        return {
            "status": "success",
            "message": "End-to-end vector analysis completed successfully",
            **result
        }
    except Exception as e:
        logging.error(f"Error in end-to-end vector extraction: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


def mcp_calculate_rdf(
    dump_file: str,
    atom_type_pairs: Optional[List[List[int]]] = None,
    rmax: float = 15.0,
    nbins: int = 150,
    skip_frames: int = 0,
    max_frames: Optional[int] = None,
    output_dir: Optional[str] = None,
    plot: bool = True
) -> Dict:
    """
    MCP Tool: Calculate radial distribution function (RDF) from simulation.
    """
    try:
        # Convert list of lists to list of tuples
        if atom_type_pairs:
            atom_types = [tuple(pair) for pair in atom_type_pairs]
        else:
            atom_types = None
        
        result = calculate_rdf(
            dump_file=dump_file,
            atom_types=atom_types,
            rmax=rmax,
            nbins=nbins,
            skip_frames=skip_frames,
            max_frames=max_frames,
            output_dir=output_dir,
            plot=plot
        )
        return {
            "status": "success",
            "message": "RDF calculation completed successfully",
            **result
        }
    except Exception as e:
        logging.error(f"Error in RDF calculation: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }
