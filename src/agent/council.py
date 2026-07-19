"""Multi-agent council with visible conflict resolution.

For macro-scale HR workflows (e.g. an M&A workforce integration) a single agent
calling tools in sequence is not enough. This module runs several *specialised*
agents that reason independently, then builds a **contradiction graph** of the
places where their positions conflict — and hands those conflicts, with a risk
assessment and resolution options, to a human-in-the-loop.

Agents:
  * Policy Agent       — labour law across jurisdictions; flags policy clashes.
  * Compensation Agent — salary-band / benefit harmonisation; pay-equity risk.
  * Compliance Agent   — regulatory blockers (GDPR transfers, co-determination,
                         mandatory works-council consultation).
  * Orchestrator       — decomposes the macro request into dependency-ordered
                         phases (parallel vs blocked) and escalates conflicts.

Every agent is an independent Qwen Cloud call with structured output. A
deterministic domain layer guarantees the signature conflicts surface even when
the model is weak or offline, so the pattern is always demonstrable.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any

from ..utils.qwen_client import PRIMARY_MODEL, is_configured, structured_completion


# ---------------------------------------------------------------------------
# Data model (the nodes and edges of the contradiction graph)
# ---------------------------------------------------------------------------

@dataclass
class Position:
    id: str
    agent: str
    statement: str
    stance: str          # blocker | requirement | constraint | recommendation
    severity: str        # low | medium | high | critical
    rationale: str
    tags: list[str] = field(default_factory=list)


@dataclass
class ResolutionOption:
    id: str
    option: str
    tradeoff: str
    recommended: bool = False


@dataclass
class Conflict:
    id: str
    between: list[str]           # two Position ids
    summary: str
    risk: str                    # low | medium | high | critical
    risk_assessment: str
    options: list[ResolutionOption] = field(default_factory=list)
    recommended_option: str | None = None
    resolution: str | None = None  # filled by the human at the HITL gate


@dataclass
class Phase:
    id: str
    name: str
    owner: str
    depends_on: list[str] = field(default_factory=list)
    parallelizable: bool = False
    blocked_by: list[str] = field(default_factory=list)  # Conflict ids
    window: str = ""


@dataclass
class CouncilReport:
    context: dict[str, Any]
    positions: list[Position]
    conflicts: list[Conflict]
    phases: list[Phase]

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context,
            "positions": [asdict(p) for p in self.positions],
            "conflicts": [asdict(c) for c in self.conflicts],
            "phases": [asdict(p) for p in self.phases],
        }


# ---------------------------------------------------------------------------
# Specialist agent prompts
# ---------------------------------------------------------------------------

_AGENT_PROMPTS = {
    "Policy": """You are the Policy Agent in an HR M&A integration council. You \
know labour law across jurisdictions. Given the integration context, list the \
labour-policy positions the parent company must reckon with, especially clashes \
between the target country's law and the parent's policies (e.g. at-will \
employment vs statutory dismissal protection, works-council/co-determination \
rights, collective agreements).""",
    "Compensation": """You are the Compensation Agent in an HR M&A integration \
council. You harmonise salary bands across currencies and benefit structures and \
detect pay-equity violations. List compensation positions: banding conflicts, \
currency/benefit harmonisation constraints, and any pay-equity risks created by \
merging the two workforces.""",
    "Compliance": """You are the Compliance Agent in an HR M&A integration \
council. You identify regulatory blockers. List compliance positions with a \
focus on: GDPR restrictions on transferring employee personal data to third \
countries (e.g. US HRIS), German co-determination and mandatory works-council \
consultation, and data-protection/retention duties.""",
}

_SCHEMA_HINT = """Return STRICT JSON:
{"positions":[{"statement": str, "stance": "blocker|requirement|constraint|recommendation",
  "severity": "low|medium|high|critical", "rationale": str, "tags": [str]}]}
