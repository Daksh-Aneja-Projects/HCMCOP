"""HCM Autopilot orchestrator.

Drives the end-to-end hiring workflow using Qwen Cloud function calling. The
orchestrator is designed to be *resumable*: because Streamlit re-runs the whole
script on every interaction and the workflow contains a human-in-the-loop
pause, the agent loop runs "until it needs a human", returns control, and can
be resumed by feeding the human's response back in.

Public surface used by the Streamlit app:

    orch = Orchestrator(today="2026-07-19")
    state = orch.start("Hire a senior backend dev in Bangalore ...")
    # state.status in {"awaiting_clarification", "awaiting_approval",
    #                   "complete", "error"}
    orch.submit_clarification("Engineering dept, start Aug 15")
    orch.submit_approval("approved")            # or ("revise", "cap CTC at 30L")

All LLM calls go through ``src.utils.qwen_client`` -> Qwen Cloud.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from types import SimpleNamespace
from typing import Any

from ..tools.approval import flag_for_approval
from ..tools.compliance import check_geo_compliance
from ..tools.ctc_estimator import estimate_ctc_band
from ..tools.offer_letter import generate_offer_letter
from ..tools.onboarding import create_onboarding_checklist
from ..tools.parse_request import parse_hiring_request
from ..utils.qwen_client import chat_completion


class Status(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETE = "complete"
    ERROR = "error"


# Workflow phases surfaced to the UI's status tracker.
PHASES = [
    "Request Parsing",
    "Compliance Check",
    "CTC Estimation",
    "Offer Draft",
    "Human Approval",
    "Onboarding Checklist",
    "Complete",
]


@dataclass
class StepLog:
    """One tool invocation, for the UI's reasoning/expander display."""

    tool: str
    arguments: dict[str, Any]
    result: Any
    reasoning: str = ""


@dataclass
class AgentState:
    status: Status = Status.IDLE
    phase: str = PHASES[0]
    steps: list[StepLog] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    assistant_message: str = ""  # latest natural-language message (question/summary)
    approval_summary: dict[str, Any] | None = None
    error: str | None = None


_SYSTEM_PROMPT = """You are HCM Autopilot, an autonomous Human Capital \
Management agent for enterprise hiring operations. You turn an ambiguous hiring \
request into a complete, compliant onboarding package.

You have these tools:
1. parse_hiring_request  - extract structured fields from the raw request.
2. check_geo_compliance  - statutory requirements for a country/state.
3. estimate_ctc_band     - indicative salary band for role/level/location.
4. generate_offer_letter - draft the offer letter.
5. create_onboarding_checklist - sequenced onboarding tasks.
6. flag_for_approval     - MANDATORY human-in-the-loop gate.

Follow this workflow strictly:
- STEP 1: Always call parse_hiring_request first.
- ONLY 'role' and 'location' are critical. If (and only if) the parsed result \
has needs_clarification=true, STOP and reply in plain text asking the user for \
those missing critical fields. Do not guess a role or country.
- NEVER ask about level, department, or start date. Infer them and continue \
(e.g. "Senior" in the job title means level = Senior; a missing department is \
fine). If role and location are both present, proceed through the ENTIRE tool \
pipeline without asking any questions.
- Once the critical fields are known, call check_geo_compliance, then \
estimate_ctc_band, then generate_offer_letter (in that order).
- Then call flag_for_approval with a concise summary. This PAUSES for a human. \
Do not call create_onboarding_checklist before approval.
- After the human APPROVES, call create_onboarding_checklist, then give a short \
final confirmation message.
- If the human asks to REVISE (e.g. "cap CTC at 30L"), re-run the affected \
tools (e.g. estimate_ctc_band with the new constraint, then \
generate_offer_letter) and call flag_for_approval again.

Be concise. When you call a tool, briefly state why in your message content. \
Never fabricate compliance or salary numbers — always use the tools."""


