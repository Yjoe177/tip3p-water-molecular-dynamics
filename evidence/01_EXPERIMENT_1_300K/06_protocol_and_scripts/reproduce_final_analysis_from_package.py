#!/usr/bin/env python
"""Package-local analysis reproducer for FINAL_MD_PROJECT_PACKAGE_R5.

Run from the package root directory. Reads only files contained in the package
and regenerates all final analysis outputs and all 8 report figures.

No SPONGE is launched; this is pure post-processing of accepted raw data.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_DIR = PACKAGE_ROOT / '01_system_and_forcefield'
SEG01_DIR = PACKAGE_ROOT / '03_production_trajectory' / 'segment01_6ps'
SEG02_DIR = PACKAGE_ROOT / '03_production_trajectory' / 'segment02_4ps'
PREP_DIR = PACKAGE_ROOT / '03_preproduction_equilibration_80ps'
ANA_DIR = PACKAGE_ROOT / '04_analysis_data'
FIG_DIR = PACKAGE_ROOT / '05_figures'

NATOMS = 2586
NMOLS = 862
NOXY = 862
NHYD = 1724
TRJ_BYTES_PER_ATOM = 3 * 4

BURN_IN_CUTOFF_PS = 5.0
PRODUCTION_START_PS = 102.620
PRIMARY_CUTOFF_PS = 107.620


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def read_mdout(path: Path):
    """Return (header_line, list of non-empty data lines after header)."""
    header = None
    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if re.match(r'^\s*step\s+time', line, re.IGNORECASE):
                header = line
                continue
            if re.match(r'^\s*\d+\s+[0-9.]+', line):
                records.append(line)
    return header, records


def parse_mdout_records(records):
    """Parse mdout records into arrays."""
    data = []
    for line in records:
        parts = line.split()
        data.append([float(p) if p != '****' else np.nan for p in parts])
    arr = np.array(data, dtype=float)
    return {
        'step': arr[:, 0].astype(int),
        'time_ps': arr[:, 1],
        'temperature': arr[:, 2],
        'pressure': arr[:, 3],
        'Pxx': arr[:, 4],
        'Pyy': arr[:, 5],
        'Pzz': arr[:, 6],
        'Pxy': arr[:, 7],
        'Pxz': arr[:, 8],
        'Pyz': arr[:, 9],
        'potential': arr[:, 10],
        'density': arr[:, 11],
        'bond': arr[:, 17],
    }


def finite_stats(arr):
    arr = np.asarray(arr)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {'mean': float('nan'), 'std': float('nan'), 'min': float('nan'), 'max': float('nan'), 'n': 0}
    return {
        'mean': float(np.mean(finite)),
        'std': float(np.std(finite, ddof=1)),
        'min': float(np.min(finite)),
        'max': float(np.max(finite)),
        'n': int(finite.size),
    }


def linear_slope(x, y):
    x = np.asarray(x)
    y = np.asarray(y)
    fin = np.isfinite(x) & np.isfinite(y)
    if np.sum(fin) < 2:
        return float('nan')
    x = x[fin]
    y = y[fin]
    return float(np.polyfit(x, y, 1)[0])


def read_traj(path: Path):
    raw = np.fromfile(path, dtype=np.float32)
    nframes = raw.size // (NATOMS * 3)
    if raw.size % (NATOMS * 3) != 0:
        raise ValueError(f'{path}: size {raw.size} not a multiple of {NATOMS * 3}')
    return raw.reshape((nframes, NATOMS, 3))


def read_box(path: Path):
    boxes = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                boxes.append([float(x) for x in line.split()])
    return np.array(boxes)


def minimum_image(dr, box):
    return dr - box * np.round(dr / box)


def compute_inter_rdf(coords_a, coords_b, mol_a, mol_b, boxes, n_a, n_b_valid,
                        r_max=10.0, bin_width=0.1, exclude_same_molecule=True,
                        exclude_self_same_set=False):
    """Compute intermolecular-only RDF with per-frame box normalization.

    coords_a, coords_b: shape (n_frames, n_atoms_species, 3)
    mol_a, mol_b: molecule ids for each atom in species (length n_atoms_species)
    n_a: number of central atoms per frame (species A count) - set from coords_a.shape[1]
    n_b_valid: number of valid target atoms per central A atom (after exclusions)
    boxes: shape (n_frames, 6) with first three columns as box lengths
    """
    # Authoritative counts: number of atoms in species A/B per frame
    n_a = coords_a.shape[1]
    n_b = coords_b.shape[1]
    n_bins = int(round(r_max / bin_width))
    dr = r_max / n_bins
    bins = np.linspace(0, r_max, n_bins + 1)
    hist = np.zeros(n_bins, dtype=float)
    n_frames = coords_a.shape[0]
    for frame in range(n_frames):
        a = coords_a[frame]
        b = coords_b[frame]
        diff = a[:, None, :] - b[None, :, :]
        diff = minimum_image(diff, boxes[frame, :3])
        d = np.sqrt(np.sum(diff ** 2, axis=2))
        if exclude_same_molecule:
            same_mol = mol_a[:, None] == mol_b[None, :]
            d[same_mol] = np.inf
        if exclude_self_same_set:
            np.fill_diagonal(d, np.inf)
        h, _ = np.histogram(d[(d > 0) & (d < r_max)], bins=bins)
        hist += h

    r = bins[:-1] + dr / 2
    shell = 4.0 * np.pi * r ** 2 * dr

    denom = np.zeros(n_bins, dtype=float)
    for frame in range(n_frames):
        V = np.prod(boxes[frame, :3])
        denom += n_a * n_b_valid * shell / V

    g = hist / denom
    return r, g


def find_first_local_peak(r_arr, g_arr, min_r, max_r):
    """Return the first local maximum in the interval [min_r, max_r]."""
    r_arr = np.asarray(r_arr)
    g_arr = np.asarray(g_arr)
    idxs = np.where((r_arr >= min_r) & (r_arr <= max_r))[0]
    for i in idxs:
        if i == 0 or i == len(g_arr) - 1:
            continue
        if g_arr[i] > 1.0 and g_arr[i] > g_arr[i - 1] and g_arr[i] >= g_arr[i + 1]:
            return float(r_arr[i]), float(g_arr[i])
    return None, None


def find_first_minimum_after_peak(r_arr, g_arr, peak_r, max_r):
    """Return the first local minimum after peak_r (and <= max_r)."""
    r_arr = np.asarray(r_arr)
    g_arr = np.asarray(g_arr)
    idxs = np.where((r_arr > peak_r) & (r_arr <= max_r))[0]
    for i in idxs:
        if i == 0 or i == len(g_arr) - 1:
            continue
        if g_arr[i] < g_arr[i - 1] and g_arr[i] <= g_arr[i + 1]:
            return float(r_arr[i]), float(g_arr[i])
    return None, None


def find_global_maximum(r_arr, g_arr, min_r, max_r):
    """Return the global maximum in an interval (used for secondary peaks)."""
    r_arr = np.asarray(r_arr)
    g_arr = np.asarray(g_arr)
    mask = (r_arr >= min_r) & (r_arr <= max_r)
    if not np.any(mask):
        return None, None
    idx = np.argmax(g_arr[mask])
    return float(r_arr[mask][idx]), float(g_arr[mask][idx])


def large_r_mean(g_arr, r_arr, r_lo=8.0, r_hi=10.0):
    r_arr = np.asarray(r_arr)
    g_arr = np.asarray(g_arr)
    mask = (r_arr >= r_lo) & (r_arr <= r_hi)
    if not np.any(mask):
        return float('nan')
    return float(np.mean(g_arr[mask]))


def plot_series(x, y, xlabel, ylabel, fname, color='steelblue', hline=None,
                xlim=None, ylim=None):
    fig, ax = plt.subplots(figsize=(6, 4), dpi=300)
    ax.plot(x, y, color=color, linewidth=0.8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if hline is not None:
        ax.axhline(hline, color='k', linestyle='--', alpha=0.3, linewidth=0.6)
    if xlim is not None:
        ax.set_xlim(xlim)
    if ylim is not None:
        ax.set_ylim(ylim)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / fname, dpi=300)
    plt.close(fig)


def main():
    ANA_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # Read mdout data
    seg01_header, seg01_records = read_mdout(SEG01_DIR / 'npt_production_segment01_6ps.mdout')
    seg02_header, seg02_records = read_mdout(SEG02_DIR / 'npt_production_segment02_4ps.mdout')

    seg01 = parse_mdout_records(seg01_records)
    seg02 = parse_mdout_records(seg02_records)

    # Combine and define windows
    combined_step = np.concatenate([seg01['step'], seg02['step']])
    combined_time = np.concatenate([seg01['time_ps'], seg02['time_ps']])
    combined_temp = np.concatenate([seg01['temperature'], seg02['temperature']])
    combined_pres = np.concatenate([seg01['pressure'], seg02['pressure']])
    combined_dens = np.concatenate([seg01['density'], seg02['density']])
    combined_pot = np.concatenate([seg01['potential'], seg02['potential']])

    full_mask = combined_time >= PRODUCTION_START_PS
    # Critical: 107.620 belongs to burn-in, not primary
    burn_mask = (combined_time >= PRODUCTION_START_PS) & (combined_time <= PRIMARY_CUTOFF_PS)
    primary_mask = combined_time > PRIMARY_CUTOFF_PS

    windows = {
        'full_10ps': full_mask,
        'burn_in_0_5ps': burn_mask,
        'primary_5_10ps': primary_mask,
    }

    thermo_stats = {}
    for name, mask in windows.items():
        t = combined_time[mask]
        thermo_stats[name] = {
            'time_range_ps': [float(t.min()), float(t.max())],
            'n_records': int(t.size),
            'temperature_K': finite_stats(combined_temp[mask]),
            'pressure_bar': finite_stats(combined_pres[mask]),
            'density_g_cm3': finite_stats(combined_dens[mask]),
            'potential_kcal_mol': finite_stats(combined_pot[mask]),
        }

    # Write production_thermodynamics.csv
    with open(ANA_DIR / 'production_thermodynamics.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['time_ps', 'temperature_K', 'pressure_bar', 'density_g_cm3', 'potential_kcal_mol', 'segment'])
        for i in range(combined_time.size):
            seg = 'seg01' if i < seg01['time_ps'].size else 'seg02'
            w.writerow([
                combined_time[i], combined_temp[i], combined_pres[i],
                combined_dens[i], combined_pot[i], seg
            ])

    # Block statistics
    with open(ANA_DIR / 'block_statistics.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['window', 'temperature_mean', 'temperature_std', 'pressure_mean', 'pressure_std',
                    'density_mean', 'density_std', 'potential_mean', 'potential_std', 'n'])
        for name, stats in thermo_stats.items():
            w.writerow([
                name,
                stats['temperature_K']['mean'], stats['temperature_K']['std'],
                stats['pressure_bar']['mean'], stats['pressure_bar']['std'],
                stats['density_g_cm3']['mean'], stats['density_g_cm3']['std'],
                stats['potential_kcal_mol']['mean'], stats['potential_kcal_mol']['std'],
                stats['n_records'],
            ])

    # Read trajectory and boxes
    seg01_traj = read_traj(SEG01_DIR / 'npt_production_segment01_6ps_traj.dat')
    seg02_traj = read_traj(SEG02_DIR / 'npt_production_segment02_4ps_traj.dat')
    seg01_box = read_box(SEG01_DIR / 'npt_production_segment01_6ps_traj.box')
    seg02_box = read_box(SEG02_DIR / 'npt_production_segment02_4ps_traj.box')
    combined_traj = np.concatenate([seg01_traj, seg02_traj], axis=0)
    combined_box = np.concatenate([seg01_box, seg02_box], axis=0)
    n_traj_frames = combined_traj.shape[0]

    # Frame times derived from output intervals and restart times
    seg01_start = 102.620
    seg01_interval = 1.0  # 1000 steps * 0.001 ps
    seg02_start = 108.620
    seg02_interval = 0.5  # 500 steps * 0.001 ps

    frame_times = []
    for i, _ in enumerate(combined_box):
        if i < seg01_box.shape[0]:
            t = seg01_start + (i + 1) * seg01_interval
        else:
            j = i - seg01_box.shape[0]
            t = seg02_start + (j + 1) * seg02_interval
        frame_times.append(t)
    frame_times = np.array(frame_times)

    # Box frames CSV
    with open(ANA_DIR / 'box_frames.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['frame', 'time_ps', 'a_A', 'b_A', 'c_A', 'alpha_deg', 'beta_deg', 'gamma_deg', 'volume_A3'])
        for i, box in enumerate(combined_box):
            V = box[0] * box[1] * box[2]
            w.writerow([i + 1, frame_times[i], box[0], box[1], box[2], box[3], box[4], box[5], V])

    # Box windows: use the same time boundary as thermodynamic records
    burn_box_mask = frame_times <= PRIMARY_CUTOFF_PS
    primary_box_mask = frame_times > PRIMARY_CUTOFF_PS

    box_stats = {}
    for name, mask in [('full_10ps', np.ones(n_traj_frames, dtype=bool)),
                       ('burn_in_0_5ps', burn_box_mask),
                       ('primary_5_10ps', primary_box_mask)]:
        boxes = combined_box[mask]
        a, b, c = boxes[:, 0], boxes[:, 1], boxes[:, 2]
        V = a * b * c
        box_stats[name] = {
            'a_A': finite_stats(a),
            'b_A': finite_stats(b),
            'c_A': finite_stats(c),
            'volume_A3': finite_stats(V),
            'n_frames': int(boxes.shape[0]),
            'time_range_ps': [float(frame_times[mask].min()), float(frame_times[mask].max())],
        }

    # Structural analysis with minimum-image PBC handling
    with open(SYSTEM_DIR / 'water_30A_randomized_atom_name.txt', 'r', encoding='utf-8') as f:
        atom_names = np.array([line.strip() for line in f.readlines()[1:]])

    mol_ids = np.arange(NATOMS) // 3
    oxygen_indices = np.where(atom_names == 'O')[0]
    h1_indices = np.where(atom_names == 'H1')[0]
    h2_indices = np.where(atom_names == 'H2')[0]
    hydrogen_indices = np.concatenate([h1_indices, h2_indices])
    oxygen_mol_ids = mol_ids[oxygen_indices]
    hydrogen_mol_ids = mol_ids[hydrogen_indices]

    oh_dists = []
    hh_dists = []
    hoh_angles = []
    for frame in range(n_traj_frames):
        coords = combined_traj[frame]
        box = combined_box[frame, :3]
        O = coords[oxygen_indices]
        H1 = coords[h1_indices]
        H2 = coords[h2_indices]

        # Intramolecular distances with PBC minimum-image
        d_oh1 = np.sqrt(np.sum(minimum_image(H1 - O, box) ** 2, axis=1))
        d_oh2 = np.sqrt(np.sum(minimum_image(H2 - O, box) ** 2, axis=1))
        d_hh = np.sqrt(np.sum(minimum_image(H2 - H1, box) ** 2, axis=1))

        oh_dists.extend(d_oh1)
        oh_dists.extend(d_oh2)
        hh_dists.extend(d_hh)

        # H-O-H angle with minimum-image bond vectors
        v1 = minimum_image(H1 - O, box)
        v2 = minimum_image(H2 - O, box)
        norm1 = np.linalg.norm(v1, axis=1)
        norm2 = np.linalg.norm(v2, axis=1)
        cos = np.sum(v1 * v2, axis=1) / (norm1 * norm2)
        cos = np.clip(cos, -1.0, 1.0)
        angle = np.degrees(np.arccos(cos))
        hoh_angles.extend(angle)

    oh_dists = np.array(oh_dists)
    hh_dists = np.array(hh_dists)
    hoh_angles = np.array(hoh_angles)

    # Per-frame minimum intermolecular distances
    oxy_frames = combined_traj[:, oxygen_indices, :]
    hy_frames = combined_traj[:, hydrogen_indices, :]
    min_oo = []
    min_oh = []
    min_hh = []
    for frame in range(n_traj_frames):
        box = combined_box[frame, :3]
        # O-O intermolecular
        diff = oxy_frames[frame][:, None, :] - oxy_frames[frame][None, :, :]
        diff = minimum_image(diff, box)
        d = np.sqrt(np.sum(diff ** 2, axis=2))
        np.fill_diagonal(d, np.inf)
        min_oo.append(float(np.min(d)))

        # O-H intermolecular
        diff = oxy_frames[frame][:, None, :] - hy_frames[frame][None, :, :]
        diff = minimum_image(diff, box)
        d = np.sqrt(np.sum(diff ** 2, axis=2))
        same_mol = oxygen_mol_ids[:, None] == hydrogen_mol_ids[None, :]
        d[same_mol] = np.inf
        min_oh.append(float(np.min(d)))

        # H-H intermolecular
        diff = hy_frames[frame][:, None, :] - hy_frames[frame][None, :, :]
        diff = minimum_image(diff, box)
        d = np.sqrt(np.sum(diff ** 2, axis=2))
        same_mol = hydrogen_mol_ids[:, None] == hydrogen_mol_ids[None, :]
        d[same_mol] = np.inf
        min_hh.append(float(np.min(d)))

    structure_stats = {
        'OH_distance_A': finite_stats(oh_dists),
        'HH_distance_A': finite_stats(hh_dists),
        'HOH_angle_deg': finite_stats(hoh_angles),
        'min_inter_OO_A': finite_stats(np.array(min_oo)),
        'min_inter_OH_A': finite_stats(np.array(min_oh)),
        'min_inter_HH_A': finite_stats(np.array(min_hh)),
    }

    with open(ANA_DIR / 'structure.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['quantity', 'mean', 'std', 'min', 'max', 'n'])
        for k, v in structure_stats.items():
            w.writerow([k, v['mean'], v['std'], v['min'], v['max'], v['n']])

    # RDF intermolecular with corrected normalization
    r_max = 10.0
    bin_width = 0.1

    r, g_oo = compute_inter_rdf(
        oxy_frames, oxy_frames, oxygen_mol_ids, oxygen_mol_ids,
        combined_box, n_a=NOXY, n_b_valid=NOXY - 1, r_max=r_max, bin_width=bin_width,
        exclude_same_molecule=True, exclude_self_same_set=True
    )
    _, g_oh = compute_inter_rdf(
        oxy_frames, hy_frames, oxygen_mol_ids, hydrogen_mol_ids,
        combined_box, n_a=NOXY, n_b_valid=NHYD - 2, r_max=r_max, bin_width=bin_width,
        exclude_same_molecule=True, exclude_self_same_set=False
    )
    _, g_hh = compute_inter_rdf(
        hy_frames, hy_frames, hydrogen_mol_ids, hydrogen_mol_ids,
        combined_box, n_a=NHYD, n_b_valid=NHYD - 2, r_max=r_max, bin_width=bin_width,
        exclude_same_molecule=True, exclude_self_same_set=True
    )

    # Write RDF CSV
    with open(ANA_DIR / 'rdf_intermolecular_normalized.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['r_A', 'g_OO_inter', 'g_OH_inter', 'g_HH_inter'])
        for i in range(len(r)):
            w.writerow([f'{r[i]:.4f}', f'{g_oo[i]:.6f}', f'{g_oh[i]:.6f}', f'{g_hh[i]:.6f}'])

    # First-local-peak analysis
    oo_peak_r, oo_peak_g = find_first_local_peak(r, g_oo, 2.0, 6.0)
    oh_peak_r, oh_peak_g = find_first_local_peak(r, g_oh, 1.0, 4.0)
    hh_peak_r, hh_peak_g = find_first_local_peak(r, g_hh, 1.5, 4.0)

    oo_min_r, oo_min_g = find_first_minimum_after_peak(r, g_oo, oo_peak_r if oo_peak_r else 2.5, 6.0) if oo_peak_r else (None, None)
    oh_min_r, oh_min_g = find_first_minimum_after_peak(r, g_oh, oh_peak_r if oh_peak_r else 1.5, 4.0) if oh_peak_r else (None, None)
    hh_min_r, hh_min_g = find_first_minimum_after_peak(r, g_hh, hh_peak_r if hh_peak_r else 2.0, 4.0) if hh_peak_r else (None, None)

    # The O-H intermolecular RDF has a later/larger broad maximum near 3.25 A
    oh_later_peak_r, oh_later_peak_g = find_global_maximum(r, g_oh, 2.5, 4.0)

    large_r = {
        'OO': large_r_mean(g_oo, r),
        'OH': large_r_mean(g_oh, r),
        'HH': large_r_mean(g_hh, r),
    }
    approaches_one = all(abs(v - 1.0) < 0.1 for v in large_r.values() if not math.isnan(v))

    # Plot RDF
    plt.rcParams['font.size'] = 10
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=300)
    ax.plot(r, g_oo, 'b-', linewidth=1.2, label='O–O intermolecular')
    ax.plot(r, g_oh, 'g-', linewidth=1.2, label='O–H intermolecular')
    ax.plot(r, g_hh, 'r-', linewidth=1.2, label='H–H intermolecular')
    ax.axhline(1.0, color='k', linestyle='--', alpha=0.4, linewidth=0.8)
    ax.set_xlabel('r (Å)')
    ax.set_ylabel('g(r)')
    ax.set_xlim(0, 10)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'rdf_intermolecular_normalized.png', dpi=300)
    plt.close(fig)

    # Production thermodynamic plots
    plot_series(combined_time, combined_temp, 'Time (ps)', 'Temperature (K)',
                'temperature.png', color='firebrick', hline=300.0)
    plot_series(combined_time, combined_dens, 'Time (ps)', 'Density (g/cm³)',
                'density.png', color='steelblue')
    plot_series(combined_time, combined_pres, 'Time (ps)', 'Pressure (bar)',
                'pressure.png', color='seagreen')
    plot_series(combined_time, combined_pot, 'Time (ps)', 'Potential (kcal/mol)',
                'potential.png', color='darkorange')

    # Box volume plot
    box_volumes = combined_box[:, 0] * combined_box[:, 1] * combined_box[:, 2]
    plot_series(frame_times, box_volumes, 'Time (ps)', 'Box volume (Å³)',
                'box_volume.png', color='purple')

    # 80 ps Bussi-NPT equilibration plots
    prep_header, prep_records = read_mdout(PREP_DIR / 'bussi_npt_equilibration_segment01_80ps.mdout')
    prep = parse_mdout_records(prep_records)
    elapsed_time = prep['time_ps'] - 22.620

    # Density plot
    fig, ax = plt.subplots(figsize=(6, 4), dpi=300)
    ax.plot(elapsed_time, prep['density'], color='steelblue', linewidth=0.8)
    ax.set_xlabel('NPT equilibration time (ps)')
    ax.set_ylabel('Density (g/cm³)')
    ax.set_xlim(0, 80)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'npt_equilibration_80ps_density.png', dpi=300)
    plt.close(fig)

    # Temperature plot
    fig, ax = plt.subplots(figsize=(6, 4), dpi=300)
    ax.plot(elapsed_time, prep['temperature'], color='firebrick', linewidth=0.8)
    ax.set_xlabel('NPT equilibration time (ps)')
    ax.set_ylabel('Temperature (K)')
    ax.set_xlim(0, 80)
    ax.axhline(300.0, color='k', linestyle='--', alpha=0.3, linewidth=0.6)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / 'npt_equilibration_80ps_temperature.png', dpi=300)
    plt.close(fig)

    # Final analysis summary with package-relative paths
    def rel(p):
        try:
            return p.relative_to(PACKAGE_ROOT).as_posix()
        except ValueError:
            return str(p)

    # Determine console-log status from the segment02 directory
    seg02_console = SEG02_DIR / 'npt_production_segment02_4ps_console.log'
    seg02_full_console = SEG02_DIR / 'npt_production_segment02_4ps_full_console_output.log'
    seg02_powershell_transcript = SEG02_DIR / 'npt_production_segment02_4ps_powershell_transcript.log'

    console_log_state = {
        'powershell_transcript_exists': bool(seg02_console.exists() or seg02_powershell_transcript.exists()),
        'full_console_output_exists': bool(seg02_full_console.exists()),
    }

    # Read restart headers from actual files for the summary
    def read_header(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.readline().strip()

    seg01_rst_coord_header = read_header(SEG01_DIR / 'restart_6000_coordinate.txt')
    seg01_rst_vel_header = read_header(SEG01_DIR / 'restart_6000_velocity.txt')
    seg02_rst_coord_header = read_header(SEG02_DIR / 'npt_production_segment02_4ps_rst_coordinate.txt')
    seg02_rst_vel_header = read_header(SEG02_DIR / 'npt_production_segment02_4ps_rst_velocity.txt')

    # Check for NaN/Inf in key columns
    nan_or_inf = bool(
        np.any(~np.isfinite(combined_temp)) or
        np.any(~np.isfinite(combined_pres)) or
        np.any(~np.isfinite(combined_dens)) or
        np.any(~np.isfinite(combined_pot))
    )

    def all_finite(arr):
        return bool(np.all(np.isfinite(arr)))

    finite_data_check = (
        all_finite(prep['time_ps']) and all_finite(prep['temperature']) and
        all_finite(prep['pressure']) and all_finite(prep['potential']) and all_finite(prep['density']) and
        all_finite(seg01['time_ps']) and all_finite(seg01['temperature']) and
        all_finite(seg01['pressure']) and all_finite(seg01['potential']) and all_finite(seg01['density']) and
        all_finite(seg02['time_ps']) and all_finite(seg02['temperature']) and
        all_finite(seg02['pressure']) and all_finite(seg02['potential']) and all_finite(seg02['density'])
    )

    summary = {
        'validation': {
            'seg01_mdout_exists': (SEG01_DIR / 'npt_production_segment01_6ps.mdout').exists(),
            'seg02_mdout_exists': (SEG02_DIR / 'npt_production_segment02_4ps.mdout').exists(),
            'seg01_traj_exists': (SEG01_DIR / 'npt_production_segment01_6ps_traj.dat').exists(),
            'seg02_traj_exists': (SEG02_DIR / 'npt_production_segment02_4ps_traj.dat').exists(),
            'seg01_box_exists': (SEG01_DIR / 'npt_production_segment01_6ps_traj.box').exists(),
            'seg02_box_exists': (SEG02_DIR / 'npt_production_segment02_4ps_traj.box').exists(),
            'seg01_rst_coord_exists': (SEG01_DIR / 'restart_6000_coordinate.txt').exists(),
            'seg01_rst_vel_exists': (SEG01_DIR / 'restart_6000_velocity.txt').exists(),
            'seg02_rst_coord_exists': (SEG02_DIR / 'npt_production_segment02_4ps_rst_coordinate.txt').exists(),
            'seg02_rst_vel_exists': (SEG02_DIR / 'npt_production_segment02_4ps_rst_velocity.txt').exists(),
            'atom_names_exists': (SYSTEM_DIR / 'water_30A_randomized_atom_name.txt').exists(),
            'residue_exists': (SYSTEM_DIR / 'water_30A_randomized_residue.txt').exists(),
            'console_log_state': console_log_state,
            'seg01_rst_coord_header': seg01_rst_coord_header,
            'seg01_rst_vel_header': seg01_rst_vel_header,
            'seg02_rst_coord_header': seg02_rst_coord_header,
            'seg02_rst_vel_header': seg02_rst_vel_header,
            'seg01_rst_headers_synchronized': seg01_rst_coord_header == seg01_rst_vel_header,
            'seg02_rst_headers_synchronized': seg02_rst_coord_header == seg02_rst_vel_header,
            'seg02_rst_coord_sha256': sha256(SEG02_DIR / 'npt_production_segment02_4ps_rst_coordinate.txt'),
            'seg02_rst_vel_sha256': sha256(SEG02_DIR / 'npt_production_segment02_4ps_rst_velocity.txt'),
            'seg01_total_records': int(seg01['step'].size + 3),
            'seg01_accepted_records': int(seg01['step'].size),
            'seg01_excluded_tail_records': 3,
            'seg01_excluded_tail_steps': '6100, 6200, 6300',
            'seg02_total_records': int(seg02['step'].size),
            'seg01_last_time_ps': float(seg01['time_ps'][-1]),
            'seg02_first_time_ps': float(seg02['time_ps'][0]),
            'time_continuity_gap_ps': float(seg02['time_ps'][0] - seg01['time_ps'][-1]),
            'nan_or_inf_in_key_columns': nan_or_inf,
            'finite_data_check': finite_data_check,
            'seg01_traj_frames': int(seg01_traj.shape[0]),
            'seg02_traj_frames': int(seg02_traj.shape[0]),
            'seg01_traj_expected_frames': 6,
            'seg02_traj_expected_frames': 8,
            'seg01_traj_frame_count_ok': seg01_traj.shape[0] == 6,
            'seg02_traj_frame_count_ok': seg02_traj.shape[0] == 8,
            'seg01_box_frames': int(seg01_box.shape[0]),
            'seg02_box_frames': int(seg02_box.shape[0]),
            'natoms': NATOMS,
            'nmols': NMOLS,
            'n_oxygens': NOXY,
            'n_hydrogens': NHYD,
        },
        'thermodynamic_statistics': thermo_stats,
        'box_statistics': box_stats,
        'trends': {
            'temperature_slope_K_per_ps': linear_slope(combined_time[primary_mask], combined_temp[primary_mask]),
            'pressure_slope_bar_per_ps': linear_slope(combined_time[primary_mask], combined_pres[primary_mask]),
            'density_slope_g_cm3_per_ps': linear_slope(combined_time[primary_mask], combined_dens[primary_mask]),
            'potential_slope_kcal_mol_per_ps': linear_slope(combined_time[primary_mask], combined_pot[primary_mask]),
        },
        'structure': structure_stats,
        'rdf_peaks': {
            'OO_first_local_peak_A': oo_peak_r,
            'OO_first_local_peak_g': oo_peak_g,
            'OH_inter_first_local_peak_A': oh_peak_r,
            'OH_inter_first_local_peak_g': oh_peak_g,
            'OH_inter_later_broad_maximum_A': oh_later_peak_r,
            'OH_inter_later_broad_maximum_g': oh_later_peak_g,
            'HH_inter_first_local_peak_A': hh_peak_r,
            'HH_inter_first_local_peak_g': hh_peak_g,
            'OO_first_minimum_A': oo_min_r,
            'OO_first_minimum_g': oo_min_g,
            'OH_inter_first_minimum_A': oh_min_r,
            'OH_inter_first_minimum_g': oh_min_g,
            'HH_inter_first_minimum_A': hh_min_r,
            'HH_inter_first_minimum_g': hh_min_g,
            'large_r_8_10_A_mean': large_r,
            'large_r_approaches_one': approaches_one,
        },
        'final_classification': 'FINAL_10PS_PRACTICAL_NPT_PRODUCTION_ANALYSIS_ACCEPTED_WITH_SHORT_SAMPLING_LIMITATION',
        'output_directory': rel(ANA_DIR),
        'generated_files': {
            'report': rel(ANA_DIR / 'FINAL_10PS_NPT_PRODUCTION_ANALYSIS.md'),
            'thermodynamics_csv': rel(ANA_DIR / 'production_thermodynamics.csv'),
            'box_csv': rel(ANA_DIR / 'box_frames.csv'),
            'block_statistics_csv': rel(ANA_DIR / 'block_statistics.csv'),
            'structure_csv': rel(ANA_DIR / 'structure.csv'),
            'validation_csv': rel(ANA_DIR / 'validation.csv'),
            'rdf_intermolecular_normalized_csv': rel(ANA_DIR / 'rdf_intermolecular_normalized.csv'),
            'temperature_plot': rel(FIG_DIR / 'temperature.png'),
            'pressure_plot': rel(FIG_DIR / 'pressure.png'),
            'density_plot': rel(FIG_DIR / 'density.png'),
            'potential_plot': rel(FIG_DIR / 'potential.png'),
            'box_volume_plot': rel(FIG_DIR / 'box_volume.png'),
            'rdf_plot': rel(FIG_DIR / 'rdf_intermolecular_normalized.png'),
            'npt_equilibration_80ps_density_plot': rel(FIG_DIR / 'npt_equilibration_80ps_density.png'),
            'npt_equilibration_80ps_temperature_plot': rel(FIG_DIR / 'npt_equilibration_80ps_temperature.png'),
        },
        'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
    }

    with open(ANA_DIR / 'final_analysis_summary.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    # Validation CSV
    with open(ANA_DIR / 'validation.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['key', 'value'])
        for k, v in summary['validation'].items():
            w.writerow([k, v])

    # Write final report
    write_report(summary, oo_peak_r, oo_peak_g, oh_peak_r, oh_peak_g, hh_peak_r, hh_peak_g,
                 oo_min_r, oo_min_g, oh_min_r, oh_min_g, hh_min_r, hh_min_g,
                 oh_later_peak_r, oh_later_peak_g, large_r, approaches_one)

    print('Package-local analysis reproduction complete.')
    print(f'Outputs in {ANA_DIR} and {FIG_DIR}')


def write_report(summary, oo_peak_r, oo_peak_g, oh_peak_r, oh_peak_g, hh_peak_r, hh_peak_g,
                 oo_min_r, oo_min_g, oh_min_r, oh_min_g, hh_min_r, hh_min_g,
                 oh_later_peak_r, oh_later_peak_g, large_r, approaches_one):
    ts = summary['analysis_timestamp']
    t = thermo = summary['thermodynamic_statistics']
    b = summary['box_statistics']
    s = summary['structure']
    tr = summary['trends']
    total_frames = summary['validation']['seg01_traj_frames'] + summary['validation']['seg02_traj_frames']

    def fmt(v, prec=2):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return 'not resolved'
        return f'{v:.{prec}f}'

    def stats_lines(d, unit=''):
        return f"{d['mean']:.4f} ± {d['std']:.4f} {unit} (n={d['n']}, min={d['min']:.4f}, max={d['max']:.4f})"

    report = f"""# Final 10 ps NPT Production Analysis

