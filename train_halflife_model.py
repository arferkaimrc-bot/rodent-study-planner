"""
Train an aqueous half-life regression model on the TDC Half_Life_Obach dataset
(Obach et al. 2008) — 667 compounds, HUMAN plasma half-life (hours).

Label is log10(half-life in hours) because the raw range is huge (0.06–1200 h).
Predict back with:  hours = 10 ** y_pred.

IMPORTANT (honesty): this is HUMAN pharmacokinetics.  Rodent half-lives are
usually SHORTER (faster metabolism), so the app uses this as a *relative*
indicator to suggest dosing frequency — not an absolute rodent value.

Featurization is IDENTICAL to the LD50 / solubility models (7 RDKit descriptors
+ 256-bit Morgan fingerprint) so the app's existing `_featurize_smiles` is reused.

Output: ml_models/halflife_model.pkl, ml_models/halflife_meta.json
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
DESC_NAMES = ['molecular_weight', 'logp', 'h_donors', 'h_acceptors',
              'rotatable_bonds', 'aromatic_rings', 'tpsa']


def featurize(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    d = {
        'molecular_weight': Descriptors.MolWt(mol),
        'logp': Crippen.MolLogP(mol),
        'h_donors': Lipinski.NumHDonors(mol),
        'h_acceptors': Lipinski.NumHAcceptors(mol),
        'rotatable_bonds': Lipinski.NumRotatableBonds(mol),
        'aromatic_rings': Lipinski.NumAromaticRings(mol),
        'tpsa': Descriptors.TPSA(mol),
    }
    desc_vec = [d[n] for n in DESC_NAMES]
    fp = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=FP_BITS)
    return desc_vec + list(fp)


def main():
    from tdc.single_pred import ADME
    df = ADME(name='Half_Life_Obach').get_data()
    print(f"Loaded {len(df)} rows")

    X, y = [], []
    skipped = 0
    for smiles, hours in zip(df['Drug'], df['Y']):
        feats = featurize(smiles)
        if feats is None or hours is None or hours <= 0:
            skipped += 1
            continue
        X.append(feats)
        y.append(np.log10(float(hours)))   # log10(half-life in hours)
    X = np.array(X)
    y = np.array(y)
    print(f"Featurized {len(X)} compounds ({skipped} skipped)")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.15, random_state=42)
    model = GradientBoostingRegressor(
        n_estimators=400, learning_rate=0.05, max_depth=3,
        subsample=0.8, random_state=42
    )
    model.fit(X_tr, y_tr)

    for name, Xs, ys in [('train', X_tr, y_tr), ('test', X_te, y_te)]:
        pred = model.predict(Xs)
        print(f"{name}: MAE={mean_absolute_error(ys, pred):.3f}  R2={r2_score(ys, pred):.3f}  (log10 hours)")

    os.makedirs(OUT, exist_ok=True)
    joblib.dump(model, os.path.join(OUT, 'halflife_model.pkl'))
    meta = {
        'label': 'log10_half_life_hours',
        'species': 'human',   # Obach dataset; used as a relative indicator only
        'descriptor_names': DESC_NAMES,
        'fp_bits': FP_BITS, 'fp_radius': 2,
        'n_train': int(len(X_tr)), 'n_test': int(len(X_te)),
        'test_mae': float(mean_absolute_error(y_te, model.predict(X_te))),
        'test_r2': float(r2_score(y_te, model.predict(X_te))),
        'source': 'TDC Half_Life_Obach (Obach et al. 2008)',
    }
    json.dump(meta, open(os.path.join(OUT, 'halflife_meta.json'), 'w'), indent=2)
    print("Saved model + meta to", OUT)
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