# JSON-schema tool definitions handed to Qwen for function calling.
def _tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "parse_hiring_request",
                "description": "Extract structured hiring details (role, level, department, location, start date, employment type) from ambiguous natural-language input. Always call this first.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "raw_request": {
                            "type": "string",
                            "description": "The full raw hiring request text (including any clarifications the user has provided).",
                        }
                    },
                    "required": ["raw_request"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_geo_compliance",
                "description": "Return statutory HR/compliance requirements for a geography (notice period, probation, mandatory benefits, required documents, statutory filings, risk flags).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {"type": "string"},
                        "state": {"type": "string", "description": "State/region if applicable."},
                        "employment_type": {"type": "string", "description": "e.g. Full-time, Contract."},
                    },
                    "required": ["country"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "estimate_ctc_band",
                "description": "Return an indicative annual CTC salary band for a role, level and location. Optionally clamp to max_ctc when the user imposes a cap.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "level": {"type": "string"},
                        "location": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"},
                                "state": {"type": "string"},
                                "country": {"type": "string"},
                            },
                        },
                        "max_ctc": {
                            "type": "number",
                            "description": "Optional hard cap on total CTC in local currency.",
                        },
                    },
                    "required": ["role", "level", "location"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_offer_letter",
                "description": "Draft a structured offer letter. Uses the already-computed parsed request, compliance and CTC results, so you only need to optionally pass a candidate name and reporting manager.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "candidate_name": {"type": "string"},
                        "reporting_to": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "flag_for_approval",
                "description": "Human-in-the-loop checkpoint. Pauses the workflow and presents a summary for explicit human approval before the final package is generated. Call after the offer letter is drafted.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "note": {
                            "type": "string",
                            "description": "Optional short note to the reviewer about what to check.",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_onboarding_checklist",
                "description": "Generate the sequenced onboarding checklist with owners and deadlines. Only call this AFTER a human has approved at the flag_for_approval checkpoint.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


# Maps a phase to the tool that, once run, marks that phase reached.
_TOOL_PHASE = {
    "parse_hiring_request": "Compliance Check",
    "check_geo_compliance": "CTC Estimation",
    "estimate_ctc_band": "Offer Draft",
    "generate_offer_letter": "Human Approval",
    "create_onboarding_checklist": "Complete",
}


class Orchestrator:
    """Stateful, resumable agent loop."""

    MAX_TURNS = 12

    def __init__(self, today: str | None = None):
        self.today = today
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT}
        ]
        self.state = AgentState()
        self._pending_approval_call_id: str | None = None
        self._approved: bool = False
        self._raw_request: str = ""

    # -- public API ---------------------------------------------------------

    def start(self, raw_request: str) -> AgentState:
        self._raw_request = raw_request
        content = raw_request
        if self.today:
            content = f"(Today is {self.today}.)\n\n{raw_request}"
        self.messages.append({"role": "user", "content": content})
        return self._run()

    def submit_clarification(self, text: str) -> AgentState:
        # Append to the running request context so the parser sees the full picture.
        self._raw_request = f"{self._raw_request}\n\nAdditional details: {text}"
        self.messages.append({"role": "user", "content": text})
        return self._run()

    def submit_approval(self, decision: str, notes: str = "") -> AgentState:
        """Resume after the human-in-the-loop checkpoint.

        Args:
            decision: "approved" or "revise".
            notes: revision notes when decision == "revise".
        """
        if self._pending_approval_call_id is None:
            # Nothing was waiting; ignore defensively.
            return self.state

        if decision == "approved":
            self._approved = True
            payload = {"decision": "approved", "notes": notes or None}
        else:
            self._approved = False
            payload = {"decision": "revise", "notes": notes or "Please revise."}

        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": self._pending_approval_call_id,
                "content": json.dumps(payload),
            }
        )
        self._pending_approval_call_id = None
        self.state.approval_summary = None
        return self._run()

    # -- core loop ----------------------------------------------------------

    def _run(self) -> AgentState:
        self.state.status = Status.RUNNING
        self.state.error = None
        try:
            for _ in range(self.MAX_TURNS):
                response = chat_completion(
                    messages=self.messages,
                    tools=_tool_specs(),
                    tool_choice="auto",
                    temperature=0.2,
                )
                message = response.choices[0].message
                # Some local/OSS models (e.g. Ollama-served) return tool calls as
                # text instead of the structured field; normalize both shapes.
                tool_calls = _normalize_tool_calls(message, _VALID_TOOL_NAMES)
                extracted = bool(tool_calls) and not getattr(message, "tool_calls", None)
                self._append_assistant(message, tool_calls, hide_content=extracted)

                if not tool_calls:
                    # Plain text: either a clarification question or a final message.
                    self.state.assistant_message = message.content or ""
                    if "checklist" in self.state.artifacts and self._approved:
                        self.state.status = Status.COMPLETE
                        self.state.phase = "Complete"
                    else:
                        self.state.status = Status.AWAITING_CLARIFICATION
                    return self.state

                reasoning = (message.content or "").strip()
                paused = self._handle_tool_calls(tool_calls, reasoning)
                if paused:
                    return self.state
                # else: continue the loop with tool results appended.

            # Exceeded MAX_TURNS.
            self.state.status = Status.ERROR
            self.state.error = "Agent exceeded the maximum number of reasoning turns."
            return self.state
        except Exception as exc:  # surface a friendly error to the UI
            self.state.status = Status.ERROR
            self.state.error = f"{type(exc).__name__}: {exc}"
            return self.state

    def _handle_tool_calls(self, tool_calls: list[Any], reasoning: str) -> bool:
        """Execute a batch of tool calls. Returns True if we paused for approval."""
        pending_approval: Any | None = None

        for call in tool_calls:
            name = call.function.name
            args = _safe_args(call.function.arguments)

            if name == "flag_for_approval":
                # Execute the gate, append its result, but PAUSE before the next
                # model turn to collect the human's decision.
                summary = self._build_approval_summary(args.get("note"))
                result = flag_for_approval(summary)
                self._log_step(name, args, result, reasoning)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )
                self.state.approval_summary = summary
                self.state.phase = "Human Approval"
                self._pending_approval_call_id = call.id
                pending_approval = call
                continue

            result = self._dispatch(name, args)
            self._log_step(name, args, result, reasoning)
            self._record_artifact(name, result)
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                }
            )
            if name in _TOOL_PHASE:
                self.state.phase = _TOOL_PHASE[name]

        if pending_approval is not None:
            self.state.status = Status.AWAITING_APPROVAL
            return True
        return False

    # -- tool dispatch ------------------------------------------------------

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        parsed = self.state.artifacts.get("parsed_request", {})
        if name == "parse_hiring_request":
            raw = args.get("raw_request") or self._raw_request
            return parse_hiring_request(raw, today=self.today)

        if name == "check_geo_compliance":
            location = parsed.get("location") or {}
            country = args.get("country") or location.get("country") or ""
            state = args.get("state") or location.get("state")
            emp = args.get("employment_type") or parsed.get("employment_type") or "Full-time"
            return check_geo_compliance(country=country, state=state, employment_type=emp)

        if name == "estimate_ctc_band":
            role = args.get("role") or parsed.get("role") or ""
            level = args.get("level") or parsed.get("level") or "Mid"
            location = args.get("location") or parsed.get("location") or {}
            max_ctc = args.get("max_ctc")
            return estimate_ctc_band(role=role, level=level, location=location, max_ctc=max_ctc)

        if name == "generate_offer_letter":
            return generate_offer_letter(
                parsed_request=parsed,
                compliance=self.state.artifacts.get("compliance", {}),
                ctc=self.state.artifacts.get("ctc", {}),
                candidate_name=args.get("candidate_name"),
                reporting_to=args.get("reporting_to"),
            )

        if name == "create_onboarding_checklist":
            return create_onboarding_checklist(
                parsed_request=parsed,
                compliance=self.state.artifacts.get("compliance", {}),
                start_date=parsed.get("start_date"),
            )

        return {"error": f"Unknown tool: {name}"}

    def _record_artifact(self, name: str, result: Any) -> None:
        key = {
            "parse_hiring_request": "parsed_request",
            "check_geo_compliance": "compliance",
            "estimate_ctc_band": "ctc",
            "generate_offer_letter": "offer_letter",
            "create_onboarding_checklist": "checklist",
        }.get(name)
        if key:
            self.state.artifacts[key] = result

    def _build_approval_summary(self, note: str | None) -> dict[str, Any]:
        art = self.state.artifacts
        offer = art.get("offer_letter", {})
        ctc = art.get("ctc", {})
        summary = {
            "role": (art.get("parsed_request") or {}).get("role"),
            "location": (art.get("parsed_request") or {}).get("location"),
            "start_date": (art.get("parsed_request") or {}).get("start_date"),
            "ctc_band": {
                "low": ctc.get("band_low"),
                "mid": ctc.get("band_mid"),
                "high": ctc.get("band_high"),
                "currency": ctc.get("currency"),
            },
            "offer_key_terms": offer.get("key_terms"),
            "compliance_risk_flags": (art.get("compliance") or {}).get("risk_flags", []),
        }
        if note:
            summary["reviewer_note"] = note
        return summary

    # -- bookkeeping --------------------------------------------------------

    def _append_assistant(
        self, message: Any, tool_calls: list[Any], hide_content: bool = False
    ) -> None:
        """Append the assistant message to history, preserving tool_calls.

        ``tool_calls`` is the normalized list (may be synthesized from text).
        ``hide_content`` blanks the raw content when the tool call was extracted
        from text, so the model doesn't re-read the raw JSON on the next turn.
        """
        content = "" if hide_content else (message.content or "")
        entry: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        self.messages.append(entry)

    def _log_step(self, tool: str, args: dict[str, Any], result: Any, reasoning: str) -> None:
        self.state.steps.append(
            StepLog(tool=tool, arguments=args, result=result, reasoning=reasoning)
        )

    # -- export -------------------------------------------------------------

    def build_package(self) -> dict[str, Any]:
        """Assemble the final onboarding package from collected artifacts."""
        art = self.state.artifacts
        return {
            "hiring_request": {
                "raw": self._raw_request,
                "parsed": art.get("parsed_request"),
            },
            "compliance_summary": art.get("compliance"),
            "ctc_breakdown": art.get("ctc"),
            "offer_letter": art.get("offer_letter"),
            "onboarding_checklist": art.get("checklist"),
            "approved": self._approved,
        }


