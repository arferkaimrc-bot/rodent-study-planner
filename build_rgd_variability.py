# -*- coding: utf-8 -*-
"""Harvest rat outcome variability from RGD PhenoMiner.

MPD covers mice only; this is the rat half. RGD serves curated quantitative
phenotype records with mean, SD, SEM, units, strain, sex, age and — unlike MPD —
an explicit experimental condition, including drug interventions such as
"acetaminophen (500 mg/kg) for 28 days". Coefficient of variation is derived
from SD/mean, falling back to SEM*sqrt(n) when only SEM is curated.

Every Clinical Measurement Ontology term is walked rather than a hand-picked
list: a curated list silently caps coverage at whatever the author thought of,
and a rat researcher whose endpoint was not on it would get no prediction. About
a quarter of CMO terms carry data, so most requests return quickly and empty.

Progress is written incrementally, so an interrupted run is not lost.

Run:  python build_rgd_variability.py [max_terms]
Out:  data/rgd_variability.json
"""
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = 'https://rest.rgd.mcw.edu/rgdws'
OBO = ('https://download.rgd.mcw.edu/ontology/clinical_measurement/'
       'clinical_measurement.obo')
UA = {'User-Agent': 'rodent-study-planner/1.0 (research; variability dataset)'}
OUT = os.path.join('data', 'rgd_variability.json')
CACHE_OBO = os.path.join('data', 'clinical_measurement.obo')
RAT = 3
PAUSE = 0.8
MIN_ANIMALS = 3
SAVE_EVERY = 100


def fetch(url, timeout=120, headers=UA):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def cmo_terms():
    """Every live Clinical Measurement Ontology term, id and name."""
    if not os.path.exists(CACHE_OBO):
        os.makedirs('data', exist_ok=True)
        open(CACHE_OBO, 'wb').write(fetch(OBO, timeout=180))
    txt = open(CACHE_OBO, encoding='utf-8', errors='replace').read()
    terms = re.findall(r'^\[Term\]\nid: (CMO:\d+)\nname: (.+?)$', txt, re.M)
    obsolete = set(re.findall(r'id: (CMO:\d+)\n(?:.*\n)*?is_obsolete: true', txt))
    return [(i, n) for i, n in terms if i not in obsolete]


def harvest(acc, label):
    """Usable CV rows for one measurement term."""
    try:
        raw = fetch(f'{BASE}/phenotype/phenominer/chart/{RAT}/{acc}')
        data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError):
        return []
    except Exception:
        return []

    records = data.get('records') or []
    if not records:
        return []
    strains = {k: v.get('term') for k, v in (data.get('termResolver') or {}).items()}

    rows = []
    for r in records:
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
        try:
            sd = float(r.get('measurementSD'))
        except (TypeError, ValueError):
            sd = None
        if sd is None:                        # curated as SEM only
            try:
                sd = float(r.get('measurementSem')) * math.sqrt(n)
            except (TypeError, ValueError):
                continue
        cv = abs(sd / mean) * 100.0
        if not (0.3 <= cv <= 200):
            continue
        lo, hi = s.get('ageDaysFromLowBound'), s.get('ageDaysFromHighBound')
        method = r.get('measurementMethod')
        rows.append({
            'source': 'RGD', 'species': 'rat',
            'measure_acc': acc, 'descrip': label,
            'units': r.get('measurementUnits') or '',
            'strain': strains.get(s.get('strainAccId')) or s.get('strainAccId') or 'unspecified',
            'sex': s.get('sex') or 'unspecified',
            'age_days': (lo + hi) / 2 if (lo is not None and hi is not None) else None,
            'life_stage': s.get('lifeStage') or '',
            'intervention': r.get('conditionDescription') or '',
            'method': method.get('term', '') if isinstance(method, dict) else '',
            'study': r.get('studyName') or '',
            'mean': mean, 'sd': sd, 'n': n, 'cv_pct': round(cv, 2),
        })
    return rows


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10 ** 6
    os.makedirs('data', exist_ok=True)
    terms = cmo_terms()[:limit]
    print(f"CMO terms to walk: {len(terms):,}", flush=True)

    all_rows, hits = [], 0
    for i, (acc, name) in enumerate(terms, 1):
        time.sleep(PAUSE)
        rows = harvest(acc, name)
        if rows:
            hits += 1
            all_rows.extend(rows)
            print(f"  [{i:4d}/{len(terms)}] {acc} {name[:44]:<46} +{len(rows):<5} "
                  f"total={len(all_rows):,}", flush=True)
        if i % SAVE_EVERY == 0:
            json.dump(all_rows, open(OUT, 'w'))
            print(f"  … {i}/{len(terms)} walked · {hits} with data · "
                  f"{len(all_rows):,} rows saved", flush=True)

    json.dump(all_rows, open(OUT, 'w'))
    print(f"\nterms with data {hits}/{len(terms)}")
    print(f"rows {len(all_rows):,}  measures {len({r['measure_acc'] for r in all_rows})}  "
          f"strains {len({r['strain'] for r in all_rows})}")
    print("wrote:", OUT)


if __name__ == '__main__':
    main()
