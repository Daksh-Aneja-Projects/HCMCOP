# HCM Autopilot Agent

An enterprise **Human Capital Management (HCM)** autopilot that turns an
ambiguous, natural-language hiring request into a complete, compliant
**onboarding package** — autonomously decomposing the work, orchestrating
execution through **Qwen Cloud function calling**, and pausing for
**human approval** at the critical checkpoint before finalizing.

This is a workflow-automation agent, not a chatbot. The model reasons about
what's missing, asks for clarification when the input is ambiguous, runs a
multi-step tool pipeline, and stops for a human before the offer is committed.

![HCM Autopilot UI](docs/screenshots/landing.png)

---

## What it does

Given something as vague as *"We need a senior backend dev in Bangalore, starting
next month,"* the agent:

1. **Parses** the request into structured fields, resolving relative dates and
   flagging missing critical info (asks you if role/location are unclear).
2. **Checks geo-compliance** — notice periods, probation, mandatory benefits,
   required documents, statutory filings, and risk flags.
3. **Estimates the CTC band** for the role, level and location.
4. **Drafts an offer letter** with all key terms filled in.
5. **Pauses for human approval** — shows a summary and waits for an explicit
   *Approve* or *Revise* decision. It never auto-approves.
6. On approval, **generates a sequenced onboarding checklist** with owners and
   deadlines relative to the start date.
7. Lets you **download the full package** as JSON or Markdown.

Reject at the gate with a note like *"cap CTC at 30L"* and the agent re-runs the
affected tools and re-presents the checkpoint.

---

## Architecture

```
User (Streamlit UI)
      │  request / clarifications / approval
      ▼
Orchestrator Agent  ──►  Qwen Cloud API (qwen-plus / qwen-turbo, function calling)
      │
      ├─ parse_hiring_request        (LLM extraction)
      ├─ check_geo_compliance        (knowledge base)
      ├─ estimate_ctc_band           (knowledge base)
      ├─ generate_offer_letter       (template)
      ├─ flag_for_approval           HUMAN-IN-THE-LOOP
      └─ create_onboarding_checklist (deterministic)
                    │
                    ▼
        Onboarding Package (offer · compliance · CTC · checklist · timeline)
```

Full Mermaid diagram and design rationale: **[docs/architecture.md](docs/architecture.md)**.

All LLM reasoning flows through the OpenAI SDK pointed at Qwen Cloud:

```python
from openai import OpenAI
client = OpenAI(
    api_key=os.getenv("QWEN_CLOUD_API_KEY"),
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)
```

---

## Setup & run

**Prerequisites:** Python 3.11+ and a Qwen Cloud (DashScope international) API key.

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. configure
cp .env.example .env          # then set QWEN_CLOUD_API_KEY in .env

# 3. run
streamlit run app.py          # opens http://localhost:8501
```

---

## Docker / Alibaba Cloud ECS

```bash
docker build -t hcm-autopilot .
docker run --rm -p 8501:8501 --env-file .env hcm-autopilot
# or:
docker compose up --build
```

**On Alibaba Cloud ECS:**
1. Provision an ECS instance (Ubuntu 22.04, ≥1 vCPU / 2 GB) with Docker installed.
2. Open inbound TCP **8501** in the security group (or front it with an SLB / Nginx).
3. Copy the project to the instance and create `.env` with your `QWEN_CLOUD_API_KEY`
   (never bake keys into the image).
4. `docker compose up -d --build`, then browse to `http://<ecs-public-ip>:8501`.
   A container `HEALTHCHECK` polls Streamlit's `/_stcore/health` endpoint.

---

## Tests

```bash
pytest -q
```

The suite covers the compliance knowledge base, the deterministic tools (CTC,
offer letter, onboarding), and the orchestrator's full control flow — including
the human-in-the-loop pause and the revise/re-run path — with the Qwen client
mocked so it runs offline.

---

## Configuration notes

- **No hardcoded secrets.** The API key is read only from `QWEN_CLOUD_API_KEY`
  via `python-dotenv`. `.env` is git-ignored; `.env.example` documents the vars.
- **No database** — all workflow state lives in Streamlit session state.
- **No external APIs** beyond Qwen Cloud; compliance and salary data are
  self-contained knowledge bases.

---

## Project structure

```
hcm-autopilot/
├── app.py                      # Streamlit entry point
├── src/
│   ├── agent/orchestrator.py   # Agent loop + Qwen function calling (resumable)
│   ├── tools/                  # parse, compliance, ctc, offer, onboarding, approval
│   ├── knowledge/              # compliance_data.py, salary_bands.py (hardcoded KBs)
│   ├── ui/theme.py             # dark-enterprise theme + inline SVG icon set
│   └── utils/qwen_client.py    # Qwen Cloud API client wrapper
├── tests/                      # pytest suite
├── docs/architecture.md        # Mermaid architecture diagram + rationale
├── Dockerfile / docker-compose.yml
├── requirements.txt
├── .env.example / .gitignore
├── LICENSE                     # MIT
└── README.md
```

---

## License

Released under the [MIT License](LICENSE).
