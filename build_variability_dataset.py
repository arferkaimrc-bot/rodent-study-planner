# -*- coding: utf-8 -*-
"""Mine rodent outcome-measure variability (CV%) from the open-access literature.

Sample size is driven by how much the measured outcome varies between animals,
and that dispersion is the one number researchers cannot guess. A fixed
assumption (Cohen's d = 0.8) gives the same answer whatever is being measured,
which is wrong in both directions: body weight barely varies between littermates
while tumour volume varies enormously. This builds the training set for
predicting the dispersion instead — one row per reported group, carrying the
measure, species, strain, sex, and the coefficient of variation.

Two things make or break the data, and both are handled explicitly:

  SD vs SEM — SEM = SD/sqrt(n), so reading a reported SEM as an SD shrinks the
  dispersion by sqrt(n) and would silently recommend an underpowered study.
  Papers declare which they report in a statistics sentence; that declaration is
  read per paper and the value converted.

  Attribution — a bare "24.1 +/- 1.8" says nothing about what was measured. A
  match is kept only when the surrounding text names the measure AND the value
  is physiologically plausible for that measure and species, which rejects
  almost all spurious numbers (husbandry conditions, stereotactic coordinates,
  percentages, p-values).

CV% is scale-invariant, so units matter only for identifying the measure and
range-checking it — never for the stored value.

Run:  python build_variability_dataset.py [n_papers_per_measure]
Out:  data/variability_outcomes.json
"""
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

SEARCH = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
FULLTEXT = 'https://www.ebi.ac.uk/europepmc/webservices/rest/{}/fullTextXML'
UA = {'User-Agent': 'rodent-study-planner/1.0 (variability dataset; research use)'}
OUT = os.path.join('data', 'variability_outcomes.json')
PAUSE = 1.2                      # be a polite API citizen

# ── the outcome measures ───────────────────────────────────────────────────
# units:   unit token -> factor into the canonical unit (for range checks only)
# context: must appear near the number for the match to be attributed here
# range:   plausible canonical-unit values, per species ('any' = both)
MEASURES = {
    'body_weight': {
        'label': 'Body weight',
        'canonical': 'g',
        'units': {'g': 1.0, 'kg': 1000.0},
        'context': r'body\s*weight|bodyweight|\bbw\b|body\s*mass',
        'range': {'mouse': (12.0, 60.0), 'rat': (120.0, 700.0)},
        'query': 'TITLE:"body weight"',
    },
    'tumor_volume': {
        'label': 'Tumour volume',
        'canonical': 'mm3',
        'units': {'mm3': 1.0, 'mm³': 1.0, 'cm3': 1000.0, 'cm³': 1000.0},
        'context': r'tumou?r\s*(?:volume|size|burden)',
        'range': {'any': (5.0, 8000.0)},
        'query': 'TITLE:"tumor volume" OR TITLE:"tumour volume" OR ABSTRACT:"tumor volume"',
    },
    # Tumour volume is nearly always plotted as a growth curve rather than
    # tabulated, so endpoint tumour WEIGHT carries the same information and is
    # reported as a number far more often.
    'tumor_weight': {
        'label': 'Tumour weight (endpoint)',
        'canonical': 'g',
        'units': {'g': 1.0, 'mg': 0.001},
        'context': r'tumou?r\s*weight|weight\s+of\s+(?:the\s+)?tumou?rs?',
        'range': {'any': (0.005, 15.0)},
        'query': 'ABSTRACT:"tumor weight" OR ABSTRACT:"tumour weight" OR TITLE:"tumor weight"',
    },
    'alt': {
        'label': 'ALT (alanine aminotransferase)',
        'canonical': 'U/L',
        'units': {'u/l': 1.0, 'iu/l': 1.0, 'u/liter': 1.0},
        'context': r'\bALT\b|alanine\s+amino\s?transferase|\bGPT\b',
        'range': {'any': (3.0, 3000.0)},
        'query': 'ABSTRACT:"alanine aminotransferase" OR ABSTRACT:"ALT"',
    },
    'ast': {
        'label': 'AST (aspartate aminotransferase)',
        'canonical': 'U/L',
        'units': {'u/l': 1.0, 'iu/l': 1.0, 'u/liter': 1.0},
        'context': r'\bAST\b|aspartate\s+amino\s?transferase|\bGOT\b',
        'range': {'any': (3.0, 3000.0)},
        'query': 'ABSTRACT:"aspartate aminotransferase" OR ABSTRACT:"AST"',
    },
    'glucose': {
        'label': 'Blood glucose',
        'canonical': 'mg/dL',
        'units': {'mg/dl': 1.0, 'mmol/l': 18.0},   # glucose molar conversion
        'context': r'(?:blood|plasma|serum|fasting)\s+glucose|\bglucose\s+level',
        'range': {'any': (30.0, 700.0)},
        'query': 'ABSTRACT:"blood glucose" OR TITLE:"blood glucose"',
    },
}