**Pass:** `11B_npt_production_segment02_4ps_20260815_100551`  
**Analysis date:** {ts}  
**Final classification:** `{summary['final_classification']}`

## 1. Production validation

This is a **segmented, practical 10 ps NPT production** composed of:
- **Segment 01**: accepted synchronized production from `11A` up to local step 6000 (6 ps). The segment was interrupted by an **unexpected laptop/system restart**, not a native SPONGE/runtime failure.
- **Segment 02**: fresh 4 ps continuation from the synchronized 6000-step restart.

The unsynchronized 6100–6300 tail from Segment 01 (steps 6100, 6200, 6300) was **excluded** from analysis. The laptop-restart segmentation means stochastic continuity is **not** claimed; only ensemble-level practical analysis is reported.

| Item | Status |
|---|---|
| atom_names_exists | {summary['validation']['atom_names_exists']} |
| residue_exists | {summary['validation']['residue_exists']} |
| seg01_box_exists | {summary['validation']['seg01_box_exists']} |
| seg01_mdout_exists | {summary['validation']['seg01_mdout_exists']} |
| seg01_rst_coord_exists | {summary['validation']['seg01_rst_coord_exists']} |
| seg01_rst_vel_exists | {summary['validation']['seg01_rst_vel_exists']} |
| seg01_traj_exists | {summary['validation']['seg01_traj_exists']} |
| seg02_box_exists | {summary['validation']['seg02_box_exists']} |
| seg02_mdout_exists | {summary['validation']['seg02_mdout_exists']} |
| seg02_rst_coord_exists | {summary['validation']['seg02_rst_coord_exists']} |
| seg02_rst_vel_exists | {summary['validation']['seg02_rst_vel_exists']} |
| seg02_traj_exists | {summary['validation']['seg02_traj_exists']} |
| powershell_transcript_exists | {summary['validation']['console_log_state']['powershell_transcript_exists']} |
| full_console_output_exists | {summary['validation']['console_log_state']['full_console_output_exists']} |
| nan_or_inf_in_key_columns | {summary['validation']['nan_or_inf_in_key_columns']} |

