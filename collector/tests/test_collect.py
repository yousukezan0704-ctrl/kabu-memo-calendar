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


class TestXbrlRevision(unittest.TestCase):
    def rec(self, direction):
        return {"direction": direction, "scope": "連結", "period": "通期", "items": [
            {"item": "sales", "prev": 21884, "new": 21884, "diff": 0, "diff_pct": 0.0, "diff_source": "XBRL"},
            {"item": "operating_income", "prev": 6825, "new": 6425, "diff": -400, "diff_pct": -5.9, "diff_source": "XBRL"},
            {"item": "eps", "prev": 119.30, "new": 115.45, "diff": -3.85, "diff_pct": None, "diff_source": "計算"}]}

    def v(self):
        return {"id": "9", "code": "1234", "name": "テスト", "pubdate": "2026-11-02 15:30:00",
                "title": "業績予想の修正に関するお知らせ", "url": "https://example.invalid/x.pdf"}

    def test_down_event_and_rows(self):
        ev = collect.xbrl_revision_events(self.rec("down"), self.v(), "2026-11-05T10:00:00+09:00")
        self.assertEqual(ev[0]["kind"], "revision_down")
        self.assertTrue(ev[0]["confirmed"])
        self.assertIn("6,825→6,425", ev[0]["summary"])
        rows = {e["item"]: e for e in ev[1:]}
        self.assertEqual(rows["営業利益"]["prev"], "6,825")
        self.assertEqual(rows["営業利益"]["diff"], -400)
        self.assertTrue(rows["営業利益"]["verified"])
        self.assertEqual(rows["1株当たり当期純利益"]["new"], "115.45")
        self.assertEqual(len({e["id"] for e in ev}), len(ev))

    def test_mixed_is_not_up_or_down(self):
        ev = collect.xbrl_revision_events(self.rec("mixed"), self.v(), "x")
        self.assertEqual(ev[0]["kind"], "forecast")
        ev = collect.xbrl_revision_events(self.rec(None), self.v(), "x")
        self.assertEqual(ev[0]["kind"], "forecast")

    def test_other_periods_and_dividend_rows(self):
        rec = self.rec("up")
        rec["other_periods"] = [{"scope": "連結", "period": "第2四半期累計", "direction": "up", "items": [
            {"item": "ordinary_income", "prev": 45000, "new": 59500, "diff": 14500, "diff_pct": 32.2, "diff_source": "XBRL"}]}]
        rec["dividend"] = {"q2": {"prev": 75, "new": 95}, "year_end": {"prev": 7.5, "new": 9.5}}
        ev = collect.xbrl_revision_events(rec, self.v(), "x")
        periods = {(e.get("item"), e["impact_period"]) for e in ev if e["kind"] == "forecast_item"}
        self.assertIn(("経常利益", "第2四半期累計"), periods)
        div = {e["id"]: e for e in ev if e["id"].startswith("xrvd:")}
        self.assertEqual(len(div), 2)
        self.assertTrue(all(e["needs_review"] for e in div.values()))  # 桁が大きく違うので要確認
        self.assertEqual(len({e["id"] for e in ev}), len(ev))


if __name__ == "__main__":
    unittest.main()
