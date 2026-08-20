# -*- coding: utf-8 -*-
"""Train the outcome-variability model on MPD (mouse) + RGD (rat) measurements.

The sample-size calculation needs the dispersion of the outcome being measured.
A fixed Cohen's d = 0.8 returns the same N whatever the experiment, which is
wrong in both directions: body weight varies ~11% between animals while operant
behavioural counts vary ~100%. Predicting the dispersion makes N follow the
actual experiment instead of a convention.

The honest question is not "does a model fit" but "does it beat simply knowing
the measure". Literature-derived data failed that test — strain and sex added
noise, because between-study variance swamped them. Curated phenotype databases
measure many strains under one protocol, so the same comparison is run here with
the measure's own median as the baseline to beat.

Evaluated two ways:
  unseen cell    — a strain/sex combination never seen for that measure
  unseen study   — an entire project/study held out, the harder generalisation

Run:  python train_variability_model.py
Out:  ml_models/variability_model.pkl + variability_meta.json (only if it wins)
"""
import json
import os
import numpy as np
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.metrics import mean_absolute_error

MPD = os.path.join('data', 'mpd_variability.json')
RGD = os.path.join('data', 'rgd_variability.json')
OUT = 'ml_models'
CATS = ['species', 'measure', 'strain', 'sex', 'intervention', 'method']
MODEL_KW = dict(max_iter=400, learning_rate=0.06, max_depth=6, random_state=42)


def load():
    """One row shape for both sources, keyed on what the researcher will type."""
    rows = []
    for r in json.load(open(MPD)):
        rows.append({
            'species': 'mouse', 'measure': (r['descrip'] or '').strip().lower(),
            'strain': r['strain'] or 'unspecified', 'sex': r['sex'] or 'unspecified',
            'intervention': (r['intervention'] or '').strip().lower(),
            'method': (r['method'] or '').strip().lower(),
            'n': r['n'], 'mean': r['mean'], 'cv_pct': r['cv_pct'],
            'study': f"MPD:{r['project']}",
        })
    for r in json.load(open(RGD)):
        rows.append({
            'species': 'rat', 'measure': (r['descrip'] or '').strip().lower(),
            'strain': r['strain'] or 'unspecified', 'sex': r['sex'] or 'unspecified',
            'intervention': (r['intervention'] or '').strip().lower(),
            'method': (r['method'] or '').strip().lower(),
            'n': r['n'], 'mean': r['mean'], 'cv_pct': r['cv_pct'],
            'study': f"RGD:{r['study']}",
        })
    return rows


def build(rows, tr_idx):
    """Baseline (measure median) plus design features.

    The measure's median CV is computed from TRAINING rows only and used both as
    the baseline prediction and as the model's first feature — so the model is
    scored on what it adds to that knowledge, not on rediscovering it.
    """
    per_measure, all_cv = {}, []
    for i in tr_idx:
        key = (rows[i]['species'], rows[i]['measure'])
        per_measure.setdefault(key, []).append(rows[i]['cv_pct'])
        all_cv.append(rows[i]['cv_pct'])
    per_measure = {k: float(np.median(v)) for k, v in per_measure.items()}
    global_med = float(np.median(all_cv))
    log_global = np.log10(global_med)

    # sklearn caps native categorical features at 255 levels and strain alone has
    # ~2,400. High-cardinality features are target-encoded from TRAINING rows
    # only, so no test information leaks into the encoding.
    vocab, encoders = {}, {}
    for c in CATS:
        levels = {(r[c] or '') for r in rows}
        if len(levels) <= 200:
            vocab[c] = {v: j for j, v in enumerate(sorted(levels))}
        else:
            acc = {}
            for i in tr_idx:
                acc.setdefault(rows[i][c] or '', []).append(np.log10(rows[i]['cv_pct']))
            encoders[c] = {k: float(np.median(v)) for k, v in acc.items()}

    X = np.zeros((len(rows), 1 + len(CATS) + 2), dtype=float)
    base = np.zeros(len(rows), dtype=float)
    for i, r in enumerate(rows):
        b = per_measure.get((r['species'], r['measure']), global_med)
        base[i] = b
        X[i, 0] = np.log10(b)
        for j, c in enumerate(CATS, start=1):
            v = r[c] or ''
            X[i, j] = vocab[c][v] if c in vocab else encoders[c].get(v, log_global)
        X[i, len(CATS) + 1] = r['n'] or 0
        X[i, len(CATS) + 2] = np.log10(abs(r['mean']) + 1e-6) if r['mean'] else 0.0
    cat_mask = [False] + [c in vocab for c in CATS] + [False, False]
    return X, base, cat_mask, per_measure, global_med, (vocab, encoders)


