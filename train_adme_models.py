"""
Train a BATCH of ADME regression models on free TDC datasets, reusing the exact
same featurization as the other models (7 RDKit descriptors + 256-bit Morgan
fingerprint) so the app's `_featurize_smiles` serves them all.

Models (all free — Therapeutics Data Commons):
  clearance      Clearance_Hepatocyte_AZ   (log-trained; µL/min/10^6 cells)
  lipophilicity  Lipophilicity_AstraZeneca (logD 7.4)
  caco2          Caco2_Wang                (log Papp, cm/s)
  ppbr           PPBR_AZ                   (% plasma protein bound)

Output per model: ml_models/<key>_model.pkl + ml_models/<key>_meta.json
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

# key, TDC name, log10-transform Y?, label, unit, source
CONFIGS = [
    ('clearance', 'Clearance_Hepatocyte_AZ', True,
     'Clearance', 'µL/min/10⁶ cells', 'TDC Clearance_Hepatocyte_AZ'),
    ('lipophilicity', 'Lipophilicity_AstraZeneca', False,
     'Lipophilicity (LogD)', '', 'TDC Lipophilicity_AstraZeneca'),
    ('caco2', 'Caco2_Wang', False,
     'Caco-2 permeability', 'log Papp', 'TDC Caco2_Wang'),
    ('ppbr', 'PPBR_AZ', False,
     'Plasma protein binding', '%', 'TDC PPBR_AZ'),
]


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
    fp = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=FP_BITS)
    return [d[n] for n in DESC_NAMES] + list(fp)


def main():
    from tdc.single_pred import ADME
    os.makedirs(OUT, exist_ok=True)
    for key, name, use_log, label, unit, source in CONFIGS:
        df = ADME(name=name).get_data()
        X, y = [], []
        for smi, val in zip(df['Drug'], df['Y']):
            f = featurize(smi)
            if f is None or val is None:
                continue
            if use_log and val <= 0:
                continue
            X.append(f)
            y.append(np.log10(float(val)) if use_log else float(val))
        X, y = np.array(X), np.array(y)
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.15, random_state=42)
        model = GradientBoostingRegressor(
            n_estimators=400, learning_rate=0.05, max_depth=3,
            subsample=0.8, random_state=42)
        model.fit(X_tr, y_tr)
        mae = float(mean_absolute_error(y_te, model.predict(X_te)))
        r2 = float(r2_score(y_te, model.predict(X_te)))
        joblib.dump(model, os.path.join(OUT, f'{key}_model.pkl'))
        meta = {
            'key': key, 'task': 'regression', 'label': label, 'unit': unit,
            'log': bool(use_log),
            'descriptor_names': DESC_NAMES, 'fp_bits': FP_BITS, 'fp_radius': 2,
            'n_train': int(len(X_tr)), 'n_test': int(len(X_te)),
            'test_mae': mae, 'test_r2': r2, 'source': source,
        }
        json.dump(meta, open(os.path.join(OUT, f'{key}_meta.json'), 'w'), indent=2)
        print(f"{key:14s} {label:24s} n={len(X):5d}  R2={r2:.3f}  MAE={mae:.3f}{' (log)' if use_log else ''}")


if __name__ == '__main__':
    main()
