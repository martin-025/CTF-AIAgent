"""Offline tests for attachment link selection; no site or API access."""
import unittest
from unittest.mock import MagicMock
from harness.platform.browser_ctf import BrowserCTF


class AttachmentTests(unittest.TestCase):
    def test_asset_filtering(self):
        ctl = BrowserCTF()
        ctl.page = MagicMock()
        ctl.page.url = "https://jolly-grass-0486f7a10.3.azurestaticapps.net/dashboard"
        allowed = MagicMock()
        allowed.is_visible.return_value = True
        allowed.get_attribute.side_effect = lambda name: "assets/magicinme" if name == "href" else None
        allowed.inner_text.return_value = "Download magicinme unknown file"
        blocked = MagicMock()
        blocked.is_visible.return_value = True
        blocked.get_attribute.side_effect = lambda name: "https://other.example/test" if name == "href" else None
        blocked.inner_text.return_value = "External URL"
        ctl.page.locator.return_value.all.return_value = [allowed, blocked]
        found = ctl.list_attachments()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["label"], "Download magicinme unknown file")

    def test_missing_label_does_not_download(self):
        ctl = BrowserCTF()
        ctl.list_attachments = lambda: []
        with self.assertRaises(ValueError):
            ctl.download_attachment("missing")


if __name__ == "__main__":
    unittest.main()
