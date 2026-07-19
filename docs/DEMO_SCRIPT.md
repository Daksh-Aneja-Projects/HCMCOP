# HCM Autopilot Agent — 3-Minute Demo Script

Target runtime: ~3:00. Track 4 submission.

> Note: the live demo runs entirely on **Qwen Cloud (`qwen-plus`)** via DashScope / Model Studio — local Ollama is used only for offline development.

---

### 0:00 – 0:20 — Hook + problem

- **What to say:** "Enterprise hiring ops is slow and risky. A manager fires off a one-line request — 'get me a senior backend dev in Bangalore' — and someone spends days chasing missing details, checking statutory compliance, sizing the offer, and drafting paperwork. Ambiguity, compliance exposure, and long turnaround. HCM Autopilot turns that one line into a complete, compliant onboarding package."
- **What to show on screen:** Title slide / app landing with the tagline, then the empty request box in the Streamlit UI.

### 0:20 – 0:45 — Ambiguous request → structured parse + clarify

- **What to say:** "I paste a deliberately vague request. The agent's first tool call parses it into structured fields using Qwen structured JSON output. It detects the critical fields it has, notices what's genuinely missing, and asks one targeted clarifying question instead of guessing."
- **What to show on screen:** Type an ambiguous request (e.g. "Need someone senior for backend, budget tight"); the `parse_hiring_request` expander showing extracted JSON; the agent pausing with a clarifying question; user answers "Bangalore, India".

### 0:45 – 1:30 — Tool pipeline via Qwen function calling

- **What to say:** "Now the agent runs the pipeline autonomously through Qwen function calling — geo-compliance for India, an indicative CTC band from the salary knowledge base, then a drafted offer letter. Watch the live workflow stepper advance phase by phase, with each tool's reasoning and result in its own expander. Notice the streaming narration and the live token, latency and cost metrics updating per call."
- **What to show on screen:** The phase tracker moving through Compliance Check → CTC Estimation → Offer Draft; open `check_geo_compliance`, `estimate_ctc_band`, `generate_offer_letter` expanders; the streaming text; the token/cost/latency badges.

### 1:30 – 2:05 — Compliance-Critic flags an issue → auto-revise

- **What to say:** "Before any human sees it, a second agent — the Compliance-Critic, its own Qwen call — audits the draft. Here it flags an issue: the CTC lands above the market band (or a pre-start Right-to-Work requirement isn't accounted for). The lead agent doesn't stop — it automatically re-runs the affected tools to cap the CTC, regenerates the offer, and re-reviews until the critic passes."
- **What to show on screen:** The `review_compliance` expander showing `passed: false` and the flagged issue with severity; the agent re-invoking `estimate_ctc_band` (with the cap) and `generate_offer_letter`; the re-review returning `passed: true`.

### 2:05 – 2:35 — Human-in-the-loop approval → package + OSS

- **What to say:** "Only now does it hit the human gate. The agent pauses and presents a concise summary for a reviewer. I approve. The agent generates the sequenced onboarding checklist and timeline, assembles the full package, and publishes it to Alibaba Cloud OSS — downloadable right here, with the whole run written to the audit trail."
- **What to show on screen:** The approval card with the summary; click **Approve**; the `create_onboarding_checklist` output with owners/deadlines and the timeline; the OSS download link / download button.

### 2:35 – 3:00 — Architecture + Qwen usage recap + close

- **What to say:** "Under the hood: a resumable orchestrator that survives Streamlit reruns and threads pause/resume on the tool-call ID; a multi-agent critic loop; RAG over the compliance knowledge base with Qwen embeddings; and full observability. It uses Qwen Cloud end-to-end — `qwen-plus` for reasoning, `qwen-turbo` for speed, `text-embedding-v4` for retrieval, `qwen-vl-max` for document vision — plus Alibaba Cloud OSS and an audit trail. Ambiguous request to compliant, approved, production-ready onboarding package. That's HCM Autopilot, Track 4."
- **What to show on screen:** The architecture flowchart from `docs/architecture.md`; a quick pan over the Qwen Cloud model list and the final downloaded package; closing title slide.
