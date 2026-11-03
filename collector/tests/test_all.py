import os
import sys
import unittest
import datetime as dt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dates_jp import parse_target, parse_time  # noqa: E402
from extract import extract_document, merge_events, extract_page, keep_event  # noqa: E402

D = dt.date


class TestDates(unittest.TestCase):
    def test_full_date_and_time(self):
        r = parse_target("2026年11月12日 15時30分に発表予定", D(2026, 11, 3))
        self.assertEqual((r["start"], r["precision"], r["needs_review"]), ("2026-11-12", "day", False))
        self.assertEqual(r["time"], "15:30")

    def test_no_time_is_none(self):
        r = parse_target("2026年11月12日に発表予定", D(2026, 11, 3))
        self.assertIsNone(r["time"])

    def test_month_day_infers_year_and_flags(self):
        r = parse_target("11月12日に開催", D(2026, 11, 3))
        self.assertEqual(r["start"], "2026-11-12")
        self.assertTrue(r["year_inferred"])
        r = parse_target("2月10日に発表", D(2026, 11, 3))   # 半年以上前 → 翌年
        self.assertEqual(r["start"], "2027-02-10")

    def test_next_spring_resolved_when_unambiguous(self):
        r = parse_target("来春に発売予定", D(2026, 11, 3))
        self.assertEqual((r["start"], r["end"]), ("2027-03-01", "2027-05-31"))
        self.assertFalse(r["needs_review"])
        self.assertEqual(r["raw"], "来春")

    def test_next_spring_ambiguous_in_january(self):
        r = parse_target("来春に発売予定", D(2026, 1, 20))
        self.assertTrue(r["needs_review"])

    def test_bare_season_needs_review(self):
        r = parse_target("春に量産開始予定", D(2026, 11, 3))
        self.assertTrue(r["needs_review"])
        self.assertEqual(r["start"], "2027-03-01")

    def test_nendonai_needs_review_without_fy(self):
        r = parse_target("年度内に承認申請を行う予定", D(2026, 11, 3))
        self.assertTrue(r["needs_review"])
        self.assertIsNone(r["start"])
        r = parse_target("年度内に承認申請を行う予定", D(2026, 11, 3), fy_end_month=3)
        self.assertEqual(r["end"], "2027-03-31")
        self.assertFalse(r["needs_review"])

    def test_kiyo(self):
        r = parse_target("2027年3月期の業績予想", D(2026, 11, 3))
        self.assertEqual((r["start"], r["end"]), ("2026-04-01", "2027-03-31"))

    def test_wareki(self):
        r = parse_target("令和9年4月1日", D(2026, 11, 3))
        self.assertEqual(r["start"], "2027-04-01")

    def test_invalid_date(self):
        r = parse_target("2026年2月30日", D(2026, 1, 1))
        self.assertTrue(r["needs_review"])

    def test_none_when_absent(self):
        self.assertIsNone(parse_target("お知らせします。", D(2026, 1, 1)))
        self.assertIsNone(parse_time("お知らせ"))

    def test_zenkaku(self):
        r = parse_target("２０２６年１２月１日", D(2026, 11, 3))
        self.assertEqual(r["start"], "2026-12-01")


CTX = {"code": "9999", "name": "テスト株式会社", "pubdate": "2026-11-03 15:00:00", "title": "テスト",
       "url": "https://example.invalid/a.pdf", "checked_at": "2026-11-03T16:00:00+09:00", "fy_end_month": None}


