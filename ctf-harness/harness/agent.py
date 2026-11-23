"""
A minimal ReAct agent (thought -> action -> observation) driven by Claude's
tool-use API. Small on purpose: you can read the whole loop and explain every
line in your report.

The agent gets exactly three tools and nothing else:
  * run_command  — run a shell command in the isolated sandbox
  * submit_flag  — submit a candidate flag; the PLATFORM judges correctness
  * give_up      — stop and explain why

It has no web-search / retrieval tool, and the sandbox network policy blocks the
open internet, so it must solve from the challenge itself — the "no outside
materials" requirement, enforced two ways at once.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .flags import find_flags
from .platform.base import Challenge, CTFPlatform
from .sandbox import Sandbox

MAX_OBS_CHARS = 6000  # truncate tool output so one noisy command can't blow the context

TOOLS = [
    {
        "name": "run_command",
        "description": (
            "Run a bash command inside the isolated analysis sandbox. Returns the "
            "combined stdout/stderr and exit code. Challenge files are in the "
            "working directory. There is NO internet access."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to run."}
            },
            "required": ["command"],
        },
    },
    {
        "name": "submit_flag",
        "description": (
            "Submit a candidate flag to the CTF platform for grading. Use this the "
            "moment you believe you have the flag. Returns whether it was correct."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "flag": {"type": "string", "description": "The exact flag string."}
            },
            "required": ["flag"],
        },
    },
    {
        "name": "give_up",
        "description": "Abandon this challenge. Only call this when genuinely stuck.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why you are stuck."}
            },
            "required": ["reason"],
        },
    },
]


BROWSER_TOOLS = [
    {
        "name": "browser_read",
        "description": "Read the text currently visible in the FGCU CTF browser window.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_click",
        "description": "Click a visible text label, such as a challenge title, in the FGCU CTF browser window.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Exact visible text to click."}},
            "required": ["text"],
        },
    },
]


@dataclass
class AgentResult:
    challenge_id: str
    challenge_name: str
    category: str
    solved: bool = False
    flag: str | None = None
    steps: int = 0
    wall_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    failure_reason: str | None = None
    submissions: list[str] = field(default_factory=list)


def _system_prompt(ch: Challenge, flag_regex: str) -> str:
    conn = f"\nConnection: {ch.connection_info}" if ch.connection_info else ""
    files = ("\nFiles (already in your working directory): "
             + ", ".join(f.split("/")[-1] for f in ch.files)) if ch.files else ""
    return f"""You are an expert CTF player solving one challenge autonomously.

Challenge: {ch.name}
Category: {ch.category}{conn}{files}

Description:
{ch.description}

Rules:
- Work only with the tools provided and the files in the sandbox. You have no
  internet access and cannot look up write-ups — solve it yourself.
- The flag is wrapped like {flag_regex} — e.g. FGCU{{the_answer}}. When the
  challenge asks for a word, password, or value, wrap that answer in FGCU{{...}}.
- submit_flag is checked instantly and for free, so submit the moment you have a
  candidate. If it's rejected, try formatting variants before giving up:
  wrap/unwrap FGCU{{...}}, change capitalization, swap spaces for underscores.
- Any hints in the description may be imprecise or wrong — verify by testing
  (e.g. brute-force all cipher shifts rather than trusting a stated shift).
