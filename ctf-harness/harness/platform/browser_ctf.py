"""Reusable, UI-only browser controller for the authorized FGCU Talon CTF.

No direct /data/challenges.json requests, no answer-hash inspection, no AI/API key.
The caller decides which challenge/flag to use.
"""
from __future__ import annotations

import re
import uuid
from urllib.parse import urljoin, urlparse
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Playwright, Browser, BrowserContext, sync_playwright

CTF_URL = "https://jolly-grass-0486f7a10.3.azurestaticapps.net/"


class BrowserCTF:
    def __init__(self, url: str = CTF_URL):
        self.url = url
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def __enter__(self) -> "BrowserCTF":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def start(self) -> None:
        if self.page:
            raise RuntimeError("Browser already started")
        self.playwright = sync_playwright().start()
        try:
            self.browser = self.playwright.chromium.launch(headless=False)
            self.context = self.browser.new_context(accept_downloads=True)
            self.page = self.context.new_page()
            self.page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            self.close()
            raise

    def _page(self) -> Page:
        if self.page is None:
            raise RuntimeError("Call start() or use 'with BrowserCTF() as ctf' first")
        return self.page

    def read_page(self, max_chars: int = 6000) -> dict[str, str]:
        page = self._page()
        return {
            "url": page.url,
            "title": page.title(),
            "visible_text": page.locator("body").inner_text(timeout=15000)[:max_chars],
        }

    def click_text(self, label: str) -> dict[str, str]:
        """Click an exact visible label. Useful for challenges and Back controls."""
        if not label or len(label) > 200:
            raise ValueError("label must be 1-200 characters")
        self._page().get_by_text(label, exact=True).first.click(timeout=15000)
        return self.read_page()

    def open_challenge(self, title: str) -> dict[str, str]:
        return self.click_text(title)

    def list_attachments(self) -> list[dict[str, str]]:
        """Discover downloadable challenge assets from visible links, not JSON.

        Only same-site /assets/ links are considered challenge attachments.
        External resource URLs are deliberately excluded from file downloads.
        """
        page = self._page()
        origin = urlparse(self.url)
        attachments: list[dict[str, str]] = []
        for link in page.locator("a[href]").all():
            if not link.is_visible():
                continue
            href = link.get_attribute("href") or ""
            absolute = urljoin(page.url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in ("http", "https"):
                continue
            if parsed.netloc != origin.netloc or not parsed.path.startswith("/assets/"):
                continue
            label = link.inner_text().strip() or link.get_attribute("download") or ""
            if label:
                attachments.append({"label": label, "href": href})
        return attachments

    def download_attachment(
        self,
        label: str,
        destination_dir: str | Path = "browser_artifacts/attachments",
        max_bytes: int = 20 * 1024 * 1024,
    ) -> dict[str, Any]:
        """Click a visible, same-site attachment link and save its bytes.

        Does not execute files, bypass the UI, or transfer them to the sandbox.
        The caller must explicitly approve sandbox import separately.
        """
        if not label or len(label) > 200:
            raise ValueError("attachment label must be 1-200 characters")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")

        matches = [a for a in self.list_attachments() if a["label"] == label]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one visible asset link labelled {label!r}; found {len(matches)}")
        page = self._page()
        link = page.get_by_role("link", name=label, exact=True)
        if link.count() != 1:
            raise ValueError("Attachment link is ambiguous in the page")
        with page.expect_download(timeout=15000) as download_info:
            link.click(timeout=15000)
        download = download_info.value
        if download.failure():
            raise RuntimeError(f"Browser download failed: {download.failure()}")

        # Strip directory components from a browser-supplied filename.
        suggested = download.suggested_filename.replace("\\", "/").split("/")[-1]
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", suggested).strip(".")
        if not safe_name or safe_name in (".", ".."):
            safe_name = "attachment.bin"
        output_dir = Path(destination_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
        download.save_as(output)
        size = output.stat().st_size
        if size > max_bytes:
            output.unlink(missing_ok=True)
            raise ValueError(f"Downloaded file exceeds {max_bytes} byte limit")
        return {
            "label": label,
            "filename": safe_name,
            "path": str(output.resolve()),
            "bytes": size,
        }

    def submit_flag(self, flag: str) -> dict[str, Any]:
        """Submit through the visible UI; never infer correctness from hashes.

        Only use with permission. Calling this makes an actual attempt on the
        currently open challenge, which may affect a real account's counters.
        """
        if not flag or len(flag) > 500:
            raise ValueError("flag must be 1-500 characters")
        page = self._page()
        before = page.locator("body").inner_text()
        # This selector worked in the user's manual Playwright submission test.
        page.get_by_role("textbox").last.fill(flag)
        page.get_by_role("button", name="Submit", exact=True).click(timeout=15000)
        try:
            page.wait_for_function(
                "previous => document.body.innerText !== previous",
                arg=before,
                timeout=5000,
            )
        except Exception:
            pass  # Feedback may be subtle or unchanged; don't invent a result.
        after = page.locator("body").inner_text(timeout=15000)
        # Classification is a best-effort convenience, not authoritative grading.
        lower = after.lower()
        if re.search(r"incorrect flag|wrong flag|flag rejected|try again", lower):
            status = "rejected"
        elif re.search(r"correct flag|flag accepted|challenge solved|congratulations", lower):
            status = "accepted"
        else:
            status = "unknown"
        return {
            "status": status,
            "before_text": before[:2000],
            "after_text": after[:6000],
            "url": page.url,
        }

    def screenshot(self, path: str | Path) -> str:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self._page().screenshot(path=str(output), full_page=True)
        return str(output.resolve())

    def close(self) -> None:
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
        finally:
            if self.playwright:
                self.playwright.stop()
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