class TestExtract(unittest.TestCase):
    def test_launch_and_quote_page(self):
        pages = ["お知らせ\n当社は新製品Aを2027年2月15日に発売する予定です。", "別ページ。\n来春に工場の量産開始を計画しています。"]
        ev = extract_document(pages, CTX)
        kinds = {(e["kind"], e["page"]) for e in ev}
        self.assertIn(("launch", 1), kinds)
        self.assertIn(("production", 2), kinds)
        e = [x for x in ev if x["kind"] == "launch"][0]
        self.assertEqual(e["target"]["start"], "2027-02-15")
        self.assertIn("発売", e["quote"])
        self.assertEqual(e["origin"], "official")
        self.assertEqual(e["time_text"], None)   # 書かれていない時刻は補わない

    def test_no_invented_impact(self):
        ev = extract_page("業績予想を修正します。", 1, CTX)
        self.assertTrue(all(e["impact_period"] == "記載なし" for e in ev if e["kind"] == "forecast"))

    def test_fx(self):
        ev = extract_page("想定為替レートは1ドル=150円としております。", 1, CTX)
        self.assertTrue(any(e["kind"] == "fx" for e in ev))

    def test_delay_not_inferred_from_absence(self):
        # 「見つからない」だけでは延期・中止の項目を作らない
        self.assertEqual([e for e in extract_page("新製品の発売日は未定です。", 1, CTX) if e["kind"] == "delay"], [])
        self.assertEqual(extract_page("新製品を発売します。", 1, CTX)[0]["kind"], "launch")

    def test_real_world_false_positives_rejected(self):
        """実際のIR本文(2026-11-02)で誤って拾っていた文。拾ってはいけない。"""
        bad = [
            "抗悪性腫瘍剤Poteligeoは、2020年の発売以来、上市国を拡大しながら売上収益を伸ばしています。",
            "北米市場向けに単層ビニル床シート「HITOE」を発売して教育・医療分野案件の獲得強化に取り組むなど、浸透に注力しました。",
            "AI関連を中心とした設備投資需要の拡大に加え、個人消費の持ち直しもあり、総じて底堅く推移しました。",
            "ブルームバーグによる為替レート（1米ドル＝157.57円）により計算しています。",
            "主要顧客における受注環境が好調に推移いたしました。",
            "業績予想等の将来に関する記述を常に見直して公表するとは限りません。",
            "2026年11月2日 決算説明会資料",
            "(2)受注実績当中間連結会計期間における受注実績は、以下のとおりです。",
            "自社株買いなどによる自己資本の圧縮によりROEは0.1%改善",
            "機動的な株主還元の手段として自己株式の取得を実施し、総還元性向40～50％を目指す",
            "配当支払開始予定日2026年12月1日決算補足説明資料作成の有無:有決算説明会開催の有無:有（機関投資家・アナリスト向け）",
            "金融負債の認識の中止日の明確化（IFRS第9号の改訂）",
            "海外の事業環境の変化を踏まえた販売計画の見直しにより、下半期の売上高は減少します。",
        ]
        for s in bad:
            self.assertEqual(extract_page(s, 1, dict(CTX, title="決算説明会資料")), [], s)

    def test_real_world_true_positives_kept(self):
        good = {
            "launch": "新製品Aを2027年2月に発売する予定です。",
            "production": "新工場において2027年4月に量産を開始する予定です。",
            "fx": "業績予想の前提となる想定為替レートは1米ドル=150円としております。",
            "delay": "発売時期を2027年6月に延期いたします。",
            "buyback": "自己株式の取得に係る事項の内容は以下のとおりです。取得期間は2026年11月4日から2027年3月31日まで。",
            "earnings": "決算発表日は2026年11月12日の15時30分を予定しております。",
        }
        for k, s in good.items():
            self.assertIn(k, [e["kind"] for e in extract_page(s, 1, CTX)], s)

    def test_reference_dates_are_not_schedules(self):
        ev = extract_page("前回予想（2026年5月11日公表）から業績予想を修正します。", 1, CTX)
        self.assertTrue(ev and all(e["target"] is None for e in ev))
        ev = extract_page("2026年4月1日に自己株式の取得を決議しました。", 1, CTX)
        self.assertTrue(all(e["target"] is None for e in ev))

    def test_disclaimer_skipped(self):
        self.assertEqual(extract_page("将来の見通しに関する記載は、中止や延期のリスクや不確実性を含みます。", 1, CTX), [])

    def test_dedupe_and_history(self):
        pages = ["新製品を2027年2月15日に発売する予定です。"]
        a = extract_document(pages, CTX)
        merged, added, upd = merge_events([], a)
        self.assertEqual((added, upd), (len(a), 0))
        merged, added, upd = merge_events(merged, extract_document(pages, CTX))
        self.assertEqual((added, upd), (0, 0))
        self.assertEqual(len(merged), len(a))

    def test_history_on_change(self):
        a = extract_document(["新製品を2027年2月15日に発売する予定です。"], CTX)
        merged, _, _ = merge_events([], a)
        b = [dict(a[0], target_text="X", checked_at="later")]
        merged, _, upd = merge_events(merged, b)
        self.assertEqual(upd, 1)
        self.assertEqual(len(merged[0]["history"]), 1)

    def test_forecast_compare_item_rows_verified(self):
        txt = "前回発表予想（A） 修正後（B）\n売上高 100,000 110,000 10,000 10.0%\n営業利益 5,000 6,500 1,400 28.0%"
        rows = [e for e in extract_document([txt], CTX) if e["kind"] == "forecast_item"]
        by = {r["item"]: r for r in rows}
        self.assertEqual((by["売上高"]["prev"], by["売上高"]["new"], by["売上高"]["diff"]), ("100,000", "110,000", 10000.0))
        self.assertTrue(by["売上高"]["verified"])
        self.assertFalse(by["営業利益"]["verified"])      # 差額が計算と合わない → 要確認のまま
        self.assertTrue(by["営業利益"]["needs_review"])

    def test_forecast_compare_column_layout(self):
        txt = "2．業績予想の修正\n売上高 営業利益 経常利益\n前回発表予想（A） 500,000 40,000 41,000\n今回修正予想（B） 520,000 45,000 46,000\n"
        rows = [e for e in extract_document([txt], CTX) if e["kind"] == "forecast_item"]
        got = {r["item"]: (r["prev"], r["new"]) for r in rows}
        self.assertEqual(got.get("営業利益"), ("40,000", "45,000"))
        self.assertEqual(got.get("売上高"), ("500,000", "520,000"))

    def test_forecast_rows(self):
        txt = "前回発表予想（A） 修正後（B）\n売上高 100,000 110,000\n営業利益 5,000 6,500"
        ev = extract_document([txt], CTX)
        rows = [e for e in ev if e["kind"] == "forecast_item"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["needs_review"] for r in rows))


