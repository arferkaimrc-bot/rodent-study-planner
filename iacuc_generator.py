"""
IACUC Auto-Fill — turn a Rodent Study Planner analysis into a filled KAIMRC
Animal Ethics Application Form (.docx).

The scientific narrative (PARTS 2, 3, 4, 6, 8, 11) is synthesised here from the
platform's analysis output; the researcher only supplies the administrative
details (team, funding, housing) via the front-end modal.

Public API:
    generate_iacuc_docx(payload) -> io.BytesIO   # a ready-to-download .docx

`payload` (JSON from the browser):
    {
      "study":    {"study_title", "pi_name", "institution"},
      "groups":   [ <original form groups: group_name, drug_name, species,
                     strain, sex, age, weight, num_mice, dose, route,
                     experiment_type, target_organ, toxicity_endpoints[] ...> ],
      "analysis": [ <the /predict response array; each item has `summary`,
                     `rationale`, `reference_papers`, `drug` ...> ],
      "admin":    {"funding_source", "housing_type" ("standard"|"absl"),
                   "team": [ {name, role, qualifications, institution,
                              email, mobile} ] }
    }

Nothing here is persisted — the form is generated in-memory and streamed back,
honouring the project's rule never to store study data.
"""
import io
from pathlib import Path

from docxtpl import DocxTemplate

TEMPLATE_PATH = Path(__file__).resolve().parent / "iacuc_assets" / "iacuc_template.docx"

# ── small helpers ─────────────────────────────────────────────────────────

def _s(v, default=""):
    """Safe string."""
    if v is None:
        return default
    v = str(v).strip()
    return v if v else default


