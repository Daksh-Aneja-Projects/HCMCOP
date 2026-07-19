"""Premium dark-enterprise theme: global CSS, inline SVG icon set, and small
HTML render helpers for the Streamlit UI.

Everything here is self-contained (no external fonts/CSS/JS) so it renders
identically offline and inside a locked-down container.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Inline SVG icon set (24px, stroke-based line icons, inherit currentColor).
# ---------------------------------------------------------------------------

_ICONS: dict[str, str] = {
    # Brand / agent mark
    "logo": '<path d="M12 2a2 2 0 0 1 2 2v1.1a7 7 0 0 1 4.9 4.9H20a2 2 0 1 1 0 4h-1.1a7 7 0 0 1-4.9 4.9V20a2 2 0 1 1-4 0v-1.1A7 7 0 0 1 5.1 14H4a2 2 0 1 1 0-4h1.1A7 7 0 0 1 10 5.1V4a2 2 0 0 1 2-2Z"/><circle cx="12" cy="12" r="3"/>',
    # Pipeline steps
    "parse": '<path d="M4 4h10l6 6v10a0 0 0 0 1 0 0H4a0 0 0 0 1 0 0Z"/><path d="M14 4v6h6"/><path d="M9 14l2 2 4-4"/>',
    "compliance": '<path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3Z"/><path d="M9 12l2 2 4-4"/>',
    "ctc": '<circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5c0-1.1 1.1-2 2.5-2s2.5.9 2.5 2-1.1 1.7-2.5 2-2.5.9-2.5 2 1.1 2 2.5 2 2.5-.9 2.5-2"/>',
    "offer": '<path d="M6 2h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/>',
    "approval": '<path d="M12 2l2.4 1.8 3 .2.9 2.9 2.3 1.9-.9 2.9.9 2.9-2.3 1.9-.9 2.9-3 .2L12 22l-2.4-1.5-3-.2-.9-2.9L3.4 15.5l.9-2.9-.9-2.9 2.3-1.9.9-2.9 3-.2Z"/><path d="M9 12l2 2 4-4"/>',
    "checklist": '<path d="M4 6h2M4 12h2M4 18h2"/><path d="M9 6h11M9 12h11M9 18h11"/>',
    "complete": '<path d="M5 21V4a1 1 0 0 1 1-1h10l-2 4 2 4H6"/><circle cx="5" cy="21" r="0.6"/>',
    # UI accents
    "sparkle": '<path d="M12 3l1.8 4.9L19 9.7l-4.9 1.8L12 16l-2.1-4.5L5 9.7l5.2-1.8Z"/><path d="M19 15l.9 2.4L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.6Z"/>',
    "robot": '<rect x="4" y="8" width="16" height="11" rx="2"/><path d="M12 8V4M9 4h6"/><circle cx="9" cy="13" r="1.2"/><circle cx="15" cy="13" r="1.2"/><path d="M9.5 16.5h5"/>',
    "alert": '<path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v5M12 18h.01"/>',
    "download": '<path d="M12 3v12M7 11l5 5 5-5"/><path d="M4 20h16"/>',
    "edit": '<path d="M4 20h4L20 8l-4-4L4 16v4Z"/><path d="M14 6l4 4"/>',
    "check": '<path d="M5 13l4 4L19 7"/>',
    "send": '<path d="M4 12l16-8-6 16-3-6-7-2Z"/>',
    "shield": '<path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3Z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "pin": '<path d="M12 21s7-5.7 7-11a7 7 0 1 0-14 0c0 5.3 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/>',
    "flag": '<path d="M5 21V4a1 1 0 0 1 1-1h10l-2 4 2 4H6"/>',
}


def icon(name: str, size: int = 20, color: str = "currentColor", stroke: float = 1.75) -> str:
    """Return an inline SVG string for the named icon."""
    body = _ICONS.get(name, _ICONS["sparkle"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round" class="hcm-ico">{body}</svg>'
    )


# Maps workflow phases to an icon key for the sidebar stepper.
PHASE_ICONS = {
    "Request Parsing": "parse",
    "Compliance Check": "compliance",
    "CTC Estimation": "ctc",
    "Offer Draft": "offer",
    "Compliance Review": "shield",
    "Human Approval": "approval",
    "Onboarding Checklist": "checklist",
    "Complete": "complete",
    # Workforce-integration (M&A) phases
    "Council Convened": "robot",
    "Positions Gathered": "compliance",
    "Conflicts Detected": "alert",
    "Human Resolution": "approval",
    "Integration Plan": "checklist",
}


# ---------------------------------------------------------------------------
# Global CSS — sleek dark enterprise.
# ---------------------------------------------------------------------------

GLOBAL_CSS = """
<style>
:root{
  --bg:#0a0e17; --surface:#121826; --surface-2:#161d2e; --border:#232c40;
  --border-soft:#1c2437; --text:#e6ebf5; --muted:#8a95ad; --muted-2:#5f6b85;
  --accent:#6366f1; --accent-2:#8b5cf6; --accent-3:#22d3ee;
  --good:#34d399; --warn:#fbbf24; --danger:#fb7185;
  --grad:linear-gradient(135deg,#6366f1 0%,#8b5cf6 55%,#22d3ee 130%);
}
html,body,[class*="css"]{ font-feature-settings:"cv02","cv03","cv04"; }
.stApp{
  background:
    radial-gradient(1200px 600px at 15% -10%, rgba(99,102,241,.14), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(34,211,238,.10), transparent 55%),
    var(--bg);
  color:var(--text);
}
/* hide default chrome for a cleaner canvas */
#MainMenu, footer, header [data-testid="stToolbar"]{ visibility:hidden; }
[data-testid="stDecoration"]{ display:none; }

.block-container{ padding-top:2.2rem; max-width:1120px; }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#0d1220 0%, #0a0e17 100%);
  border-right:1px solid var(--border-soft);
}
section[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }

.hcm-brand{ display:flex; align-items:center; gap:.7rem; margin-bottom:.2rem; }
.hcm-brand .mark{
  width:42px; height:42px; border-radius:12px; display:grid; place-items:center;
  background:var(--grad); color:#fff; box-shadow:0 8px 24px -8px rgba(99,102,241,.7);
}
.hcm-brand h1{ font-size:1.18rem; margin:0; font-weight:750; letter-spacing:-.01em; color:var(--text);}
.hcm-brand p{ margin:0; font-size:.72rem; color:var(--muted); letter-spacing:.14em; text-transform:uppercase;}

.hcm-sep{ height:1px; background:linear-gradient(90deg,transparent,var(--border),transparent); margin:1.1rem 0; border:0;}
.hcm-side-title{ font-size:.72rem; letter-spacing:.16em; text-transform:uppercase; color:var(--muted); margin:.2rem 0 .9rem;}

/* ---------- Stepper ---------- */
.hcm-step{ position:relative; display:flex; align-items:center; gap:.75rem; padding:.42rem 0; }
.hcm-step .rail{ position:absolute; left:15px; top:34px; bottom:-8px; width:2px; background:var(--border); }
.hcm-step:last-child .rail{ display:none; }
.hcm-node{
  width:32px; height:32px; min-width:32px; border-radius:9px; display:grid; place-items:center;
  background:var(--surface); border:1px solid var(--border); color:var(--muted); z-index:1;
  transition:all .25s ease;
}
.hcm-step .lbl{ font-size:.86rem; color:var(--muted); font-weight:550; }
.hcm-step.done .hcm-node{ background:rgba(52,211,153,.12); border-color:rgba(52,211,153,.45); color:var(--good); }
.hcm-step.done .lbl{ color:#b9c2d6; }
.hcm-step.active .hcm-node{
  background:var(--grad); border-color:transparent; color:#fff;
  box-shadow:0 0 0 4px rgba(99,102,241,.16), 0 8px 20px -8px rgba(99,102,241,.8);
}
.hcm-step.active .lbl{ color:var(--text); font-weight:700; }
.hcm-step.active .rail{ background:linear-gradient(180deg,var(--accent),var(--border)); }

/* ---------- Hero ---------- */
.hcm-hero{ margin:.2rem 0 1.4rem; }
.hcm-eyebrow{
  display:inline-flex; align-items:center; gap:.4rem; padding:.34rem .7rem; border-radius:999px;
  background:rgba(99,102,241,.10); border:1px solid rgba(99,102,241,.28); color:#c7ccf5;
  font-size:.74rem; font-weight:600; letter-spacing:.02em; margin-bottom:.9rem;
}
.hcm-hero h1{
  font-size:2.6rem; line-height:1.05; margin:.1rem 0 .5rem; font-weight:800; letter-spacing:-.03em;
  background:linear-gradient(120deg,#fff 20%, #b9c0ff 55%, #8fe6f5 100%);
  -webkit-background-clip:text; background-clip:text; color:transparent;
}
.hcm-hero p{ color:var(--muted); font-size:1.02rem; max-width:640px; margin:0; }

/* ---------- Cards ---------- */
.hcm-card{
  background:linear-gradient(180deg,var(--surface) 0%, var(--surface-2) 100%);
  border:1px solid var(--border); border-radius:16px; padding:1.05rem 1.15rem;
  box-shadow:0 20px 40px -28px rgba(0,0,0,.8); margin-bottom:.2rem;
}
.hcm-card-head{ display:flex; align-items:center; gap:.65rem; margin-bottom:.15rem; }
.hcm-card-ico{
  width:38px; height:38px; min-width:38px; border-radius:11px; display:grid; place-items:center;
  background:rgba(99,102,241,.12); border:1px solid rgba(99,102,241,.25); color:#a7adf7;
}
.hcm-card-ico.good{ background:rgba(52,211,153,.12); border-color:rgba(52,211,153,.3); color:var(--good);}
.hcm-card-ico.warn{ background:rgba(251,191,36,.12); border-color:rgba(251,191,36,.3); color:var(--warn);}
.hcm-card-title{ font-size:1.02rem; font-weight:700; margin:0; color:var(--text); }
.hcm-card-sub{ font-size:.8rem; color:var(--muted); margin:.05rem 0 0; }

/* pills / chips */
.hcm-pill{ display:inline-flex; align-items:center; gap:.35rem; padding:.28rem .6rem; border-radius:999px;
  font-size:.76rem; font-weight:600; background:var(--surface-2); border:1px solid var(--border); color:#c3cadb; margin:.15rem .3rem .15rem 0;}
.hcm-pill.good{ color:var(--good); border-color:rgba(52,211,153,.35); background:rgba(52,211,153,.08);}
.hcm-pill.warn{ color:var(--warn); border-color:rgba(251,191,36,.35); background:rgba(251,191,36,.08);}

/* ---------- Native widget polish ---------- */
[data-testid="stExpander"]{
  border:1px solid var(--border) !important; border-radius:14px !important;
  background:linear-gradient(180deg,var(--surface),var(--surface-2)) !important; overflow:hidden;
}
[data-testid="stExpander"] summary{ font-weight:650; padding:.55rem .3rem; }
[data-testid="stExpander"] summary:hover{ color:#fff; }

div[data-testid="stChatInput"] textarea{ background:var(--surface-2) !important; }

.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
  border-radius:11px; font-weight:650; border:1px solid var(--border);
  background:var(--surface-2); color:var(--text); transition:all .18s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover, .stFormSubmitButton>button:hover{
  border-color:var(--accent); transform:translateY(-1px);
  box-shadow:0 10px 24px -14px rgba(99,102,241,.9);
}
.stButton>button[kind="primary"], .stFormSubmitButton>button[kind="primary"]{
  background:var(--grad); border:none; color:#fff;
  box-shadow:0 12px 28px -12px rgba(99,102,241,.9);
}
.stButton>button[kind="primary"]:hover{ filter:brightness(1.07); }

[data-testid="stMetric"]{
  background:linear-gradient(180deg,var(--surface),var(--surface-2)); border:1px solid var(--border);
  border-radius:13px; padding:.7rem .9rem;
}
[data-testid="stMetricValue"]{ font-size:1.25rem !important; font-weight:750; }
[data-testid="stMetricLabel"]{ color:var(--muted) !important; }

/* chat bubbles */
[data-testid="stChatMessage"]{ background:transparent; }

/* approval banner */
.hcm-gate{
  border:1px solid rgba(251,191,36,.4); border-radius:16px; padding:1rem 1.2rem;
  background:linear-gradient(180deg, rgba(251,191,36,.10), rgba(251,191,36,.03));
  margin-bottom:1rem;
}
.hcm-gate .g-head{ display:flex; align-items:center; gap:.6rem; color:var(--warn); font-weight:750; font-size:1.02rem; }

/* status dot */
.hcm-status{ display:flex; align-items:center; gap:.5rem; padding:.55rem .7rem; border-radius:11px;
  border:1px solid var(--border); background:var(--surface); font-size:.82rem; }
.hcm-status.ok{ color:var(--good); border-color:rgba(52,211,153,.3); background:rgba(52,211,153,.07);}
.hcm-status.bad{ color:var(--danger); border-color:rgba(251,113,133,.3); background:rgba(251,113,133,.07);}
.hcm-dot{ width:8px; height:8px; border-radius:50%; background:currentColor; box-shadow:0 0 10px currentColor;}

.hcm-kv{ display:flex; gap:.5rem; font-size:.9rem; padding:.2rem 0; }
.hcm-kv .k{ color:var(--muted); min-width:96px; }
.hcm-kv .v{ color:var(--text); font-weight:600; }

/* inline-flowing pill row (fixes stacked-pill misalignment) */
.hcm-pillrow{ display:flex; flex-wrap:wrap; gap:.35rem; margin:.5rem 0 .2rem; }
.hcm-pillrow:empty{ display:none; margin:0; }

/* real bordered cards (st.container(border=True)) — align header + content */
div[data-testid="stVerticalBlockBorderWrapper"]{
  border-radius:16px !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div{ border-radius:16px; }
.hcm-card-head{ margin-top:.1rem; }

/* agent position card */
.hcm-agentcard{ border:1px solid var(--border); border-radius:14px; padding:.8rem .95rem;
  background:linear-gradient(180deg,var(--surface),var(--surface-2)); margin-bottom:.55rem; }
.hcm-agentcard .a-head{ display:flex; align-items:center; gap:.5rem; margin-bottom:.35rem; }
.hcm-agentcard .a-badge{ font-size:.7rem; font-weight:750; padding:.2rem .5rem; border-radius:7px; color:#fff; }
.hcm-agentcard .a-stmt{ font-size:.92rem; color:var(--text); font-weight:550; }
.hcm-agentcard .a-why{ font-size:.78rem; color:var(--muted); margin-top:.25rem; }

/* conflict card */
.hcm-conflict{ border:1px solid rgba(251,113,133,.4); border-radius:14px; padding:.9rem 1rem;
  background:linear-gradient(180deg, rgba(251,113,133,.09), rgba(251,113,133,.02)); margin-bottom:.6rem; }
.hcm-conflict.resolved{ border-color:rgba(52,211,153,.4);
  background:linear-gradient(180deg, rgba(52,211,153,.09), rgba(52,211,153,.02)); }
.hcm-vs{ display:grid; grid-template-columns:1fr auto 1fr; gap:.6rem; align-items:stretch; margin:.5rem 0; }
.hcm-vs .side{ border:1px solid var(--border); border-radius:10px; padding:.55rem .65rem; background:var(--surface-2); }
.hcm-vs .side .who{ font-size:.72rem; font-weight:700; margin-bottom:.2rem; }
.hcm-vs .side .txt{ font-size:.82rem; color:var(--text); }
.hcm-vs .clash{ display:grid; place-items:center; color:var(--danger); font-weight:800; font-size:.8rem; }
</style>
"""


# ---------------------------------------------------------------------------
# HTML render helpers
# ---------------------------------------------------------------------------

def brand_html() -> str:
    return (
        '<div class="hcm-brand">'
        f'<div class="mark">{icon("logo", 24, "#fff", 1.6)}</div>'
        "<div><h1>HCM Autopilot</h1><p>Hiring Operations Agent</p></div>"
        "</div>"
    )


def stepper_html(phases: list[str], active: str) -> str:
    active_idx = phases.index(active) if active in phases else 0
    rows = []
    for i, phase in enumerate(phases):
        cls = "done" if i < active_idx else ("active" if i == active_idx else "todo")
        ico = icon("check", 16) if cls == "done" else icon(PHASE_ICONS.get(phase, "sparkle"), 16)
        rows.append(
            f'<div class="hcm-step {cls}"><span class="rail"></span>'
            f'<span class="hcm-node">{ico}</span><span class="lbl">{phase}</span></div>'
        )
    return '<div class="hcm-stepper">' + "".join(rows) + "</div>"


def hero_html(eyebrow: str, title: str, subtitle: str) -> str:
    return (
        '<div class="hcm-hero">'
        f'<span class="hcm-eyebrow">{icon("sparkle", 14)} {eyebrow}</span>'
        f"<h1>{title}</h1><p>{subtitle}</p>"
        "</div>"
    )


def card_head(icon_name: str, title: str, subtitle: str = "", tone: str = "") -> str:
    tone_cls = f" {tone}" if tone else ""
    sub = f'<p class="hcm-card-sub">{subtitle}</p>' if subtitle else ""
    return (
        '<div class="hcm-card-head">'
        f'<span class="hcm-card-ico{tone_cls}">{icon(icon_name, 20)}</span>'
        f'<div><p class="hcm-card-title">{title}</p>{sub}</div>'
        "</div>"
    )


def status_html(ok: bool, text: str) -> str:
    cls = "ok" if ok else "bad"
    return f'<div class="hcm-status {cls}"><span class="hcm-dot"></span>{text}</div>'