def run(rows, y, tr, te, label):
    X, base, cat_mask, per_measure, global_med, enc = build(rows, tr)
    model = HistGradientBoostingRegressor(categorical_features=cat_mask, **MODEL_KW)
    model.fit(X[tr], y[tr])

    true = 10 ** y[te]
    preds = (('global median (naive)', np.full(len(te), global_med)),
             ('per-measure median (lookup table)', base[te]),
             ('model: table + design features', 10 ** model.predict(X[te])))
    print(f"\n-- {label} --   train {len(tr):,} / test {len(te):,}")
    print(f"{'method':<36}{'MAE (CV points)':>18}{'median AE':>12}")
    print('-' * 66)
    res = {}
    for name, p in preds:
        res[name] = float(mean_absolute_error(true, p))
        print(f"{name:<36}{res[name]:>18.2f}{float(np.median(np.abs(true - p))):>12.2f}")
    tbl, mdl = res['per-measure median (lookup table)'], res['model: table + design features']
    gain = (tbl - mdl) / tbl * 100
    print('-' * 66)
    print(f"model vs lookup table: {gain:+.1f}%")
    return res, gain


def main():
    rows = load()
    y = np.log10(np.array([r['cv_pct'] for r in rows]))
    by_species = {}
    for r in rows:
        by_species[r['species']] = by_species.get(r['species'], 0) + 1
    print(f"rows {len(rows):,}  {by_species}  "
          f"measures {len({(r['species'], r['measure']) for r in rows}):,}  "
          f"strains {len({r['strain'] for r in rows}):,}")

    idx = np.arange(len(rows))
    tr1, te1 = train_test_split(idx, test_size=0.2, random_state=42)
    res_cell, gain_cell = run(rows, y, tr1, te1, "unseen strain/sex cell")

    groups = np.array([r['study'] for r in rows])
    tr2, te2 = next(GroupShuffleSplit(1, test_size=0.2, random_state=42)
                    .split(idx, groups=groups))
    res_study, gain_study = run(rows, y, tr2, te2, "unseen study")

    if gain_cell <= 0:
        print("\nThe model does NOT beat the lookup table. Not saving it.")
        return

    os.makedirs(OUT, exist_ok=True)
    # Refit on everything for the shipped artefact. Deliberately not scored: any
    # test row is now a training row, so a printed metric would be leakage
    # dressed up as a result. The held-out numbers above are the real ones.
    X, _, cat_mask, per_measure, global_med, enc = build(rows, idx)
    model = HistGradientBoostingRegressor(categorical_features=cat_mask,
                                          **MODEL_KW).fit(X, y)
    joblib.dump({'model': model, 'per_measure': per_measure,
                 'global_median': global_med, 'encoders': enc,
                 'cats': CATS, 'cat_mask': cat_mask}, os.path.join(OUT, 'variability_model.pkl'))
    json.dump({
        'name': 'Outcome Variability Model (OVM)',
        'algorithm': 'Histogram-based Gradient Boosting Regression Tree '
                     '(scikit-learn HistGradientBoostingRegressor)',
        'task': 'regression', 'target': 'log10(CV%)',
        'sources': ['Mouse Phenome Database (Jackson Laboratory)',
                    'Rat Genome Database PhenoMiner (MCW)'],
        'n_rows': len(rows), 'rows_by_species': by_species,
        'n_measures': len({(r['species'], r['measure']) for r in rows}),
        'n_strains': len({r['strain'] for r in rows}),
        'features': ['measure median CV'] + CATS + ['n', 'log mean'],
        'test_mae_cell_held_out': res_cell['model: table + design features'],
        'baseline_mae_cell_held_out': res_cell['per-measure median (lookup table)'],
        'improvement_cell_pct': round(gain_cell, 1),
        'test_mae_study_held_out': res_study['model: table + design features'],
        'baseline_mae_study_held_out': res_study['per-measure median (lookup table)'],
        'improvement_study_pct': round(gain_study, 1),
        'limitation': 'Adds nothing for a measure absent from both databases; '
                      'callers must fall back and say so.',
    }, open(os.path.join(OUT, 'variability_meta.json'), 'w'), indent=2)
    print("\nsaved ml_models/variability_model.pkl")


if __name__ == '__main__':
    main()
