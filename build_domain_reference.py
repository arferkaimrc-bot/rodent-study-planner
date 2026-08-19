# -*- coding: utf-8 -*-
"""Build the applicability-domain reference for every trained model.

A QSAR model only makes meaningful predictions for compounds that resemble the
ones it was trained on (its "applicability domain" — one of the OECD principles
for QSAR validation). Without this check a model happily returns a confident
number for water or a polymer.

For each model this stores the packed Morgan fingerprints of its training set.
At prediction time the platform measures the query compound's highest Tanimoto
similarity to that set; below a threshold the prediction is withheld rather than
shown as a normal result.

Run once:  python build_domain_reference.py
"""
import os
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

OUT = 'ml_models'
FP_BITS = 256
FP_RADIUS = 2

# model key -> (dataset file, SMILES column)
DATASETS = {
    'herg':          ('data/herg.tab', 'Drug'),
    'dili':          ('data/dili.tab', 'Drug'),
    'ames':          ('data/ames.tab', 'Drug'),
    'bbb':           ('data/bbb_martins.tab', 'Drug'),
    'cyp3a4':        ('data/cyp3a4_veith.tab', 'Drug'),
    'cyp2d6':        ('data/cyp2d6_veith.tab', 'Drug'),
    'cyp2c9':        ('data/cyp2c9_veith.tab', 'Drug'),
    'bioavail':      ('data/bioavailability_ma.tab', 'Drug'),
    'solubility':    ('data/solubility_aqsoldb.tab', 'Drug'),
    'halflife':      ('data/half_life_obach.tab', 'Drug'),
    'caco2':         ('data/caco2_wang.tab', 'Drug'),
    'lipophilicity': ('data/lipophilicity_astrazeneca.tab', 'Drug'),
    'ppbr':          ('data/ppbr_az.tab', 'Drug'),
    'ld50':          ('data/ld50_zhu.tab', 'X'),      # this file uses column X
}


def fingerprint(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    fp = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol, radius=FP_RADIUS, nBits=FP_BITS)
    return np.frombuffer(np.packbits(np.array(fp, dtype=np.uint8)).tobytes(), dtype=np.uint8)


def main():
    total_kb = 0
    for key, (path, col) in DATASETS.items():
        if not os.path.exists(path):
            print(f"  skip {key}: {path} not found")
            continue
        df = pd.read_csv(path, sep='\t')
        if col not in df.columns:
            col = 'Drug' if 'Drug' in df.columns else df.columns[1]
        fps = [f for f in (fingerprint(s) for s in df[col]) if f is not None]
        arr = np.vstack(fps)                       # (n, 32) packed bits
        out = os.path.join(OUT, f'{key}_domain.npz')
        np.savez_compressed(out, fps=arr, n=len(arr))
        kb = os.path.getsize(out) / 1024
        total_kb += kb
        print(f"  {key:<14} {len(arr):>6} compounds  →  {kb:6.0f} KB")
    print(f"\n  total: {total_kb/1024:.1f} MB")


if __name__ == '__main__':
    main()