STRAINS = [
    ('C57BL/6', r'c57bl[/\s-]?6|c57black|\bb6\b'),
    ('BALB/c', r'balb[/\s-]?c'),
    ('Swiss/CD-1/ICR', r'\bcd-?1\b|swiss albino|\bswiss\b|\bicr\b'),
    ('Nude/SCID/NSG', r'\bnude\b|\bscid\b|\bnsg\b|athymic'),
    ('Wistar', r'\bwistar\b'),
    ('Sprague-Dawley', r'sprague[\s-]?dawley|\bsd rats?\b'),
    ('Long-Evans', r'long[\s-]?evans'),
]

N_NEAR = re.compile(r'\bn\s*=\s*(\d{1,3})\b', re.I)
SEM_DECL = re.compile(
    r'(?:mean|expressed|presented|shown|given|reported)[^.]{0,80}?'
    r'(?:±|\+/-|\+-|as)\s*(?:the\s*)?(s\.?e\.?m\.?|standard error)', re.I)
SD_DECL = re.compile(
    r'(?:mean|expressed|presented|shown|given|reported)[^.]{0,80}?'
    r'(?:±|\+/-|\+-|as)\s*(?:the\s*)?(s\.?d\.?|standard deviation)', re.I)


def _num_pattern(units):
    """'24.1 +/- 1.8 <unit>' for one measure's unit vocabulary."""
    alts = '|'.join(sorted((re.escape(u) for u in units), key=len, reverse=True))
    return re.compile(
        r'(\d{1,5}(?:\.\d{1,3})?)\s*(?:±|\+/-|\+-)\s*(\d{1,5}(?:\.\d{1,3})?)\s*'
        r'(' + alts + r')(?![a-z0-9])', re.I)


for _k, _m in MEASURES.items():
    _m['num_re'] = _num_pattern(_m['units'])
    _m['ctx_re'] = re.compile(_m['context'], re.I)


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def search_papers(measure_query, n_papers):
    query = (f'(mouse OR mice OR rat OR rats) AND ({measure_query}) '
             'AND (OPEN_ACCESS:Y) AND (HAS_FT:Y) NOT (PUB_TYPE:"Review")')
    out, cursor = [], '*'
    while len(out) < n_papers:
        params = {'query': query, 'format': 'json', 'pageSize': 25,
                  'resultType': 'core', 'cursorMark': cursor}
        data = json.loads(fetch(SEARCH + '?' + urllib.parse.urlencode(params)))
        batch = data.get('resultList', {}).get('result', []) or []
        if not batch:
            break
        for rec in batch:
            if rec.get('pmcid'):
                out.append({'pmcid': rec['pmcid'], 'year': rec.get('pubYear', ''),
                            'title': (rec.get('title') or '').strip()})
        nxt = data.get('nextCursorMark')
        if not nxt or nxt == cursor:
            break
        cursor = nxt
        time.sleep(PAUSE)
    return out[:n_papers]


def plain_text(xml):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', xml))


def dispersion_kind(text):
    """Which dispersion the paper says it reports. None when it never says."""
    sem, sd = SEM_DECL.search(text), SD_DECL.search(text)
    if sem and sd:
        return 'sem' if sem.start() < sd.start() else 'sd'
    if sem:
        return 'sem'
    if sd:
        return 'sd'
    return None


def species_of(text):
    head = text[:6000].lower()
    mouse = len(re.findall(r'\bmice\b|\bmouse\b', head))
    rat = len(re.findall(r'\brats?\b', head))
    if mouse == rat == 0:
        return None
    return 'mouse' if mouse >= rat else 'rat'


