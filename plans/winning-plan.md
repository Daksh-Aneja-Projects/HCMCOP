# HCM Autopilot — "10x / Win-100%" Implementation Plan

**Track 4: Autopilot Agent** · Global AI Hackathon with Qwen Cloud
Repo: https://github.com/Daksh-Aneja-Projects/HCMCOP

This is a phased, LLM-friendly plan. Each phase is self-contained and can be
executed in a fresh chat context. Every phase cites the exact APIs/patterns to
**copy** (from Phase 0), a verification checklist, and anti-pattern guards.

---

## Strategy: mapping work to the judging rubric

| Criterion | Weight | Our winning move |
|---|---|---|
| Technical Depth & Engineering | 30% | Multi-agent (Planner→Executor→Compliance-Critic) on tiered Qwen models; native function calling + **parallel tool calls**; **streaming** with usage; **structured outputs** (`json_object` + Pydantic); **RAG** via `text-embedding-v4`; **MCP** integration; observability (token/cost/latency + tracing). |
| Innovation & AI Creativity | 30% | Self-critiquing compliance reviewer that can **veto → force revision**; **multimodal** JD/resume image parsing (`qwen-vl`); confidence-driven clarification; a **workflow registry** that generalizes the agent beyond hiring. |
| Problem Value & Impact | 25% | Real enterprise HCM pain (compliance risk, hiring TAT); **persistent memory + immutable audit trail**; **measurable efficiency** vs a single-shot baseline; multi-workflow productization + OSS adoption story. |
| Presentation & Documentation | 15% | Upgraded Mermaid architecture; polished streaming UI with **timeline/Gantt + cost badges + audit panel**; crisp 3-min demo; README with Alibaba-Cloud proof links + track ID; optional blog post. |

**Track-4 judges reward:** ambiguous-input handling, external tool invocation,
human-in-the-loop at critical points, and *production-readiness over toy demos*.
Every phase below reinforces at least one of those.

---

## Phase 0 — Documentation Discovery (CONSOLIDATED — read before building)

### Allowed APIs (verified against official Alibaba Cloud Model Studio docs)

**Endpoints / auth**
- OpenAI-compatible base URL (intl, confirmed still functional):
  `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- Native DashScope SDK: `pip install dashscope`; `import dashscope`;
  `dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"`.
- Auth env var (Alibaba convention): `DASHSCOPE_API_KEY`. (We keep our existing
  `QWEN_CLOUD_API_KEY` and read either.)
- **DashScope = Alibaba Cloud Model Studio (Bailian)** → `qwen_client.py` is
  already valid "proof of Alibaba Cloud API usage".

**Models** (classic aliases still resolve; current-gen also available)
- Reasoning: `qwen-plus`, `qwen-max`, `qwen-turbo`, `qwen-flash` (cheap/fast),
  `qwen-max-latest`. Current-gen: `qwen3.7-max`, `qwen3.7-plus`, `qwen3.6-flash`.
- Long context / documents: `qwen-long`.
- Coder: `qwen-coder` (a.k.a. `qwen2.5-coder` locally).
- Multimodal/vision: `qwen-vl-max`, `qwen-vl-plus`, `qwen3-vl-plus`.
- Embeddings: **`text-embedding-v4`** — selectable `dimensions`
  (2048/1536/1024(default)/768/512/256/128/64), max 8192 tokens/text, batch ≤10.

**Structured output** (source: qwen-structured-output)
```python
resp = client.chat.completions.create(
    model="qwen-plus",
    messages=[{"role":"system","content":"Extract fields. Respond in JSON."},  # MUST contain "json"
              {"role":"user","content":raw}],
    response_format={"type": "json_object"},
)
```

**Function calling** (source: qwen-function-calling): `tool_choice` ∈
`"auto" | "none" | "required" | {"type":"function","function":{"name":...}}`;
`parallel_tool_calls=True` supported; **streaming with tools IS supported**.

**Streaming** (source: model-studio/stream):
```python
client.chat.completions.create(..., stream=True,
    stream_options={"include_usage": True})   # usage arrives in the final chunk
```

**Embeddings** (openai SDK param is `dimensions`; native dashscope param is
`dimension` — singular):
```python
emb = client.embeddings.create(model="text-embedding-v4", input=texts, dimensions=1024)
```

**MCP** (source: model-studio/mcp): via the **Responses API** only, SSE transport,
≤10 servers, on Qwen Max/Plus/Flash:
```python
client.responses.create(model="qwen3.7-plus", input="...",
  tools=[{"type":"mcp","server_protocol":"sse","server_label":"hcm",
          "server_url":"https://.../sse","headers":{"Authorization":"Bearer ..."}}])
```

**Alibaba Cloud OSS** (source: aliyun-oss-python-sdk / oss docs):
```python
import oss2
auth = oss2.Auth(os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"],
                 os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"])
bucket = oss2.Bucket(auth, "https://oss-ap-southeast-1.aliyuncs.com", "your-bucket")
result = bucket.put_object("onboarding/pkg.json", json_bytes)   # result.status == 200
```
Optional persistence: `tablestore` (`OTSClient.put_row`) or ApsaraDB RDS via `PyMySQL`.

