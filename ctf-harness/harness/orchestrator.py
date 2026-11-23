"""
The orchestrator: the top-level harness loop.

For each selected challenge it spins up a fresh isolated sandbox, stages the
challenge files, runs the agent under a budget, records the result, and tears
the sandbox down. This is the "harness" your project is really about.
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

from .agent import CTFAgent
from .logging_utils import RunLogger
from .platform.base import Challenge, load_platform
from .sandbox import Sandbox


def select_challenges(challenges: list[Challenge], run_cfg: dict) -> list[Challenge]:
    cats = run_cfg.get("categories")
    out = challenges
    if cats:
        cats = {c.lower() for c in cats}
        out = [c for c in out if c.category.lower() in cats]
    limit = run_cfg.get("max_challenges")
    if limit:
        out = out[: int(limit)]
    return out


def _stage_files(platform: Any, ch: Challenge, sandbox: Sandbox, tmp: str) -> None:
    for url in ch.files:
        name = url.split("/")[-1].split("?")[0] or "file"
        local = os.path.join(tmp, name)
        try:
            platform.download_file(url, local)
            sandbox.put_file(local, name)
            print(f"    staged {name}")
        except Exception as exc:  # noqa: BLE001 - keep going, log the miss
            print(f"    [warn] could not stage {url}: {exc}")


def run(cfg: dict, secrets: dict, client: Any, run_id: str | None = None) -> str:
    run_cfg = cfg["run"]
    logger = RunLogger("results", "logs", run_id)
    print(f"Run: {logger.run_id}")

    if os.environ.get("CTF_BROWSER_MODE") == "1":
        return _run_browser_session(cfg, client, logger)

    platform = load_platform(cfg, secrets)
    print("Logging in to platform…")
    platform.login()

    print("Fetching challenge list…")
    challenges = platform.list_challenges()
    chosen = select_challenges(challenges, run_cfg)
    print(f"{len(challenges)} challenges available; attempting {len(chosen)}.\n")

    solved = 0
    for i, ch in enumerate(chosen, 1):
        print(f"[{i}/{len(chosen)}] {ch.short()}")
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Sandbox(cfg)
            try:
                sandbox.start()
                _stage_files(platform, ch, sandbox, tmp)
                agent = CTFAgent(
                    client=client,
                    model=run_cfg["model"],
                    sandbox=sandbox,
                    platform=platform,
                    challenge=ch,
                    flag_regex=cfg["flag"]["regex"],
                    max_steps=int(run_cfg["max_steps"]),
                    max_wall_seconds=int(run_cfg["max_wall_seconds"]),
                    on_event=logger.event_sink(ch.id),
                )
                result = agent.run()
            finally:
                sandbox.stop()

        logger.write_result(
            result,
            float(run_cfg.get("price_per_mtok_input", 0) or 0),
            float(run_cfg.get("price_per_mtok_output", 0) or 0),
        )
        status = "SOLVED" if result.solved else f"unsolved ({result.failure_reason})"
        solved += int(result.solved)
        print(f"    => {status}  [{result.steps} steps, {result.wall_seconds}s, "
              f"{result.input_tokens + result.output_tokens} tok]\n")

    print(f"Done. Solved {solved}/{len(chosen)}. Results: {logger.csv_path}")
    return logger.csv_path


def _run_browser_session(cfg: dict, client: Any, logger: RunLogger) -> str:
    """One website-first AI session. No challenge JSON or local grading.

    This is an integration test, not yet a per-challenge evaluation run.
    """
    from .browser import CTFBrowser

    run_cfg = cfg["run"]
    browser = CTFBrowser()
    sandbox = Sandbox(cfg)
    # Placeholder metadata only. The agent receives the actual challenge
    # descriptions through browser_read, not through this object.
    session = Challenge(
        id="browser-session", name="Website-selected challenge",
        category="browser", description="",
    )
    try:
        browser.start()  # User signs in; browser remains on challenge dashboard.
        sandbox.start()
        agent = CTFAgent(
            client=client, model=run_cfg["model"], sandbox=sandbox,
            platform=None,  # Browser mode NEVER calls the JSON-backed grader.
            challenge=session, flag_regex=cfg["flag"]["regex"],
            max_steps=int(run_cfg["max_steps"]),
            max_wall_seconds=int(run_cfg["max_wall_seconds"]),
            on_event=logger.event_sink(session.id), browser=browser,
        )
        result = agent.run()
        logger.write_result(
            result,
            float(run_cfg.get("price_per_mtok_input", 0) or 0),
            float(run_cfg.get("price_per_mtok_output", 0) or 0),
        )
        print(f"Browser session finished: solved={result.solved}; "
              f"steps={result.steps}; results={logger.csv_path}")
        return logger.csv_path
    finally:
        sandbox.stop()
        browser.close()