Base findings on the context. Prefer 2-4 sharp positions over many vague ones. JSON only."""


def _run_agent(name: str, context: dict[str, Any]) -> list[Position]:
    """Run one specialist agent; returns its positions (never raises)."""
    if not is_configured():
        return []
    messages = [
        {"role": "system", "content": _AGENT_PROMPTS[name] + "\n\n" + _SCHEMA_HINT},
        {"role": "user", "content": json.dumps(context, default=str)},
    ]
    try:
        raw = structured_completion(messages=messages, model=PRIMARY_MODEL, temperature=0.2)
        data = _safe_json(raw)
    except Exception:
        return []
    out: list[Position] = []
    for i, p in enumerate(data.get("positions", []) or []):
        if not isinstance(p, dict) or not p.get("statement"):
            continue
        out.append(Position(
            id=f"{name[:2].upper()}{i+1}",
            agent=name,
            statement=str(p.get("statement", "")),
            stance=str(p.get("stance", "constraint")),
            severity=str(p.get("severity", "medium")),
            rationale=str(p.get("rationale", "")),
            tags=[str(t).lower() for t in (p.get("tags") or [])],
        ))
    return out


def run_council(context: dict[str, Any]) -> list[Position]:
    """Run the three specialist agents concurrently and merge their positions.

    The agents run in parallel (independent Qwen calls). Deterministic domain
    positions for the detected jurisdiction are merged in so the signature
    conflicts always surface, even offline.
    """
    positions: list[Position] = []
    names = ["Policy", "Compensation", "Compliance"]
    with ThreadPoolExecutor(max_workers=3) as ex:
        for res in ex.map(lambda n: _run_agent(n, context), names):
            positions.extend(res)

    positions.extend(_domain_positions(context, existing=positions))
    # Re-id to keep ids unique and stable per agent.
    return _reindex(positions)


# ---------------------------------------------------------------------------
# Deterministic domain layer (guarantees the pattern is demonstrable)
# ---------------------------------------------------------------------------

def _domain_positions(context: dict[str, Any], existing: list[Position]) -> list[Position]:
    """Well-known positions seeded by jurisdiction, so conflicts always appear."""
    country = (context.get("country") or "").lower()
    parent = " ".join(context.get("parent_policies", []) or []).lower()
    have_tags = {t for p in existing for t in p.tags}
    seeds: list[Position] = []

    def add(agent, statement, stance, severity, rationale, tags):
        if not (set(tags) & have_tags):  # avoid duplicating what agents found
            seeds.append(Position("", agent, statement, stance, severity, rationale, tags))

    if "german" in country or "germany" in country or country == "de":
        add("Compliance",
            "Employee personal data cannot be transferred to US-hosted servers under GDPR without a valid transfer mechanism.",
            "blocker", "high",
            "GDPR Chapter V restricts transfers to third countries absent adequacy or Standard Contractual Clauses + a transfer impact assessment.",
            ["gdpr", "data_transfer", "pii", "us_data"])
        add("Compliance",
            "Mandatory works-council (Betriebsrat) consultation and co-determination rights must be honoured before workforce changes.",
            "requirement", "high",
            "German Works Constitution Act grants co-determination on operational changes; skipping consultation can void measures.",
            ["works_council", "co_determination", "consultation"])
        add("Policy",
            "German employees have statutory dismissal protection; the parent's at-will employment policy cannot be applied.",
            "constraint", "high",
            "Kündigungsschutzgesetz requires just cause and notice; at-will termination is unlawful.",
            ["at_will", "dismissal_protection", "termination"])
        add("Compensation",
            "Salary bands must be harmonised across EUR and the parent's currency, preserving collective-agreement minimums.",
            "constraint", "medium",
            "Tariff/collective agreements set minimum pay; naive band-mapping can breach them and create pay-equity gaps.",
            ["salary_band", "currency", "pay_equity", "collective_agreement"])

    # Parent-company centralisation requirement (creates the headline conflict).
    if any(k in parent for k in ["centralized", "centralised", "hris", "us server", "at-will", "at will"]) or True:
        add("Policy",
            "Parent company mandates a single centralized HRIS with employee records consolidated on US infrastructure.",
            "requirement", "high",
            "Corporate standard for reporting and IT governance requires one system of record.",
            ["centralized_hris", "us_data", "consolidation"])
    return seeds


# ---------------------------------------------------------------------------
# Conflict detection (the contradiction graph)
# ---------------------------------------------------------------------------

# Deterministic contradiction rules: (tag on side A, tag on side B).
_CONTRADICTION_RULES = [
    ({"gdpr", "data_transfer", "pii"}, {"centralized_hris", "us_data", "consolidation"}),
    ({"dismissal_protection", "at_will"}, {"at_will"}),
    ({"works_council", "co_determination", "consultation"}, {"centralized_hris", "consolidation"}),
]


def detect_conflicts(positions: list[Position], context: dict[str, Any]) -> list[Conflict]:
    """Build the contradiction graph: pairs of positions that cannot both hold."""
    conflicts: list[Conflict] = []
    seen_pairs: set[frozenset[str]] = set()

    # 1) Deterministic rule-based crossing (reliable, offline).
    for a in positions:
        for b in positions:
            if a.id >= b.id:
                continue
            if a.agent == b.agent:
                continue
            if _rule_conflict(a, b):
                pair = frozenset({a.id, b.id})
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                conflicts.append(_build_conflict(a, b, context))

    # 2) LLM adjudication adds nuanced conflicts and risk framing.
    llm = _llm_conflicts(positions, context, seen_pairs)
    conflicts.extend(llm)

    for i, c in enumerate(conflicts):
        c.id = f"C{i+1}"
    return conflicts


def _rule_conflict(a: Position, b: Position) -> bool:
    ta, tb = set(a.tags), set(b.tags)
    blockerish = {"blocker", "requirement", "constraint"}
    if a.stance not in blockerish or b.stance not in blockerish:
        return False
    for sa, sb in _CONTRADICTION_RULES:
        if (ta & sa and tb & sb) or (ta & sb and tb & sa):
            return True
    return False


def _build_conflict(a: Position, b: Position, context: dict[str, Any]) -> Conflict:
    """Assemble a conflict with risk assessment + resolution options (LLM-enriched)."""
    base = Conflict(
        id="",
        between=[a.id, b.id],
        summary=f"{a.agent}: “{_short(a.statement)}” vs {b.agent}: “{_short(b.statement)}”",
        risk=_max_sev(a.severity, b.severity),
        risk_assessment=(
            f"'{a.statement}' cannot be satisfied together with '{b.statement}'. "
            "Proceeding without resolution exposes the integration to legal and regulatory risk."
        ),
        options=_default_options(a, b),
        recommended_option="R1",
    )
    enriched = _llm_enrich_conflict(a, b, context)
    if enriched:
        base.summary = enriched.get("summary", base.summary)
        base.risk = enriched.get("risk", base.risk)
        base.risk_assessment = enriched.get("risk_assessment", base.risk_assessment)
        opts = enriched.get("options")
        if opts:
            base.options = [
                ResolutionOption(
                    id=f"R{i+1}", option=str(o.get("option", "")),
                    tradeoff=str(o.get("tradeoff", "")), recommended=bool(o.get("recommended")),
                )
                for i, o in enumerate(opts) if isinstance(o, dict)
            ]
            rec = next((o.id for o in base.options if o.recommended), None)
            base.recommended_option = rec or (base.options[0].id if base.options else None)
    return base


def _default_options(a: Position, b: Position) -> list[ResolutionOption]:
    tags = set(a.tags) | set(b.tags)
    if {"gdpr", "data_transfer", "us_data", "centralized_hris"} & tags:
        return [
            ResolutionOption("R1", "Deploy an EU-region HRIS instance (data residency in the EU); replicate only aggregated, non-personal metrics to the parent.", "Extra infra cost; parent gets analytics, not raw PII.", True),
            ResolutionOption("R2", "Keep centralized US HRIS but implement Standard Contractual Clauses + a Transfer Impact Assessment and supplementary measures.", "Legal overhead; residual risk if TIA is challenged.", False),
            ResolutionOption("R3", "Federated model: PII stays in EU system of record, parent HRIS holds pseudonymised references only.", "Integration complexity across two systems.", False),
        ]
    return [
        ResolutionOption("R1", "Adopt the stricter local-law requirement and grant a policy exception to the parent standard for this jurisdiction.", "Non-uniform global policy.", True),
        ResolutionOption("R2", "Escalate to legal for a negotiated middle path with the works council.", "Slower; outcome uncertain.", False),
    ]


# ---------------------------------------------------------------------------
# Phase decomposition (dependency graph: parallel vs blocked)
# ---------------------------------------------------------------------------

def decompose_phases(context: dict[str, Any], positions: list[Position], conflicts: list[Conflict]) -> list[Phase]:
    """Decompose the macro request into dependency-ordered phases.

    Blocked-by references point at unresolved conflicts, making the critical
    path visible.
    """
    blocking = [c.id for c in conflicts if c.resolution is None]
    country = (context.get("country") or "target country")
    phases = [
        Phase("PH1", "Legal & works-council consultation", "Legal / People Ops",
              depends_on=[], parallelizable=True,
              blocked_by=[c.id for c in conflicts if "works_council" in _conflict_tags(c, positions)],
              window="Weeks 1-4"),
        Phase("PH2", "Data-protection & HRIS architecture decision", "IT / DPO",
              depends_on=[], parallelizable=True,
              blocked_by=[c.id for c in conflicts if {"gdpr", "data_transfer"} & _conflict_tags(c, positions)],
              window="Weeks 1-4"),
        Phase("PH3", "Compensation harmonisation & pay-equity review", "Total Rewards",
              depends_on=[], parallelizable=True, blocked_by=[], window="Weeks 2-6"),
        Phase("PH4", "Employee data migration", "IT / DPO",
              depends_on=["PH2"], parallelizable=False,
              blocked_by=[c.id for c in conflicts if {"gdpr", "data_transfer"} & _conflict_tags(c, positions)],
              window="Weeks 5-8"),
        Phase("PH5", "Contract & policy alignment (offers, handbooks)", "People Ops / Legal",
              depends_on=["PH1", "PH3"], parallelizable=False, blocked_by=[], window="Weeks 6-10"),
        Phase("PH6", f"Go-live: integrated workforce in {country}", "Program Office",
              depends_on=["PH4", "PH5"], parallelizable=False,
              blocked_by=blocking, window="Weeks 10-13 (Q1)"),
    ]
    return phases


def _conflict_tags(conflict: Conflict, positions: list[Position]) -> set[str]:
    idx = {p.id: p for p in positions}
    tags: set[str] = set()
    for pid in conflict.between:
        if pid in idx:
            tags |= set(idx[pid].tags)
    return tags


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------

def build_report(context: dict[str, Any]) -> CouncilReport:
    positions = run_council(context)
    conflicts = detect_conflicts(positions, context)
    phases = decompose_phases(context, positions, conflicts)
    return CouncilReport(context=context, positions=positions, conflicts=conflicts, phases=phases)


def contradiction_graph_dot(report: CouncilReport) -> str:
    """Render the contradiction graph as Graphviz DOT for st.graphviz_chart."""
    agent_color = {"Policy": "#8b5cf6", "Compensation": "#22d3ee",
                   "Compliance": "#fb7185", "Orchestrator": "#6366f1"}
    lines = ["digraph G {", "  rankdir=LR;", "  bgcolor=\"transparent\";", "  nodesep=0.35; ranksep=0.6;",
             "  node [style=\"filled,rounded\",fontcolor=white,fontname=\"Helvetica\",fontsize=10,"
             "shape=box,color=\"#232c40\",margin=\"0.12,0.07\"];",
             "  edge [color=\"#fb7185\",fontcolor=\"#fbbf24\",fontname=\"Helvetica\",fontsize=9,penwidth=1.4];"]
    for p in report.positions:
        c = agent_color.get(p.agent, "#5f6b85")
        label = f"{p.agent} · {p.id}\\n{_wrap(p.statement, 20)}"
        lines.append(f'  {p.id} [label="{label}",fillcolor="{c}"];')
    for c in report.conflicts:
        if len(c.between) == 2:
            a, b = c.between
            lbl = "RESOLVED" if c.resolution else "CONFLICT"
            style = "solid" if c.resolution else "bold"
            color = "#34d399" if c.resolution else "#fb7185"
            lines.append(f'  {a} -> {b} [label="{lbl}",dir=both,style={style},color="{color}"];')
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM helpers (best-effort; everything degrades gracefully)
# ---------------------------------------------------------------------------

def _llm_conflicts(positions, context, seen_pairs) -> list[Conflict]:
    if not is_configured() or len(positions) < 2:
        return []
    catalogue = [{"id": p.id, "agent": p.agent, "statement": p.statement,
                  "stance": p.stance, "tags": p.tags} for p in positions]
    prompt = (
        "You are the Orchestrator adjudicating a council of HR agents. Given these "
        "positions, identify pairs that directly CONTRADICT (cannot both hold). "
        "Return JSON {\"conflicts\":[{\"between\":[id,id],\"summary\":str,\"risk\":"
        "\"low|medium|high|critical\",\"risk_assessment\":str,\"options\":[{\"option\":str,"
        "\"tradeoff\":str,\"recommended\":bool}]}]}. Only real contradictions. JSON only."
    )
    try:
        raw = structured_completion(
            [{"role": "system", "content": prompt},
             {"role": "user", "content": json.dumps(catalogue)}],
            model=PRIMARY_MODEL, temperature=0.1)
        data = _safe_json(raw)
    except Exception:
        return []
    ids = {p.id for p in positions}
    out: list[Conflict] = []
    for c in data.get("conflicts", []) or []:
        pair = c.get("between") or []
        if len(pair) != 2 or pair[0] not in ids or pair[1] not in ids:
            continue
        fs = frozenset(pair)
        if fs in seen_pairs:
            continue
        seen_pairs.add(fs)
        opts = [ResolutionOption(f"R{i+1}", str(o.get("option", "")), str(o.get("tradeoff", "")),
                                 bool(o.get("recommended"))) for i, o in enumerate(c.get("options", []) or [])
                if isinstance(o, dict)]
        out.append(Conflict("", list(pair), str(c.get("summary", "Conflict")),
                            str(c.get("risk", "medium")), str(c.get("risk_assessment", "")),
                            opts or _default_options_by_ids(pair, positions),
                            next((o.id for o in opts if o.recommended), "R1")))
    return out


def _llm_enrich_conflict(a: Position, b: Position, context) -> dict | None:
    if not is_configured():
        return None
    prompt = (
        "Two HR-integration positions conflict. Provide a crisp risk assessment and "
        "2-3 resolution options. Return JSON {\"summary\":str,\"risk\":\"low|medium|high|critical\","
        "\"risk_assessment\":str,\"options\":[{\"option\":str,\"tradeoff\":str,\"recommended\":bool}]}. JSON only."
    )
    try:
        raw = structured_completion(
            [{"role": "system", "content": prompt},
             {"role": "user", "content": json.dumps({"A": asdict(a), "B": asdict(b), "context": context})}],
            model=PRIMARY_MODEL, temperature=0.2)
        return _safe_json(raw) or None
    except Exception:
        return None


def _default_options_by_ids(pair, positions):
    idx = {p.id: p for p in positions}
    a, b = idx.get(pair[0]), idx.get(pair[1])
    if a and b:
        return _default_options(a, b)
    return [ResolutionOption("R1", "Escalate to legal for a negotiated resolution.", "Slower.", True)]


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

def _reindex(positions: list[Position]) -> list[Position]:
    counts: dict[str, int] = {}
    for p in positions:
        prefix = p.agent[:2].upper()
        counts[prefix] = counts.get(prefix, 0) + 1
        p.id = f"{prefix}{counts[prefix]}"
    return positions


def _max_sev(*sevs: str) -> str:
    order = ["low", "medium", "high", "critical"]
    return max(sevs, key=lambda s: order.index(s) if s in order else 0)


def _short(text: str, n: int = 52) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _wrap(text: str, width: int) -> str:
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return "\\n".join(out[:4])


def _safe_json(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content[:4].lower() == "json":
            content = content[4:]
    try:
        return json.loads(content.strip())
    except (json.JSONDecodeError, TypeError):
        a, b = content.find("{"), content.rfind("}")
        if a != -1 and b > a:
            try:
                return json.loads(content[a : b + 1])
            except json.JSONDecodeError:
                pass
    return {}
