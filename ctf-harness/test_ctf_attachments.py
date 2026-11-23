"""Live UI attachment smoke test (no Claude, Docker, JSON or flag submission).

Run from ctf-harness: python test_ctf_attachments.py
"""
from pathlib import Path
from harness.platform.browser_ctf import BrowserCTF


def main():
    with BrowserCTF() as ctf:
        print("Sign in and leave the browser on the challenge dashboard.")
        input("Press Enter once the challenge list is visible...")

        details = ctf.open_challenge("Unknown File")
        assert "Unknown File" in details["visible_text"], "Unexpected challenge page"
        print("\nPASS: Opened Unknown File through the website")

        attachments = ctf.list_attachments()
        print("\nVisible same-site challenge attachments:")
        for attachment in attachments:
            print(" -", attachment["label"], "=>", attachment["href"])

        if not attachments:
            print("No downloadable /assets/ link found. Check the displayed UI and report this output.")
            return

        label = next((a["label"] for a in attachments if "magicinme" in a["label"].lower()), None)
        if not label:
            print("Couldn't identify magicinme from visible attachment labels; no download attempted.")
            return

        result = ctf.download_attachment(label, Path("browser_artifacts") / "attachments")
        print("\nPASS: Downloaded attachment via browser UI")
        print("File:", result["path"])
        print("Size:", result["bytes"], "bytes")
        print("Note: file was downloaded but not executed or copied into Docker.")
        input("\nPress Enter to close browser...")


if __name__ == "__main__":
    main()