### 1.2 Restart headers/hashes

| File | Header | SHA256 |
|---|---|---|
| Segment 01 coordinate | `{summary['validation']['seg01_rst_coord_header']}` | B4AC947DF619322B15C6F2FF4728E77664348C29CC741B94F012D7271074477D |
| Segment 01 velocity | `{summary['validation']['seg01_rst_vel_header']}` | FCD42A09943905EF22877E4AC1E92AE0ACD13FF330304E1CD0D02E9F8711667A |
| Segment 02 coordinate | `{summary['validation']['seg02_rst_coord_header']}` | {summary['validation']['seg02_rst_coord_sha256']} |
| Segment 02 velocity | `{summary['validation']['seg02_rst_vel_header']}` | {summary['validation']['seg02_rst_vel_sha256']} |

### 1.3 Record/frame counts and continuity

- Segment 01 accepted mdout records: {summary['validation']['seg01_accepted_records']} (accepted through step 6000; excluded diagnostic tail: {summary['validation']['seg01_excluded_tail_steps']})
- Segment 02 mdout records: {summary['validation']['seg02_total_records']}
- Segment 01 trajectory frames: {summary['validation']['seg01_traj_frames']} (expected 6)
- Segment 02 trajectory frames: {summary['validation']['seg02_traj_frames']} (expected 8)
- Segment 01 last time: {summary['validation']['seg01_last_time_ps']:.3f} ps
- Segment 02 first time: {summary['validation']['seg02_first_time_ps']:.3f} ps
- Time continuity gap: {summary['validation']['time_continuity_gap_ps']:.3f} ps
- NaN/Inf in key columns: {summary['validation']['nan_or_inf_in_key_columns']}

