"""Adapter between the team's existing Claude browser tools and the tested BrowserCTF.

This module performs only user-visible UI actions. It never fetches challenge
JSON or uses locally stored answer hashes to grade submissions.
"""
from __future__ import annotations

from .platform.browser_ctf import BrowserCTF


class CTFBrowser:
    def __init__(self):
        self.controller = BrowserCTF()

    def start(self):
        self.controller.start()
        print("Log into the CTF and navigate to the challenge list in the opened browser.")
        input("Press Enter here when the challenge list is visible...")

    def read_page(self) -> str:
        data = self.controller.read_page()
        return f"URL: {data['url']}\nPAGE: {data['title']}\nVISIBLE TEXT:\n{data['visible_text']}"

    def click_text(self, text: str) -> str:
        try:
            data = self.controller.click_text(text)
            return (f"Clicked: {text}\nURL: {data['url']}\n"
                    f"VISIBLE TEXT:\n{data['visible_text']}")
        except Exception as exc:
            return f"CLICK FAILED: {type(exc).__name__}: {str(exc)[:350]}"

    def submit_flag(self, flag: str) -> dict:
        """Real submission; call only when the instructor permits test attempts."""
        return self.controller.submit_flag(flag)

    def close(self):
        self.controller.close()
