"""
Train a BATCH of binary safety / ADME classifiers on free TDC datasets, reusing
the exact same featurization as the LD50 / solubility models (7 RDKit descriptors
+ 256-bit Morgan fingerprint), so the app's `_featurize_smiles` serves them all.

Each model outputs a probability (0-1) for its positive class; the app surfaces a
Low/High flag with that probability and the benchmark ROC-AUC as confidence.

All datasets are free (Therapeutics Data Commons). Output per model:
    ml_models/<key>_model.pkl + ml_models/<key>_meta.json
"""
import os
import json
import numpy as np
import joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, Lipinski, rdMolDescriptors
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

OUT = 'ml_models'
FP_BITS = 256
DESC_NAMES = ['molecular_weight', 'logp', 'h_donors', 'h_acceptors',
              'rotatable_bonds', 'aromatic_rings', 'tpsa']

# key, TDC group, TDC name, human label, meaning of positive (Y==1), source
CONFIGS = [
    ('herg', 'Tox', 'hERG', 'hERG cardiotoxicity',
     'a hERG blocker (potential cardiotoxicity)', 'TDC hERG (Karim et al.)'),
    ('dili', 'Tox', 'DILI', 'Hepatotoxicity (DILI)',
     'drug-induced liver injury', 'TDC DILI'),
    ('ames', 'Tox', 'AMES', 'Mutagenicity (Ames)',
     'mutagenic (Ames positive)', 'TDC AMES (Xu et al.)'),
    ('bbb', 'ADME', 'BBB_Martins', 'Blood-brain barrier',
     'able to cross the blood-brain barrier', 'TDC BBB_Martins'),
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


def load(group_name, name):
    from tdc.single_pred import Tox, ADME
    grp = {'Tox': Tox, 'ADME': ADME}[group_name]
    df = grp(name=name).get_data()
    return df['Drug'].tolist(), df['Y'].tolist()


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = []
    for key, group, name, label, meaning, source in CONFIGS:
        smiles_list, labels = load(group, name)
        X, y = [], []
        for smi, lab in zip(smiles_list, labels):
            f = featurize(smi)
            if f is None:
                continue
            X.append(f)
            y.append(int(lab))
        X, y = np.array(X), np.array(y)
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.15, random_state=42, stratify=y)
        clf = GradientBoostingClassifier(
            n_estimators=300, learning_rate=0.05, max_depth=3,
            subsample=0.8, random_state=42)
        clf.fit(X_tr, y_tr)
        auc = float(roc_auc_score(y_te, clf.predict_proba(X_te)[:, 1]))
        joblib.dump(clf, os.path.join(OUT, f'{key}_model.pkl'))
        meta = {
            'key': key, 'task': 'classification', 'label': label,
            'positive_meaning': meaning,
            'descriptor_names': DESC_NAMES, 'fp_bits': FP_BITS, 'fp_radius': 2,
            'n_train': int(len(X_tr)), 'n_test': int(len(X_te)),
            'test_auc': auc, 'source': source,
        }
        json.dump(meta, open(os.path.join(OUT, f'{key}_meta.json'), 'w'), indent=2)
        summary.append((key, label, len(X), round(auc, 3)))
        print(f"{key:6s} {label:22s} n={len(X):5d}  AUC={auc:.3f}")
    print("\nDone:", summary)


if __name__ == '__main__':
    main()