### Anti-patterns / gotchas (DO NOT do these)
- ❌ `response_format={"type":"json_schema", ...}` — **not documented** on DashScope.
  Use `json_object` + your own Pydantic/jsonschema validation.
- ❌ Calling `response_format` json_object **without the word "json"** in the
  messages → hard API error. Always inject "Respond in JSON." into the system prompt.
- ❌ Embeddings param mix-up: openai SDK = `dimensions` (plural); dashscope SDK = `dimension`.
- ❌ Assuming a "Qwen Skills" platform API — **no official doc exists**; don't invent it.
  MCP is the real extensibility primitive (via Responses API).
- ❌ Trusting the stale "tools cannot be used with stream=True" note — the current
  function-calling doc supports streamed tool calls. Smoke-test early.
- ❌ Hardcoding context-window numbers (1M/65K figures are third-party) — confirm on
  the model card before quoting in the README.
- ✅ Keep the existing **resumable HITL** (`orchestrator.py:335-378`, `submit_approval:261`)
  and the **tool-call text-extraction** fallback (`_extract_tool_calls_from_text:533`) —
  both are load-bearing and correct.

### Current-state anchors (for "copy, don't transform")
- Tool registration is 5 coordinated edits: `_tool_specs()` `orchestrator.py:117`,
  `_dispatch()` `:382`, `_record_artifact()` `:420`, `_render_artifacts()` `app.py:110`,
  imports `orchestrator.py:30`. Phase advance: `_TOOL_PHASE` `:221` + `PHASES` `:49`.
- LLM call sites: orchestrator reasoning `orchestrator.py:297`; parser extraction
  `parse_request.py:68` (currently prompt-only JSON — upgrade target).
- KB seams (RAG swap points): `compliance.py:31 get_compliance`, `ctc_estimator.py:31 estimate_band`.
- Client: `qwen_client.py:79 chat_completion` (add streaming/usage/model-tier here).

---

## Phase 1 — Qwen Cloud foundation upgrade (backend core)

**What to implement (copy from Phase 0 snippets):**
1. In `qwen_client.py`: add `stream=True` support + `stream_options={"include_usage":True}`
   returning (text, usage); a `structured_completion(messages, schema)` helper that sets
   `response_format={"type":"json_object"}` and injects "Respond in JSON." into the system
   message; an `embed(texts, dimensions=1024)` wrapper on `text-embedding-v4`.
2. Add **model tiering**: `qwen-plus` for reasoning/critic, `qwen-flash`/`qwen-turbo` for
   cheap extraction, configurable via env (`QWEN_PRIMARY_MODEL`, `QWEN_FAST_MODEL`).
3. Add lightweight **usage/cost/latency capture** (dataclass `CallMetrics`) recorded per call.
4. Upgrade `parse_request.py:68` to `structured_completion` + **Pydantic** model
   `ParsedRequest` validation (replace regex-only `_safe_json`).

**Verification:** new unit tests for `structured_completion` (mock), `embed` shape,
metrics capture; existing 20 tests still green; live smoke test that `qwen-plus` returns
native `tool_calls` (confirm the `orchestrator.py:527` assumption).

**Anti-pattern guards:** grep to ensure no `json_schema` usage; assert system prompt
contains "json" wherever `response_format` is set.

---

## Phase 2 — Multi-agent orchestration (Planner → Executor → Compliance-Critic)

**What to implement:**
1. **Planner agent** (qwen-plus): given the request, emit an explicit ordered plan of
   tool steps (structured output). Surfaces "the agent's reasoning" the judges want to see.
2. **Executor** = current tool loop (keep it).
3. **Compliance-Critic agent** (qwen-plus, distinct system prompt): after the offer draft,
   review against compliance facts; if it finds a violation (e.g. below statutory floor,
   missing Right-to-Work step), it **vetoes** and injects a revision instruction that
   re-runs the affected tools *before* the human gate. This is the reflection/negotiation
   loop that differentiates a multi-agent system from a linear pipeline.
4. Enable `parallel_tool_calls=True` for independent tools (compliance + CTC can run together).
5. Add structured **logging** (`logging` module) + an in-UI **trace timeline** of agent turns.

**Verification:** a test where the critic forces a revision (mock a sub-floor CTC → expect a
re-run then approval gate); measure and log step count / tokens for a "measurable efficiency"
claim vs a single-prompt baseline.

**Anti-pattern guards:** critic must cite compliance-KB facts (no free-form legal claims);
keep the human gate as the final authority even after the critic passes.

---

## Phase 3 — RAG + persistent memory + Alibaba Cloud services

**What to implement:**
1. **Embeddings RAG** behind the existing KB seams (`compliance.py:31`, `ctc_estimator.py:31`):
   ingest compliance/salary docs → `text-embedding-v4` → vector store (start with a local
   FAISS/SQLite; optionally Alibaba **Tablestore**). Adds document upload → the KB is no
   longer limited to 4 hardcoded countries.