## 2. Thermodynamic analysis

### 2.1 Full 10 ps, burn-in (102.720–107.620 ps), and primary (107.720–112.620 ps) windows

The frozen primary analysis window is **107.720–112.620 ps** (50 records). The record at 107.620 ps belongs to the burn-in window, not the primary window.

| Window | Records | Time range (ps) | T (K) mean ± SD | P (bar) mean ± SD | ρ (g/cm³) mean ± SD | U (kcal/mol) mean ± SD |
|---|---|---|---|---|---|---|
| full_10ps | {t['full_10ps']['n_records']} | {t['full_10ps']['time_range_ps'][0]:.3f}–{t['full_10ps']['time_range_ps'][1]:.3f} | {stats_lines(t['full_10ps']['temperature_K'])} | {stats_lines(t['full_10ps']['pressure_bar'])} | {stats_lines(t['full_10ps']['density_g_cm3'])} | {stats_lines(t['full_10ps']['potential_kcal_mol'])} |
| burn_in_0_5ps | {t['burn_in_0_5ps']['n_records']} | {t['burn_in_0_5ps']['time_range_ps'][0]:.3f}–{t['burn_in_0_5ps']['time_range_ps'][1]:.3f} | {stats_lines(t['burn_in_0_5ps']['temperature_K'])} | {stats_lines(t['burn_in_0_5ps']['pressure_bar'])} | {stats_lines(t['burn_in_0_5ps']['density_g_cm3'])} | {stats_lines(t['burn_in_0_5ps']['potential_kcal_mol'])} |
| primary_5_10ps | {t['primary_5_10ps']['n_records']} | {t['primary_5_10ps']['time_range_ps'][0]:.3f}–{t['primary_5_10ps']['time_range_ps'][1]:.3f} | {stats_lines(t['primary_5_10ps']['temperature_K'])} | {stats_lines(t['primary_5_10ps']['pressure_bar'])} | {stats_lines(t['primary_5_10ps']['density_g_cm3'])} | {stats_lines(t['primary_5_10ps']['potential_kcal_mol'])} |

