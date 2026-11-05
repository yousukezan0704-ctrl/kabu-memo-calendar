"""collect.py の小さな判定部分のテスト(通信はしない)。"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import collect  # noqa: E402


class TestSkipAndPdf(unittest.TestCase):
    def test_buyback_status_not_skipped_but_charter_change_is(self):
        t1 = "自己株式の取得状況に関するお知らせ（会社法第165条第2項の規定による定款の定めに基づく自己株式の取得）"
        t2 = "会社分割による持株会社体制への移行及び定款の一部変更に関するお知らせ"
        self.assertFalse(collect.SKIP_TITLE.search(t1))
        self.assertTrue(collect.SKIP_TITLE.search(t2))
        self.assertTrue(collect.SKIP_TITLE.search("役員報酬の減額に関するお知らせ"))

    def test_truncated_pdf_retried_then_error(self):
        with mock.patch.object(collect, "http_get", return_value=b"%PDF-1.6 abc"), \
                mock.patch.object(collect.time, "sleep"):
            with self.assertRaises(IOError):
                collect.fetch_pdf("https://example.invalid/a.pdf")

    def test_truncated_then_complete_pdf_ok(self):
        seq = [b"%PDF-1.6 abc", b"%PDF-1.6 abc\n%%EOF\n"]
        with mock.patch.object(collect, "http_get", side_effect=seq), mock.patch.object(collect.time, "sleep"):
            self.assertTrue(collect.fetch_pdf("https://example.invalid/a.pdf").endswith(b"%%EOF\n"))

    def test_image_event_is_unconfirmed_and_has_no_numbers(self):
        v = {"id": "9", "code": "1234", "name": "テスト", "pubdate": "2026-11-02 15:00:00",
             "title": "業績予想の修正に関するお知らせ", "url": "https://example.invalid/x.pdf"}
        e = collect.make_image_event(v, "2026-11-05T10:00:00+09:00")
        self.assertFalse(e["confirmed"])
        self.assertTrue(e["needs_review"])
        self.assertIsNone(e["target"]["start"])
        self.assertIn("自動で読めていません", e["summary"])
        self.assertTrue(collect.IMPORTANT_IMG.search(v["title"]))
        self.assertFalse(collect.IMPORTANT_IMG.search("貸借取引貸付金・貸付有価証券等の平均残高のお知らせ"))


if __name__ == "__main__":
    unittest.main()
