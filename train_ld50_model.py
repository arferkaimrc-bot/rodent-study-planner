"""
Train a REAL LD50 (acute toxicity) regression model on the TDC LD50_Zhu dataset.

Dataset: 7385 compounds, rat oral acute toxicity.
Label Y = -log10(LD50 in mol/kg).  Higher Y = MORE toxic (smaller LD50).

To convert model output back to mg/kg:
    mol_per_kg = 10 ** (-Y)
    ld50_mg_kg = mol_per_kg * MolWt * 1000

Output: ml_models/ld50_model.pkl, ml_models/ld50_scaler.pkl, ml_models/ld50_meta.json
This replaces the old hand-crafted score-based LD50 heuristic with a model
trained on real experimental data.
"""
import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, Lipinski, rdMolDescriptors
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

DATA = 'training_data/ld50_zhu.tab'
OUT = 'ml_models'
FP_BITS = 256

# The 7 descriptors the app already computes (keep names identical for reuse)
DESC_NAMES = ['molecular_weight', 'logp', 'h_donors', 'h_acceptors',
              'rotatable_bonds', 'aromatic_rings', 'tpsa']


def descriptors_from_mol(mol):
    return {
        'molecular_weight': Descriptors.MolWt(mol),
        'logp': Crippen.MolLogP(mol),
        'h_donors': Lipinski.NumHDonors(mol),
        'h_acceptors': Lipinski.NumHAcceptors(mol),
        'rotatable_bonds': Lipinski.NumRotatableBonds(mol),
        'aromatic_rings': Lipinski.NumAromaticRings(mol),
        'tpsa': Descriptors.TPSA(mol),
    }


def featurize(smiles):
    """Return a feature vector (7 descriptors + Morgan fingerprint) or None."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    d = descriptors_from_mol(mol)
    desc_vec = [d[n] for n in DESC_NAMES]
    fp = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=FP_BITS)
    fp_vec = list(fp)
    return desc_vec + fp_vec


def main():
    df = pd.read_csv(DATA, sep='\t')
    print(f"Loaded {len(df)} rows")

    X, y = [], []
    skipped = 0
    for smiles, label in zip(df['X'], df['Y']):
        feats = featurize(smiles)
        if feats is None:
            skipped += 1
            continue
        X.append(feats)
        y.append(label)
    X = np.array(X)
    y = np.array(y)
    print(f"Featurized {len(X)} compounds ({skipped} skipped)")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.15, random_state=42)

    model = GradientBoostingRegressor(
        n_estimators=400, learning_rate=0.05, max_depth=4,
        subsample=0.8, random_state=42
    )
    model.fit(X_tr, y_tr)

    for name, Xs, ys in [('train', X_tr, y_tr), ('test', X_te, y_te)]:
        pred = model.predict(Xs)
        print(f"{name}: MAE={mean_absolute_error(ys, pred):.3f}  R2={r2_score(ys, pred):.3f}")

    os.makedirs(OUT, exist_ok=True)
    joblib.dump(model, os.path.join(OUT, 'ld50_model.pkl'))
    meta = {
        'label': 'ld50_neg_log10_mol_per_kg',
        'species': 'rat', 'route': 'oral',
        'descriptor_names': DESC_NAMES,
        'fp_bits': FP_BITS, 'fp_radius': 2,
        'n_train': int(len(X_tr)), 'n_test': int(len(X_te)),
        'test_mae': float(mean_absolute_error(y_te, model.predict(X_te))),
        'test_r2': float(r2_score(y_te, model.predict(X_te))),
        'source': 'TDC LD50_Zhu (Zhu et al. 2009)',
    }
    json.dump(meta, open(os.path.join(OUT, 'ld50_meta.json'), 'w'), indent=2)
    print("Saved model + meta to", OUT)
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