def strain_of(text):
    head = text[:12000]
    for name, pat in STRAINS:
        if re.search(pat, head, re.I):
            return name
    return 'unspecified'


def sex_of(text):
    head = text[:12000].lower()
    m, f = 'male' in head, 'female' in head
    if m and f:
        return 'both'
    return 'male' if m else ('female' if f else 'unspecified')


def paper_group_size(text):
    """The per-group n the paper declares, for converting a reported SEM.

    Takes the most frequently stated small n — the group size repeated across
    legends — rather than a one-off total or a stray count.
    """
    vals = [int(v) for v in N_NEAR.findall(text)]
    vals = [v for v in vals if 2 <= v <= 40]
    return max(set(vals), key=vals.count) if vals else None


def extract(paper, text, key, spec, species, strain, sex, kind, paper_n):
    rng = spec['range'].get(species) or spec['range'].get('any')
    if not rng:
        return []
    lo, hi = rng
    rows, seen = [], set()
    for m in spec['num_re'].finditer(text):
        mean, disp = float(m.group(1)), float(m.group(2))
        factor = spec['units'][m.group(3).lower()]
        mean_c, disp_c = mean * factor, disp * factor
        if not (lo <= mean_c <= hi):
            continue                          # not a plausible value
        window = text[max(0, m.start() - 220):m.end() + 120]
        if not spec['ctx_re'].search(window):
            continue                          # context does not name the measure
        if disp <= 0 or disp / mean > 0.9:
            continue                          # implausible spread
        n_hit = N_NEAR.search(window)
        n = int(n_hit.group(1)) if n_hit else paper_n
        if kind == 'sem':
            if not n or n < 2:
                continue                      # cannot convert SEM without n
            disp = disp * math.sqrt(n)        # SEM -> SD
        cv = disp / mean * 100.0              # scale-invariant
        if not (0.3 <= cv <= 120):
            continue
        dedupe = (round(mean, 2), round(cv, 1))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        rows.append({
            'measure': key, 'pmcid': paper['pmcid'], 'year': paper['year'],
            'species': species, 'strain': strain, 'sex': sex,
            'mean': round(mean, 3), 'unit': m.group(3),
            'cv_pct': round(cv, 2), 'n': n, 'reported_as': kind,
            'snippet': re.sub(r'\s+', ' ', window[-170:]).strip(),
        })
    return rows


def main():
    per = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    os.makedirs('data', exist_ok=True)
    all_rows, stats = [], {}

    for key, spec in MEASURES.items():
        print(f"\n=== {spec['label']} ===")
        try:
            papers = search_papers(spec['query'], per)
        except Exception as e:
            print("  search failed:", e)
            continue
        got_rows, contributing = 0, set()
        for i, p in enumerate(papers, 1):
            time.sleep(PAUSE)
            try:
                text = plain_text(fetch(FULLTEXT.format(p['pmcid'])))
            except Exception:
                continue
            sp = species_of(text)
            kind = dispersion_kind(text)
            if sp is None or kind is None:
                continue
            rows = extract(p, text, key, spec, sp, strain_of(text), sex_of(text),
                           kind, paper_group_size(text))
            if rows:
                contributing.add(p['pmcid'])
                got_rows += len(rows)
                all_rows.extend(rows)
            if i % 10 == 0 or rows:
                print(f"  [{i:3d}/{len(papers)}] {p['pmcid']:<12} +{len(rows)}")
        stats[key] = (got_rows, len(contributing), len(papers))
        print(f"  -> {got_rows} rows from {len(contributing)}/{len(papers)} papers")

    json.dump(all_rows, open(OUT, 'w'), indent=1)
    print("\n" + "=" * 62)
    print(f"{'measure':<18}{'rows':>7}{'papers':>9}{'yield/paper':>13}")
    for k, (r, c, t) in stats.items():
        print(f"{k:<18}{r:>7}{c:>4}/{t:<4}{(r / t if t else 0):>13.2f}")
    print(f"{'TOTAL':<18}{len(all_rows):>7}")
    print("wrote:", OUT)


if __name__ == '__main__':
    main()
