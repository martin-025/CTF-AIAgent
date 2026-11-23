"""Offline contract test: browser mode never calls JSON-backed platform."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from harness import orchestrator

class BrowserModeTest(unittest.TestCase):
    def test_browser_mode_bypasses_json_adapter(self):
        config = {"run": {"model": "test-model", "max_steps": 5,
                          "max_wall_seconds": 60},
                  "flag": {"regex": r"FGCU\{[^}]+\}"},
                  "sandbox": {"image": "mock", "network_mode": "none"}}
        result = SimpleNamespace(solved=False, steps=1, wall_seconds=0.1,
                                 input_tokens=0, output_tokens=0,
                                 submissions=[], failure_reason="gave_up",
                                 challenge_id="browser-session",
                                 challenge_name="Website-selected challenge",
                                 category="browser", flag=None)
        fake_agent_instance = MagicMock()
        fake_agent_instance.run.return_value = result
        fake_agent_factory = MagicMock(return_value=fake_agent_instance)
        fake_logger = MagicMock()
        fake_logger.run_id = "test"
        fake_logger.csv_path = "test-results.csv"
        fake_browser = MagicMock()
        fake_sandbox = MagicMock()
        with patch.dict(os.environ, {"CTF_BROWSER_MODE": "1"}), \
             patch.object(orchestrator, "load_platform") as old_adapter, \
             patch.object(orchestrator, "RunLogger", return_value=fake_logger), \
             patch.object(orchestrator, "Sandbox", return_value=fake_sandbox), \
             patch.object(orchestrator, "CTFAgent", fake_agent_factory), \
             patch("harness.browser.CTFBrowser", return_value=fake_browser):
            path = orchestrator.run(config, {}, object())
        self.assertEqual(path, "test-results.csv")
        old_adapter.assert_not_called()
        fake_browser.start.assert_called_once()
        fake_agent_instance.run.assert_called_once()
        fake_agent_factory.call_args.kwargs["browser"] is fake_browser or self.fail("Browser not passed")
        self.assertIsNone(fake_agent_factory.call_args.kwargs["platform"])
        fake_browser.close.assert_called_once()
        fake_sandbox.stop.assert_called_once()
        print("PASS: browser mode runs without querying challenge JSON or local platform adapter")

if __name__ == "__main__":
    unittest.main()