def _safe_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


# Convenience for callers/tests that want to enumerate available tools.
def available_tool_names() -> list[str]:
    return [spec["function"]["name"] for spec in _tool_specs()]


_VALID_TOOL_NAMES = set(available_tool_names())


def _normalize_tool_calls(message: Any, valid_names: set[str]) -> list[Any]:
    """Return tool calls from a message, whether structured or emitted as text.

    Cloud Qwen returns a proper ``tool_calls`` field. Some local/OSS models
    served via Ollama instead put the tool call in ``content`` as JSON or inside
    ``<tool_call>...</tool_call>`` tags. This bridges both.
    """
    real = getattr(message, "tool_calls", None)
    if real:
        return list(real)
    return _extract_tool_calls_from_text(message.content or "", valid_names)


def _extract_tool_calls_from_text(text: str, valid_names: set[str]) -> list[Any]:
    raw_objs: list[dict[str, Any]] = []

    # 1) <tool_call>{...}</tool_call> blocks (Qwen chat template style).
    for block in re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL):
        obj = _try_json(block)
        if isinstance(obj, dict):
            raw_objs.append(obj)

    # 2) Otherwise treat the whole (de-fenced) content as JSON.
    if not raw_objs:
        c = text.strip()
        if c.startswith("```"):
            c = c.strip("`")
            if c[:4].lower() == "json":
                c = c[4:]
            c = c.strip()
        obj = _try_json(c)
        if isinstance(obj, list):
            raw_objs = [o for o in obj if isinstance(o, dict)]
        elif isinstance(obj, dict):
            raw_objs = [obj]

    calls: list[Any] = []
    for i, o in enumerate(raw_objs):
        fn = o.get("function") if isinstance(o.get("function"), dict) else {}
        name = o.get("name") or o.get("tool") or fn.get("name")
        args = o.get("arguments")
        if args is None:
            args = o.get("parameters")
        if args is None:
            args = fn.get("arguments")
        if not name or name not in valid_names:
            continue
        if args is None:
            args = {}
        calls.append(_mk_call(f"call_local_{i}_{name}", name, args))
    return calls


def _mk_call(call_id: str, name: str, args: Any) -> Any:
    arguments = args if isinstance(args, str) else json.dumps(args)
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _try_json(s: str) -> Any:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        for open_c, close_c in (("{", "}"), ("[", "]")):
            a, b = s.find(open_c), s.rfind(close_c)
            if a != -1 and b > a:
                try:
                    return json.loads(s[a : b + 1])
                except json.JSONDecodeError:
                    continue
    return None