2. **Persistence / memory**: serialize `messages` + `artifacts` + audit record per session
   id (thread through `app.py:40 _init_state` / `app.py:309`). Cross-session req history & dedupe.
3. **Immutable audit trail**: in `submit_approval:261` capture reviewer email
   (`userEmail` is available), timestamp, decision, notes → append-only record.
4. **Alibaba Cloud OSS** (`oss_client.py`, Phase-0 snippet A): "Publish package to OSS" button
   in `_render_download` `app.py:228`; also persist audit records to OSS/Tablestore. This is
   the **second, unambiguous Alibaba Cloud service** for the deployment-proof requirement.
5. **Multimodal** (`qwen-vl-max`): accept a JD screenshot / resume image; a `parse_jd_image`
   tool that feeds structured fields into the same pipeline.

**Verification:** RAG test (retrieve a known clause), OSS upload test (mock/real bucket with
`result.status == 200`), audit-record test (reviewer identity persisted), multimodal smoke test.

**Anti-pattern guards:** never log AK/secret; OSS creds via env only; `dimensions` (plural)
on the openai SDK path.

---

## Phase 4 — Workflow registry (generalize beyond hiring → "not a toy")

**What to implement:**
1. Abstract a `Workflow` definition (name, tools, phases, artifact renderers, system prompt).
2. Refactor hiring into the first registered workflow; add a **second** Track-4 workflow to
   prove generality — e.g. **"support email → quote generation"** or **"system alert →
   remediation runbook"** (both are Track-4 example scenarios) with its own 2–3 tools + HITL gate.
3. UI **workflow switcher** in the sidebar.

**Verification:** both workflows run end-to-end; registry test enumerates tools/phases per
workflow; no hiring-specific hardcoding left in the orchestrator core.

---

## Phase 5 — Frontend 10x

**What to implement (build on `app.py` + `src/ui/theme.py`):**
1. **Live streaming**: render agent tokens/steps as they arrive (`st.write_stream` /
   placeholder) instead of a blocking spinner (`app.py:206/312`).
2. **Timeline/Gantt** from checklist `due_date`/`D-30` offsets (data already exists,
   `onboarding.py`); render as a horizontal timeline, not a flat table.
3. **Cost & latency badges** per step (from Phase-1 metrics); a **tokens used** meter.
4. **Audit panel** (reviewer, timestamp, decision) + **diff view** on revise (old vs new CTC/offer).
5. **Multimodal upload** widget; **workflow switcher**; keep the SVG icon system.

**Verification:** manual UI pass + Playwright screenshots for each state (parse, streaming,
gate, timeline, complete) for the README/video.

---

## Phase 6 — Deployment + submission assets

**What to implement:**
1. **Deploy on Alibaba Cloud ECS** (Docker/compose already present): open security-group
   inbound TCP 8501; capture the public URL + a screenshot as deployment proof.
2. **Proof-of-Alibaba links** in README About/top: point at `qwen_client.py` (DashScope) and
   `oss_client.py` (OSS). Add an OSS/ECS note.
3. **Architecture diagram v2** (Mermaid) in `docs/architecture.md`: show Planner/Executor/Critic,
   RAG + embeddings, OSS/Tablestore, streaming, Qwen Cloud, UI.
4. **README** with: description, track ID (Track 4), setup, deployment proof, screenshots,
   measurable-efficiency numbers.
5. **3-min demo video** (script in `docs/DEMO_SCRIPT.md`): ambiguous input → clarification →
   multi-agent run (streamed) → critic veto/revise → human gate → OSS publish → download.
6. **CI**: GitHub Actions running `pytest` on push.
7. Optional **blog post** (journey building on Qwen Cloud) for the Blog Prize.

**Verification:** repo public + MIT license visible in About; both proof links resolve; CI green;
video < 3:30 and public.

---

## Phase 7 — Final verification

1. `pytest` all green; add tests for the Phase-1/2/3 additions and the previously-uncovered
   `_extract_tool_calls_from_text` normalizer + `MAX_TURNS` exhaustion + `qwen_client` fallback.
2. Anti-pattern grep: no `json_schema`, no missing-"json" `response_format`, no hardcoded secrets.
3. **Live smoke test on real `qwen-plus`** (not Ollama): full pipeline hits the structured
   `flag_for_approval` gate; parallel tool calls fire; streaming shows usage.
4. Demo dry-run end-to-end on ECS.

---

## Recommended execution order if time-boxed (highest ROI first)

1. **Phase 1** (structured output + streaming + metrics) — biggest depth-per-hour, unlocks the UI.
2. **Phase 2** (multi-agent critic) — the single strongest *innovation* signal.
3. **Phase 6** (ECS deploy + OSS proof + diagram + video) — required to *submit and score*.
4. **Phase 3** (RAG + audit + OSS + multimodal) — depth + problem-value.
5. **Phase 5** (frontend streaming/timeline) — presentation polish.
6. **Phase 4** (2nd workflow) — do if time remains; it converts "good project" → "platform".

> Minimum to be competitive: Phases 1 + 2 + 6. Everything else compounds the score.