def _join_unique(items):
    seen, out = set(), []
    for it in items:
        it = _s(it)
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _list_sentence(items, joiner="and"):
    items = _join_unique(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f", {joiner} " + items[-1]


def _bullets(items):
    """Render a list as newline-separated bullet lines (Word keeps the \\n)."""
    items = [i for i in (_s(x) for x in items) if i]
    return "\n".join(f"• {i}" for i in items)


def _pair(groups, analysis):
    """Zip form groups with their analysis result by index; skip errored ones."""
    out = []
    analysis = analysis or []
    for i, g in enumerate(groups or []):
        a = analysis[i] if i < len(analysis) else {}
        if isinstance(a, dict) and a.get("error"):
            a = {}
        out.append((g or {}, a or {}, (a.get("summary") if isinstance(a, dict) else {}) or {}))
    return out


def _is_control(g):
    dn = _s(g.get("drug_name")).lower()
    gn = _s(g.get("group_name")).lower()
    return (not dn) or dn in ("control", "vehicle", "saline", "none") or "control" in gn


# ── narrative builders (each returns one answer-box string) ────────────────

def _study_purpose(rows, study):
    drugs = _join_unique(_s(g.get("drug_name")) for g, _, _ in rows if not _is_control(g))
    paradigms = _join_unique(_s(g.get("experiment_type")) for g, _, _ in rows)
    species = _join_unique(_s(s.get("species") or g.get("species")) for g, _, s in rows)
    title = _s(study.get("study_title"), "this study")
    parts = [f"The purpose of {title} is to investigate the biological effects and "
             f"tolerability of {_list_sentence(drugs) or 'the test article(s)'} "
             f"in {_list_sentence(species, 'and') or 'laboratory rodents'}."]
    if paradigms:
        parts.append(f"The work falls within {_list_sentence(paradigms)} research.")
    parts.append("Live animals are required because the whole-organism response — "
                 "absorption, distribution, metabolism, systemic toxicity and organ-level "
                 "effects — cannot be reproduced in cell-based or in-vitro systems.")
    return " ".join(parts)


def _what_done(rows):
    lines = []
    for g, _, s in rows:
        gname = _s(g.get("group_name"), "Group")
        n = _s(s.get("planned_animals") or g.get("num_mice"), "n")
        sp = _s(s.get("species") or g.get("species"), "rodents")
        if _is_control(g):
            lines.append(f"{gname}: {n} {sp.lower()} receive the vehicle/control by "
                         f"{_s(g.get('route'),'the same route')} and are handled identically "
                         f"to the treatment groups.")
        else:
            drug = _s(g.get("drug_name"), "the test article")
            dose = _s(g.get("dose"))
            route = _s(g.get("route"), "the assigned route")
            dose_txt = f" at {dose} mg/kg" if dose else ""
            lines.append(f"{gname}: {n} {sp.lower()} receive {drug}{dose_txt} via {route}, "
                         f"followed by clinical observation and scheduled sample collection.")
    lines.append("Animals are weighed and observed regularly; biological samples are "
                 "collected at defined time-points, after which animals are humanely euthanised.")
    return "\n".join(lines)


def _expected_outcomes(rows):
    organs = _join_unique(_s(g.get("target_organ")) for g, _, _ in rows
                          if _s(g.get("target_organ")).lower() not in ("", "general", "none"))
    eps = _join_unique(e for g, _, _ in rows for e in (g.get("toxicity_endpoints") or []))
    out = ["The study is expected to characterise the dose–response and safety profile "
           "of the test article(s) in the chosen model."]
    if organs:
        out.append(f"Particular attention is paid to effects on the {_list_sentence(organs)}.")
    if eps:
        out.append(f"Assessed endpoints include {_list_sentence(eps)}.")
    return " ".join(out)


def _study_benefit(rows):
    paradigms = _join_unique(_s(g.get("experiment_type")) for g, _, _ in rows)
    txt = ("The findings will improve understanding of the efficacy and safety of the "
           "test article(s), informing safer dose selection and reducing risk in "
           "subsequent research and, ultimately, clinical development.")
    if paradigms:
        txt += f" This advances {_list_sentence(paradigms)} research and may benefit " \
               "both human and animal health."
    return txt


def _strain_health_issues(rows):
    strains = _join_unique(_s(s.get("strain") or g.get("strain")) for g, _, s in rows)
    if not strains:
        return ("No strain-specific health or husbandry issues are anticipated. Standard "
                "outbred/inbred laboratory rodents will be used and monitored per facility SOPs.")
    return (f"Animals of the following strain(s) will be used: {_list_sentence(strains)}. "
            "No unusual strain-specific health or husbandry concerns are anticipated; animals "
            "will be sourced from accredited vendors and monitored per facility SOPs.")


def _scientific_justification(rows):
    species = _join_unique(_s(s.get("species") or g.get("species")) for g, _, s in rows)
    return ("Live animals of the species " + (_list_sentence(species) or "listed above") +
            " are scientifically justified because the study endpoints depend on an intact, "
            "physiologically integrated mammalian system — systemic pharmacokinetics, "
            "multi-organ toxicity and whole-body clinical response — that cannot be modelled "
            "in vitro. The rodent is the lowest phylogenetic species in which these responses "
            "are predictive, and is the established model for this class of study.")


def _literature_background(rows):
    papers = []
    for _, a, _ in rows:
        for p in (a.get("reference_papers") or [])[:3]:
            t = _s(p.get("title") if isinstance(p, dict) else p)
            yr = _s(p.get("year")) if isinstance(p, dict) else ""
            if t:
                papers.append(f"{t}" + (f" ({yr})" if yr else ""))
    overviews = _join_unique(_s(s.get("drug_overview")) for _, _, s in rows if _s(s.get("drug_overview")))
    out = []
    if overviews:
        out.append(overviews[0])
    out.append("The proposed work builds on existing pharmacological and toxicological "
               "literature for the test article(s) and study paradigm.")
    if papers:
        out.append("Representative references identified during study design include:")
        out.append(_bullets(_join_unique(papers)[:6]))
    return "\n".join(out)


def _research_aims(rows):
    aims = ["Determine the biological response and tolerability of the test article(s) "
            "at the selected dose level(s) in the chosen rodent model."]
    organs = _join_unique(_s(g.get("target_organ")) for g, _, _ in rows
                          if _s(g.get("target_organ")).lower() not in ("", "general", "none"))
    if organs:
        aims.append(f"Assess potential target-organ effects on the {_list_sentence(organs)}.")
    aims.append("Compare treatment groups against concurrent controls to establish a "
                "dose–response relationship.")
    return _bullets(aims)


def _procedures_overview(rows):
    lines = ["Overview of procedures and manipulations:"]
    for g, _, s in rows:
        if _is_control(g):
            continue
        drug = _s(g.get("drug_name"), "test article")
        route = _s(g.get("route"), "assigned route")
        dose = _s(g.get("dose"))
        dose_txt = f" ({dose} mg/kg)" if dose else ""
        lines.append(f"• Administration of {drug}{dose_txt} by {route}.")
    samples = _join_unique(x for _, _, s in rows for x in (s.get("recommended_samples") or []))
    lines.append("• Body-weight measurement and structured clinical observation.")
    if samples:
        lines.append(f"• Biological sample collection: {_list_sentence(samples)}.")
    lines.append("• Humane euthanasia and tissue collection at the study endpoint.")
    # a representative timeline, if available
    tl = None
    for _, _, s in rows:
        if s.get("timeline"):
            tl = s["timeline"]
            break
    if tl:
        lines.append("")
        lines.append("Representative timeline:")
        for step in tl[:8]:
            if isinstance(step, dict):
                day = _s(step.get("day"))
                act = _s(step.get("activity") or step.get("phase"))
                lines.append(f"  Day {day}: {act}" if day else f"  {act}")
    return "\n".join(lines)


def _experimental_endpoints(rows):
    eps = _join_unique(e for g, _, _ in rows for e in (g.get("toxicity_endpoints") or []))
    samples = _join_unique(x for _, _, s in rows for x in (s.get("recommended_samples") or []))
    out = ["Experimental endpoints (scientific data collection points):"]
    if eps:
        out.append(f"• Assessed measures: {_list_sentence(eps)}.")
    if samples:
        out.append(f"• Terminal samples/tissues: {_list_sentence(samples)}.")
    out.append("• Study endpoint is reached at the scheduled terminal time-point, after "
               "which planned analyses are performed.")
    return "\n".join(out)


def _welfare_of(rows):
    """Return the first available welfare dict among treatment groups."""
    for g, a, s in rows:
        w = s.get("welfare")
        if w:
            return w
    return None


def _humane_endpoints(rows):
    w = _welfare_of(rows)
    if w and w.get("humane_endpoints"):
        return _bullets(w["humane_endpoints"])
    return _bullets([
        "Body weight loss ≥ 20% from baseline (or ≥ 15% with other clinical signs)",
        "Body condition score ≤ 2/5 (emaciation)",
        "Persistent hunched posture, lack of grooming, or hypothermia",
        "Inability to reach food or water for > 24 h",
    ])


def _observation_frequency(rows):
    w = _welfare_of(rows)
    if w and w.get("monitoring", {}).get("frequency"):
        m = w["monitoring"]
        extra = _s(m.get("body_condition_scoring"))
        return _s(m["frequency"]) + (f" {extra}" if extra else "")
    return ("At least once daily, with additional checks after each dosing event and "
            "around the expected peak drug effect. Record body weight and body condition "
            "score (1–5) at each observation.")


def _endpoint_response(rows):
    w = _welfare_of(rows)
    if w and w.get("response_when_endpoint_reached"):
        return _s(w["response_when_endpoint_reached"])
    return ("The affected animal will be removed from study and humanely euthanised using "
            "the approved method immediately; observations are recorded and the attending "
            "veterinarian is notified.")


def _euthanasia_method(rows):
    return ("Euthanasia will be performed in accordance with the AVMA Guidelines and "
            "institutional SOPs — CO₂ inhalation from a compressed source at an approved "
            "flow rate, followed by a secondary physical method (e.g. cervical dislocation "
            "or exsanguination) to confirm death.")


def _pain_monitoring_frequency(rows):
    w = _welfare_of(rows)
    if w and w.get("monitoring", {}).get("frequency"):
        return _s(w["monitoring"]["frequency"])
    return ("Once daily during the study, increasing to twice daily around dosing and the "
            "expected peak effect; more frequently if any clinical signs are observed.")


def _discomfort_measures(rows):
    w = _welfare_of(rows)
    base = ("Measures to minimise discomfort, distress or pain: gentle handling by trained "
            "personnel, use of the least-stressful effective route and volume, provision of "
            "soft/moist food and supplemental warmth as needed, and prompt clinical intervention.")
    if w and w.get("monitoring", {}).get("analgesia_guidance"):
        base += " " + _s(w["monitoring"]["analgesia_guidance"])
    return base


# ── structured tables ─────────────────────────────────────────────────────

def _team(admin, study):
    team = []
    pi = _s(study.get("pi_name"))
    inst = _s(study.get("institution"), "KAIMRC")
    if pi:
        team.append({"name": pi, "role": "Principal Investigator", "qualifications": "",
                     "institution": inst, "email": "", "mobile": ""})
    for m in (admin.get("team") or []):
        if not isinstance(m, dict):
            continue
        if not _s(m.get("name")):
            continue
        team.append({
            "name": _s(m.get("name")),
            "role": _s(m.get("role")),
            "qualifications": _s(m.get("qualifications")),
            "institution": _s(m.get("institution"), inst),
            "email": _s(m.get("email")),
            "mobile": _s(m.get("mobile")),
        })
    return team[:6]


def _animals(rows):
    animals = []
    for g, _, s in rows:
        sp = _s(s.get("species") or g.get("species"), "Mouse")
        strain = _s(s.get("strain") or g.get("strain") or s.get("recommended_strain"))
        sex = _s(g.get("sex"), "—")
        age = _s(s.get("planned_age_weeks") or g.get("age"))
        age = f"{age} wk" if age and "wk" not in age.lower() and "week" not in age.lower() else (age or "—")
        total = _s(s.get("planned_animals") or g.get("num_mice"), "—")
        animals.append({"species": sp, "strain": strain or "—", "sex": sex,
                        "age": age, "total": total, "source": "Accredited vendor"})
    return animals[:6]


def _funding(admin):
    fund = _s(admin.get("funding_source"))
    housing = _s(admin.get("housing_type")).lower()
    note = fund
    if housing == "absl":
        note = (note + " | " if note else "") + "Housing: ABSL (biocontainment)"
    elif housing == "standard":
        note = (note + " | " if note else "") + "Housing: standard"
    return note


# ── main entry point ──────────────────────────────────────────────────────

def build_context(payload):
    study = payload.get("study") or {}
    admin = payload.get("admin") or {}
    rows = _pair(payload.get("groups") or [], payload.get("analysis") or [])
    return {
        "study_purpose": _study_purpose(rows, study),
        "what_done": _what_done(rows),
        "expected_outcomes": _expected_outcomes(rows),
        "study_benefit": _study_benefit(rows),
        "strain_health_issues": _strain_health_issues(rows),
        "scientific_justification": _scientific_justification(rows),
        "literature_background": _literature_background(rows),
        "research_aims": _research_aims(rows),
        "procedures_overview": _procedures_overview(rows),
        "experimental_endpoints": _experimental_endpoints(rows),
        "humane_endpoints": _humane_endpoints(rows),
        "observation_frequency": _observation_frequency(rows),
        "endpoint_response": _endpoint_response(rows),
        "euthanasia_method": _euthanasia_method(rows),
        "pain_monitoring_frequency": _pain_monitoring_frequency(rows),
        "discomfort_measures": _discomfort_measures(rows),
        "funding_source": _funding(admin),
        "team": _team(admin, study),
        "animals": _animals(rows),
    }


def generate_iacuc_docx(payload):
    """Render the filled IACUC form and return it as an in-memory BytesIO."""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"IACUC template not found at {TEMPLATE_PATH}. "
            "Run: python iacuc_assets/build_template.py")
    tpl = DocxTemplate(str(TEMPLATE_PATH))
    tpl.render(build_context(payload))
    buf = io.BytesIO()
    tpl.save(buf)
    buf.seek(0)
    return buf
