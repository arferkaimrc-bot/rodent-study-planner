# -*- coding: utf-8 -*-
"""Harvest outcome variability from the Mouse Phenome Database.

Literature mining gave 568 usable rows and found strain to be noise — expected,
because every paper is a different lab, protocol and cohort, so strain effects
are buried under between-study variance. MPD measures many inbred strains under
one protocol per project, which isolates the strain effect, and it publishes the
coefficient of variation directly alongside mean, SD, SEM and n. That removes
every failure mode of text extraction: no SD/SEM ambiguity, no attribution
guesswork, no negation traps.

Each project contributes its own measures; measureinfo supplies the descriptive
context (what was measured, at what age, under what intervention) that the
sample-size model needs as features.

Run:  python build_mpd_variability.py [max_projects]
Out:  data/mpd_variability.json
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = 'https://phenome.jax.org/api'
UA = {'User-Agent': 'rodent-study-planner/1.0 (research; variability dataset)'}
OUT = os.path.join('data', 'mpd_variability.json')
PAUSE = 0.8

MIN_MICE = 3          # a CV from one or two animals is not an estimate
MAX_CV = 2.0          # 200%; beyond this the measure is not usefully continuous


def get(path, timeout=90):
    req = urllib.request.Request(BASE + path, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def measure_context(projsym):
    """measnum -> what was measured, and under what conditions."""
    try:
        info = get(f'/pheno/measureinfo/{projsym}')
    except Exception:
        return {}
    out = {}
    for m in info.get('measures_info', []) or []:
        mn = m.get('measnum')
        if mn is None:
            continue
        out[mn] = {
            'descrip': m.get('descrip') or '',
            'units': m.get('units') or '',
            'age': m.get('ageweeks') or '',
            'intervention': m.get('intervention') or '',
            'method': m.get('method') or '',
            'panel': m.get('paneldesc') or '',
        }
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10 ** 6
    os.makedirs('data', exist_ok=True)

    projects = get('/projects').get('projects', [])
    syms = [p['projsym'] for p in projects if p.get('projsym')][:limit]
    print(f"projects: {len(syms)}")

    rows, ok, missing, failed = [], 0, 0, 0
    for i, sym in enumerate(syms, 1):
        time.sleep(PAUSE)
        try:
            data = get(f'/pheno/strainmeans/{sym}')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                missing += 1
            else:
                failed += 1
            continue
        except Exception:
            failed += 1
            continue

        means = data.get('strainmeans', []) or []
        if not means:
            missing += 1
            continue
        time.sleep(PAUSE)
        ctx = measure_context(sym)

        kept = 0
        for r in means:
            cv, n = r.get('cv'), r.get('nmice')
            if cv is None or n is None or n < MIN_MICE:
                continue
            if not (0 < cv <= MAX_CV):
                continue
            c = ctx.get(r.get('measnum'), {})
            if not c.get('descrip'):
                continue                      # unlabelled measure is unusable
            rows.append({
                'source': 'MPD', 'project': sym, 'measnum': r.get('measnum'),
                'descrip': c['descrip'], 'units': c['units'],
                'age': c['age'], 'intervention': c['intervention'],
                'method': c['method'], 'panel': c['panel'],
                'strain': r.get('strain'), 'sex': r.get('sex'),
                'mean': r.get('mean'), 'sd': r.get('sd'),
                'n': n, 'cv_pct': round(cv * 100.0, 2),
            })
            kept += 1
        ok += 1
        if i % 25 == 0 or kept > 2000:
            print(f"  [{i:3d}/{len(syms)}] {sym:<16} +{kept:<6} total={len(rows):,}",
                  flush=True)

    json.dump(rows, open(OUT, 'w'))
    print(f"\nprojects with data {ok} · no public means {missing} · errors {failed}")
    print(f"rows: {len(rows):,}   distinct measures: "
          f"{len({r['measnum'] for r in rows}):,}   strains: "
          f"{len({r['strain'] for r in rows}):,}")
    print("wrote:", OUT)


if __name__ == '__main__':
    main()