class TestRetention(unittest.TestCase):
    cutoff, today = "2026-09-04", "2026-11-03"

    def ev(self, kind, ann, target):
        return {"kind": kind, "announced_at": ann + " 15:00:00", "target": target}

    def test_recent_kept(self):
        self.assertTrue(keep_event(self.ev("forecast", "2026-10-30", None), self.cutoff, self.today))

    def test_old_without_future_dropped(self):
        self.assertFalse(keep_event(self.ev("launch", "2026-05-01", None), self.cutoff, self.today))
        past = {"start": "2026-06-01", "end": "2026-06-01"}
        self.assertFalse(keep_event(self.ev("launch", "2026-05-01", past), self.cutoff, self.today))

    def test_old_future_plan_kept(self):
        fut = {"start": "2027-03-01", "end": "2027-05-31", "precision": "season"}
        self.assertTrue(keep_event(self.ev("launch", "2026-05-01", fut), self.cutoff, self.today))
        self.assertTrue(keep_event(self.ev("production", "2026-01-10", {"start": "2026-12-01", "end": "2026-12-01"}), self.cutoff, self.today))

    def test_unresolved_period_kept_one_year(self):
        un = {"start": None, "end": None, "needs_review": True}
        self.assertTrue(keep_event(self.ev("development", "2026-02-01", un), self.cutoff, self.today))
        self.assertFalse(keep_event(self.ev("development", "2025-09-01", un), self.cutoff, self.today))


if __name__ == "__main__":
    unittest.main()
