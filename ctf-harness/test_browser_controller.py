"""Stand-alone integration test: no Claude, Docker or JSON needed.

Run from ctf-harness directory: python test_browser_controller.py
Optional real submission: python test_browser_controller.py --submit-test
"""
import argparse
from pathlib import Path
from harness.platform.browser_ctf import BrowserCTF


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit-test", action="store_true", help="Submit ONE incorrect flag to your authorized account")
    args = parser.parse_args()

    with BrowserCTF() as ctf:
        print("Browser opened. Log in and navigate to the challenge LIST.")
        input("Do NOT open Base Case yourself. Press Enter when the list is visible...")
        print("\n[1] Reading challenge list via UI")
        print(ctf.read_page()["visible_text"][:1200])

        print("\n[2] Opening Base Case via reusable controller")
        current = ctf.open_challenge("Base Case")
        assert "Our network monitor intercepted" in current["visible_text"], (
            "Base Case description not found after click"
        )
        print("PASS: Controller opened and read Base Case from the website")
        print(current["visible_text"][:1200])
        print("Screenshot:", ctf.screenshot(Path("browser_artifacts") / "controller_base_case.png"))

        if args.submit_test:
            answer = input("Type YES to make one real incorrect submission: ")
            if answer == "YES":
                result = ctf.submit_flag("FGCU{test_submission}")
                print("Result status:", result["status"])
                print("Response page:\n", result["after_text"][:1800])
                print("Screenshot:", ctf.screenshot(Path("browser_artifacts") / "controller_submission.png"))

        input("\nPress Enter to close the browser...")


if __name__ == "__main__":
    main()
