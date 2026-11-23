"""Test the SAME browser tools used by CTFAgent without Claude, Docker, or a key.

This invokes CTFAgent._dispatch directly to verify the tool-to-Playwright wiring.
No flags are submitted and no challenge JSON is fetched.
"""
from harness.agent import CTFAgent, AgentResult
from harness.browser import CTFBrowser
from harness.platform.base import Challenge


def main():
    browser = CTFBrowser()
    try:
        browser.start()
        agent = CTFAgent(
            client=None, model="not-used", sandbox=None, platform=None,
            challenge=Challenge(id="ui-test", name="Browser UI test", category="web", description=""),
            flag_regex=r"FGCU\\{.*?\\}", max_steps=5, max_wall_seconds=60,
            browser=browser,
        )
        result = AgentResult("ui-test", "Browser UI test", "web")
        observation, _ = agent._dispatch("browser_read", {}, result)
        print("\n=== AGENT TOOL: browser_read ===\n", observation[:1200])
        if "Base Case" not in observation:
            raise RuntimeError("Base Case not visible. Navigate to the challenge list and retry.")
        observation, _ = agent._dispatch("browser_click", {"text": "Base Case"}, result)
        print("\n=== AGENT TOOL: browser_click ===\n", observation[:1800])
        if "Our network monitor intercepted" not in observation:
            raise RuntimeError("Base Case description not found after clicking.")
        print("\nPASS: The existing agent dispatcher controls the tested browser controller.")
        print("No Claude API key, Docker, JSON challenge retrieval, or flag submission was used.")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
