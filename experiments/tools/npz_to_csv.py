#!/usr/bin/env python3
"""Convert one or more .npz time-series files to CSV.

Usage:
  python experiments/tools/npz_to_csv.py <npz1> [<npz2> ...] -o <outdir>

Creates one CSV per .npz in the output directory. CSV columns are the sorted keys
with `t` first if present (time in minutes), otherwise keys order from file.
"""
import argparse
import os
import numpy as np


def npz_to_csv(npz_path: str, out_dir: str) -> str:
    data = np.load(npz_path)
    keys = list(data.keys())
    # Put time first if exists
    if 't' in keys:
        keys = ['t'] + [k for k in keys if k != 't']
    # Stack into 2D array (len(keys) columns)
    arrays = [np.asarray(data[k]) for k in keys]
    # Ensure 2D shape: (n_rows, n_cols)
    # transpose if arrays are 1D
    try:
        stacked = np.vstack(arrays).T
    except Exception:
        # fallback: attempt to broadcast
        maxlen = max(a.shape[0] for a in arrays)
        arr2 = [np.pad(a, (0, maxlen - a.shape[0]), constant_values=np.nan) if a.shape[0] < maxlen else a for a in arrays]
        stacked = np.vstack(arr2).T

    base = os.path.splitext(os.path.basename(npz_path))[0]
    out_csv = os.path.join(out_dir, base + '.csv')
    os.makedirs(out_dir, exist_ok=True)
    # Write header and rows
    header = ','.join(keys)
    fmt = ','.join(['%s'] * len(keys))
    with open(out_csv, 'w', encoding='utf-8') as f:
        f.write(header + '\n')
        for row in stacked:
            # Convert numpy types to Python scalars and format
            f.write(','.join([format(x, '.6g') if isinstance(x, (float, np.floating)) or isinstance(x, (int, np.integer)) else str(x) for x in row]) + '\n')
    return out_csv


def main():
    p = argparse.ArgumentParser()
    p.add_argument('npz_files', nargs='+')
    p.add_argument('-o', '--outdir', required=True)
    args = p.parse_args()
    out_files = []
    for npz in args.npz_files:
        if not os.path.isfile(npz):
            print(f"WARN: not found: {npz}")
            continue
        try:
            out = npz_to_csv(npz, args.outdir)
            out_files.append(out)
            print(f"Wrote {out}")
        except Exception as e:
            print(f"ERROR converting {npz}: {e}")
    if not out_files:
        print("No files written.")


if __name__ == '__main__':
    main()