- Investigate step by step: inspect files, form a hypothesis, test it, iterate.
- Call give_up only if you are truly stuck after real attempts."""


class CTFAgent:
    def __init__(
        self,
        client: Any,
        model: str,
        sandbox: Sandbox,
        platform: CTFPlatform,
        challenge: Challenge,
        flag_regex: str,
        max_steps: int,
        max_wall_seconds: int,
        on_event: Callable[[str, dict], None] | None = None,
        browser: Any = None,
    ):
        self.client = client
        self.model = model
        self.sandbox = sandbox
        self.platform = platform
        self.ch = challenge
        self.flag_regex = flag_regex
        self.max_steps = max_steps
        self.max_wall_seconds = max_wall_seconds
        self.on_event = on_event or (lambda *_: None)
        self.browser = browser

    def _dispatch(self, name: str, args: dict, result: AgentResult) -> tuple[str, bool]:
        """Run one tool. Returns (observation_text, should_stop)."""
        if name == "browser_read" and self.browser is not None:
            obs = self.browser.read_page()
            self.on_event("observation", {"text": obs})
            return obs, False

        if name == "browser_click" and self.browser is not None:
            obs = self.browser.click_text(args.get("text", ""))
            self.on_event("action", {"tool": "browser_click", "text": args.get("text", "")})
            self.on_event("observation", {"text": obs})
            return obs, False

        if name in ("browser_read", "browser_click") and self.browser is None:
            return "Browser unavailable; cannot perform " + name, False

        if name == "run_command":
            cmd = args.get("command", "")
            self.on_event("action", {"tool": "run_command", "command": cmd})
            code, out = self.sandbox.exec(cmd)
            if len(out) > MAX_OBS_CHARS:
                out = out[:MAX_OBS_CHARS] + "\n...[output truncated]"
            obs = f"(exit {code})\n{out}"
            # Opportunistic catch: a flag may show up in command output.
            hits = find_flags(out, self.flag_regex)
            if hits:
                obs += f"\n[harness] A string matching the flag format appeared: {hits[0]}"
            self.on_event("observation", {"text": obs})
            return obs, False

        if name == "submit_flag":
            flag = args.get("flag", "").strip()
            result.submissions.append(flag)
            self.on_event("action", {"tool": "submit_flag", "flag": flag})
            if self.browser is not None:
                # In browser mode, the website judges the submission, not the
                # JSON-backed platform adapter. Unknown feedback is not success.
                feedback = self.browser.submit_flag(flag)
                status = feedback.get("status", "unknown")
                if status == "accepted":
                    result.solved = True
                    result.flag = flag
                    self.on_event("result", {"correct": True, "source": "website"})
                    return "ACCEPTED by website UI: " + str(feedback.get("after_text", ""))[-800:], True
                if status == "rejected":
                    self.on_event("result", {"correct": False, "source": "website"})
                    return "REJECTED by website UI: " + str(feedback.get("after_text", ""))[-800:], False
                self.on_event("result", {"correct": None, "source": "website"})
                return "UNKNOWN website feedback. Do not assume success. Page: " + str(feedback.get("after_text", ""))[-800:], False

            correct = self.platform.submit_flag(self.ch, flag)
            if correct:
                result.solved = True
                result.flag = flag
                self.on_event("result", {"correct": True, "flag": flag})
                return f"CORRECT — '{flag}' accepted by the platform.", True
            self.on_event("result", {"correct": False, "flag": flag})
            return f"INCORRECT — '{flag}' was rejected. Keep going.", False

        if name == "give_up":
            reason = args.get("reason", "")
            result.failure_reason = f"gave_up: {reason}"
            self.on_event("action", {"tool": "give_up", "reason": reason})
            return "Acknowledged.", True

        return f"Unknown tool: {name}", False

    def run(self) -> AgentResult:
        result = AgentResult(self.ch.id, self.ch.name, self.ch.category)
        messages: list[dict] = [
            {"role": "user", "content": "Begin by inspecting the browser page." if self.browser is not None else "Begin. Start by inspecting what you have."}
        ]
        if self.browser is not None:
            # Browser-only research mode: do not give challenge descriptions from JSON.
            system = ("You are an AI competitor navigating the authorized FGCU Talon CTF website. "
                      "Read the visible webpage with browser_read, select challenges using "
                      "browser_click, and reason from only what is visible in the UI and "
                      "any approved local analysis tools. Never inspect answer hashes or "
                      "the challenge JSON to obtain solutions. You may use run_command "
                      "for offline analysis. Submit a candidate through submit_flag only "
                      "when you intend to make an actual attempt; attempts are recorded. "
                      "The website is the grader. If a response is UNKNOWN, do not treat "
                      "it as correct. Do not use external network access. You may give_up "
                      "if stuck. Begin by inspecting the visible webpage.")
            available_tools = BROWSER_TOOLS + TOOLS
        else:
            system = _system_prompt(self.ch, self.flag_regex)
            available_tools = TOOLS
        start = time.time()

        for step in range(1, self.max_steps + 1):
            if time.time() - start > self.max_wall_seconds:
                result.failure_reason = "time_budget_exhausted"
                break
            result.steps = step

            resp = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                tools=available_tools,
                messages=messages,
            )
            result.input_tokens += resp.usage.input_tokens
            result.output_tokens += resp.usage.output_tokens

            # Log any text the model produced (its "thought").
            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    self.on_event("thought", {"text": block.text.strip()})

            messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason != "tool_use":
                # Model stopped without acting. One nudge, then give up.
                self.on_event("note", {"text": "model stopped without a tool call"})
                result.failure_reason = "model_stopped"
                break

            tool_results = []
            stop = False
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                obs, should_stop = self._dispatch(block.name, block.input, result)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": obs}
                )
                stop = stop or should_stop
            messages.append({"role": "user", "content": tool_results})

            if stop:
                break
        else:
            result.failure_reason = result.failure_reason or "step_budget_exhausted"

        result.wall_seconds = round(time.time() - start, 1)
        if not result.solved and not result.failure_reason:
            result.failure_reason = "unsolved"
        return result