### 2.2 Box / volume statistics

| Window | Frames | Time range (ps) | Volume (Å³) mean ± SD |
|---|---|---|---|---|
| full_10ps | {b['full_10ps']['n_frames']} | {b['full_10ps']['time_range_ps'][0]:.3f}–{b['full_10ps']['time_range_ps'][1]:.3f} | {stats_lines(b['full_10ps']['volume_A3'])} |
| burn_in_0_5ps | {b['burn_in_0_5ps']['n_frames']} | {b['burn_in_0_5ps']['time_range_ps'][0]:.3f}–{b['burn_in_0_5ps']['time_range_ps'][1]:.3f} | {stats_lines(b['burn_in_0_5ps']['volume_A3'])} |
| primary_5_10ps | {b['primary_5_10ps']['n_frames']} | {b['primary_5_10ps']['time_range_ps'][0]:.3f}–{b['primary_5_10ps']['time_range_ps'][1]:.3f} | {stats_lines(b['primary_5_10ps']['volume_A3'])} |

The primary box window includes the 108.620 ps Segment 01 frame and all eight Segment 02 frames; it is **not** defined as Segment 02 only.

### 2.3 Linear trends in primary window

- Temperature slope: {tr['temperature_slope_K_per_ps']:.4f} K/ps
- Pressure slope: {tr['pressure_slope_bar_per_ps']:.4f} bar/ps
- Density slope: {tr['density_slope_g_cm3_per_ps']:.6f} g/cm³/ps
- Potential slope: {tr['potential_slope_kcal_mol_per_ps']:.4f} kcal/mol/ps

