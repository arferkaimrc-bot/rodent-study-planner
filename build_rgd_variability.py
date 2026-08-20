# -*- coding: utf-8 -*-
"""Harvest rat outcome variability from RGD PhenoMiner.

MPD covers mice only; this is the rat half. RGD serves curated quantitative
phenotype records with mean, SD, SEM, units, strain, sex, age and — unlike MPD —
an explicit experimental condition, including drug interventions such as
"acetaminophen (500 mg/kg) for 28 days". Coefficient of variation is derived
from SD/mean, falling back to SEM*sqrt(n) when only SEM is curated.

Terms are looked up by name rather than hard-coded, so the measure list below
stays readable and the accession IDs cannot silently drift.

Run:  python build_rgd_variability.py
Out:  data/rgd_variability.json
"""
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://rest.rgd.mcw.edu/rgdws'
UA = {'User-Agent': 'rodent-study-planner/1.0 (research; variability dataset)'}
OUT = os.path.join('data', 'rgd_variability.json')
RAT = 3
PAUSE = 1.0
MIN_ANIMALS = 3

# The measures a preclinical rat study actually reports. Names are resolved to
# CMO accession IDs at run time.
MEASURE_NAMES = [
    'body weight', 'blood glucose level',
    'serum alanine aminotransferase activity', 'serum aspartate aminotransferase activity',
    'serum creatinine level', 'blood urea nitrogen level',
    'serum total cholesterol level', 'serum triglyceride level',
    'systolic blood pressure', 'diastolic blood pressure', 'heart rate',
    'liver wet weight', 'kidney wet weight', 'heart wet weight',
    'spleen wet weight', 'brain wet weight', 'lung wet weight',
    'blood hemoglobin level', 'blood platelet count',
    'blood leukocyte count', 'blood erythrocyte count',
    'serum albumin level', 'serum total protein level',
    'serum insulin level', 'plasma corticosterone level',
]


def get(path, timeout=180):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def resolve(name):
    try:
        t = get('/ontology/term/ont/' + urllib.parse.quote(name) + '/CMO')
    except Exception:
        return None
    acc = t.get('accId')
    return (acc, t.get('term')) if acc else None


def harvest(acc, label):
    try:
        data = get(f'/phenotype/phenominer/chart/{RAT}/{acc}')
    except urllib.error.HTTPError as e:
        print(f"  {label[:40]:<42} HTTP {e.code}")
        return []
    except Exception as e:
        print(f"  {label[:40]:<42} {type(e).__name__}")
        return []

    strains = {k: v.get('term') for k, v in (data.get('termResolver') or {}).items()}
    rows = []
    for r in data.get('records', []) or []:
        s = r.get('sample') or {}
        n = s.get('numberOfAnimals')
        if not n or n < MIN_ANIMALS:
            continue
        try:
            mean = float(r.get('measurementValue'))
        except (TypeError, ValueError):
            continue
        if mean == 0:
            continue
        sd = r.get('measurementSD')
        try:
            sd = float(sd)
        except (TypeError, ValueError):
            sd = None
        if sd is None:                       # curated as SEM only
            try:
                sd = float(r.get('measurementSem')) * math.sqrt(n)
            except (TypeError, ValueError):
                continue
        cv = abs(sd / mean) * 100.0
        if not (0.3 <= cv <= 200):
            continue
        lo, hi = s.get('ageDaysFromLowBound'), s.get('ageDaysFromHighBound')
        rows.append({
            'source': 'RGD', 'species': 'rat',
            'measure_acc': acc, 'descrip': label,
            'units': r.get('measurementUnits') or '',
            'strain': strains.get(s.get('strainAccId')) or s.get('strainAccId') or 'unspecified',
            'sex': (s.get('sex') or 'unspecified'),
            'age_days': (lo + hi) / 2 if (lo is not None and hi is not None) else None,
            'life_stage': s.get('lifeStage') or '',
            'intervention': r.get('conditionDescription') or '',
            'method': (r.get('measurementMethod') or {}).get('term', '') if isinstance(
                r.get('measurementMethod'), dict) else '',
            'study': r.get('studyName') or '',
            'mean': mean, 'sd': sd, 'n': n, 'cv_pct': round(cv, 2),
        })
    print(f"  {label[:40]:<42} {len(rows):>6} rows")
    return rows


def main():
    os.makedirs('data', exist_ok=True)
    all_rows = []
    for name in MEASURE_NAMES:
        time.sleep(PAUSE)
        hit = resolve(name)
        if not hit:
            print(f"  {name[:40]:<42} term not found")
            continue
        acc, term = hit
        time.sleep(PAUSE)
        all_rows.extend(harvest(acc, term))

    json.dump(all_rows, open(OUT, 'w'))
    print(f"\nrows {len(all_rows):,}  measures "
          f"{len({r['measure_acc'] for r in all_rows})}  strains "
          f"{len({r['strain'] for r in all_rows})}")
    print("wrote:", OUT)


if __name__ == '__main__':
    main()
