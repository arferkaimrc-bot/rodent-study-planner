"""
Train a REAL aqueous-solubility regression model on the TDC Solubility_AqSolDB
dataset (Sorkun et al. 2019) — ~9,982 compounds.

Label Y = logS = log10(aqueous solubility in mol/L).  Higher = more soluble.

Why: solubility drives vehicle / formulation choice for in-vivo dosing —
a poorly soluble compound needs a co-solvent (DMSO/cyclodextrin) rather than
plain saline.  This ML estimate feeds the platform's dosing recommendations
when no measured solubility is available (same hybrid pattern as LD50).

Featurization is IDENTICAL to the LD50 model (7 RDKit descriptors + 256-bit
Morgan fingerprint) so the app's existing `featurize()` path is reused as-is.

Output: ml_models/solubility_model.pkl, ml_models/solubility_meta.json
"""
import os
import json
import numpy as np
import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, Lipinski, rdMolDescriptors
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

OUT = 'ml_models'
FP_BITS = 256

# Same 7 descriptors the app already computes (names kept identical for reuse)
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
    return desc_vec + list(fp)


def load_data():
    from tdc.single_pred import ADME
    df = ADME(name='Solubility_AqSolDB').get_data()
    return df['Drug'].tolist(), df['Y'].tolist()   # SMILES, logS


def main():
    smiles_list, labels = load_data()
    print(f"Loaded {len(smiles_list)} rows")

    X, y = [], []
    skipped = 0
    for smiles, label in zip(smiles_list, labels):
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
    joblib.dump(model, os.path.join(OUT, 'solubility_model.pkl'))
    meta = {
        'label': 'log_solubility_logS_mol_per_L',
        'descriptor_names': DESC_NAMES,
        'fp_bits': FP_BITS, 'fp_radius': 2,
        'n_train': int(len(X_tr)), 'n_test': int(len(X_te)),
        'test_mae': float(mean_absolute_error(y_te, model.predict(X_te))),
        'test_r2': float(r2_score(y_te, model.predict(X_te))),
        'source': 'TDC Solubility_AqSolDB (Sorkun et al. 2019)',
    }
    json.dump(meta, open(os.path.join(OUT, 'solubility_meta.json'), 'w'), indent=2)
    print("Saved model + meta to", OUT)
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