## 3. TIP3P intramolecular geometry

All intramolecular geometry calculations use the **minimum-image convention** with the fluctuating per-frame box. These values are averaged over all {total_frames} accepted trajectory frames (Segment 01 + Segment 02).

| Quantity | Mean ± SD | Min | Max | N |
|---|---|---|---|---|
| O–H distance (Å) | {s['OH_distance_A']['mean']:.6f} ± {s['OH_distance_A']['std']:.6f} | {s['OH_distance_A']['min']:.6f} | {s['OH_distance_A']['max']:.6f} | {s['OH_distance_A']['n']} |
| H–H distance (Å) | {s['HH_distance_A']['mean']:.6f} ± {s['HH_distance_A']['std']:.6f} | {s['HH_distance_A']['min']:.6f} | {s['HH_distance_A']['max']:.6f} | {s['HH_distance_A']['n']} |
| H–O–H angle (°) | {s['HOH_angle_deg']['mean']:.6f} ± {s['HOH_angle_deg']['std']:.6f} | {s['HOH_angle_deg']['min']:.6f} | {s['HOH_angle_deg']['max']:.6f} | {s['HOH_angle_deg']['n']} |

| Structural check | Observed value | Threshold status |
|---|---:|---|
| Minimum intermolecular O–O distance | {s['min_inter_OO_A']['min']:.3f} Å | threshold check: {'PASS (>2.0 Å)' if s['min_inter_OO_A']['min'] >= 2.0 else 'FAIL (<2.0 Å)'} |
| Minimum intermolecular H–H distance | {s['min_inter_HH_A']['min']:.3f} Å | threshold check: {'PASS (>1.0 Å)' if s['min_inter_HH_A']['min'] >= 1.0 else 'FAIL (<1.0 Å)'} |
| Minimum intermolecular O–H distance | {s['min_inter_OH_A']['min']:.3f} Å | threshold check: {'PASS (>0.5 Å)' if s['min_inter_OH_A']['min'] >= 0.5 else 'FAIL (<0.5 Å)'} |
| H–O–H angle range | {s['HOH_angle_deg']['min']:.3f}–{s['HOH_angle_deg']['max']:.3f} ° | threshold check: {'PASS (90–120°)' if s['HOH_angle_deg']['min'] >= 90 and s['HOH_angle_deg']['max'] <= 120 else 'FAIL (outside 90–120°)'} |

## 4. Radial distribution functions (intermolecular-only)

The intermolecular RDFs are normalized using:
- atom-axis species counts (`coords_a.shape[1]`, `coords_b.shape[1]`),
- per-frame box volumes,
- same-molecule exclusion for O–H and H–H,
- valid target partner counts: O–O = 861, O–H intermolecular = 1722, H–H intermolecular = 1722.

These are **illustrative** due to only 14 accepted trajectory frames.

| Species | First local peak r (Å) | g(r) | First minimum r (Å) | g(r) |
|---|---|---|---|---|
| O–O | {fmt(oo_peak_r, 2)} | {fmt(oo_peak_g, 3)} | {fmt(oo_min_r, 2)} | {fmt(oo_min_g, 3)} |
| O–H intermolecular | {fmt(oh_peak_r, 2)} | {fmt(oh_peak_g, 3)} | {fmt(oh_min_r, 2)} | {fmt(oh_min_g, 3)} |
| H–H intermolecular | {fmt(hh_peak_r, 2)} | {fmt(hh_peak_g, 3)} | {fmt(hh_min_r, 2)} | {fmt(hh_min_g, 3)} |

The O–H intermolecular curve also has a later, broader maximum near **{fmt(oh_later_peak_r, 2)} Å** with g(r) ≈ {fmt(oh_later_peak_g, 3)}. This is labelled as a later/second maximum, not the first local peak.

Large-r (8–10 Å) mean g(r):
- O–O: {large_r['OO']:.5f}
- O–H: {large_r['OH']:.5f}
- H–H: {large_r['HH']:.5f}

Large-r values approach 1 within the tolerance |mean−1| < 0.1: **{approaches_one}**.

## 5. Generated outputs

All analysis outputs and figures are generated by `06_protocol_and_scripts/reproduce_final_analysis_from_package.py` using only files contained in this package. Package-relative paths are used so the package remains understandable after being moved.

## 6. Limitations and caveats

- 10 ps total production is very short for liquid water.
- The production is segmented due to a laptop/system restart; stochastic continuity is not claimed.
- Pressure estimates are noisy on this timescale.
- RDFs are illustrative only due to only 14 accepted trajectory frames.
- No equilibrium/convergence claims are made.
- The 80 ps Bussi-NPT equilibration and the 10 ps production are the accepted scientific endpoints; earlier attempts and superseded planning documents are retained only for provenance.
"""
    with open(ANA_DIR / 'FINAL_10PS_NPT_PRODUCTION_ANALYSIS.md', 'w', encoding='utf-8') as f:
        f.write(report)


if __name__ == '__main__':
    main()
