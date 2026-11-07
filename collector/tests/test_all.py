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


def _items(txt, ctx=CTX):
    return {(r["item"]): r for r in extract_document([txt], ctx) if r["kind"] == "forecast_item"}


class TestYenSen(unittest.TestCase):
    """配当の「14円00銭」を 14 と 00 に割らない。列は 決定額(今回)/直近の配当予想(前回)/前期実績。"""

    def test_komatsu_matere_3580(self):   # 実際のIR(2026-11-02)の原文
        txt = ("決 定 額 直近の配当予想 （2026 年５月13 日公表） 前期実績 （2026 年３月期） \n"
               "基準日 2026 年9 月 30 日 2026 年9 月30 日 2025 年9 月30 日 \n"
               "１株当たり配当金 14 円00 銭 13 円00 銭 14 円00 銭 \n配当金総額 522 百万円 － 549 百万円 ")
        r = _items(txt)["1株当たり配当金"]
        self.assertEqual((r["prev"], r["new"], r["diff"]), ("13円00銭", "14円00銭", 1.0))
        self.assertTrue(r["verified"])

    def test_nichidai_6467(self):
        txt = "決定額 直近の配当予想（2026年５月１日） 前期実績（2026年３月期）\n基準日 2026年９月30日 同左 2025年９月30日\n１株当たり配当金 ４円00銭 ２円00銭 ２円00銭\n"
        r = _items(txt)["1株当たり配当金"]
        self.assertEqual((r["prev"], r["new"], r["diff"]), ("2円00銭", "4円00銭", 2.0))

    def test_header_split_over_lines_7480(self):
        txt = ("（１）剰余金の配当（中間配当）の内容\n決定額\n直近の配当予想\n（2026年８月３日発表）\n前期実績\n（2026年３月期）\n"
               "基 準 日 2026年９月30日 同 左 2025年９月30日\n１株当たり配当金 99円 86円 36円\n配 当 金 の 総 額 1,277百万円 ― 464百万円\n")
        r = _items(txt)["1株当たり配当金"]
        self.assertEqual((r["prev"], r["new"]), ("86円", "99円"))

    def test_dividend_without_column_header_is_not_registered(self):
        self.assertEqual(_items("１株当たり配当金 14円00銭 13円00銭 14円00銭\n前回発表予想\n"), {})

    def test_dividend_before_after_rows(self):   # 「前回予想/今回修正予想」の行形式(構造は実IRと同じ、数値は例)
        txt = "1株当たり配当金 第2四半期末 期末 合計\n前回予想 （2026年5月14日公表）8円00銭 16円00銭 24円00銭\n今回修正予想 9円00銭 17円00銭 26円00銭\n"
        got = _items(txt)
        self.assertEqual(got["1株当たり配当金(期末)"]["prev"], "16円00銭")
        self.assertEqual(got["1株当たり配当金(期末)"]["new"], "17円00銭")
        self.assertEqual(got["1株当たり配当金(合計)"]["diff"], 2.0)


class TestForecastTables(unittest.TestCase):
    def test_range_forecast_keeps_both_ends_7366(self):
        txt = ("売上収益 営業利益 親会社の所有者に帰属する当期利益 1株当たり当期利益\n"
               "前回発表予想（A） 百万円44,000 百万円5,500 百万円3,300 円 銭95.82\n"
               "今回修正予想（B） 45,500～46,000 5,800～6,300 3,500～3,900 102.12～113.79\n"
               "増減額（B-A） 1,500～2,000 300～800 200～600 -\n増減率（％） 3.4～4.5 5.5～14.5 6.1～18.2 -\n")
        g = _items(txt)
        self.assertEqual((g["売上収益"]["prev"], g["売上収益"]["new"]), ("44,000", "45,500～46,000"))
        self.assertEqual((g["営業利益"]["prev"], g["営業利益"]["new"]), ("5,500", "5,800～6,300"))
        self.assertTrue(g["営業利益"]["verified"])
        self.assertEqual(g["1株当たり当期利益"]["new"], "102.12～113.79")
        self.assertFalse(g["1株当たり当期利益"]["verified"])

    def test_verified_by_diff_row_9044(self):
        txt = ("営 業 収 益 営 業 利 益 経 常 利 益 親会社株主に帰属す る 当 期 純 利 益\n"
               "前回発表予想（Ａ） 百万円287,500 百万円40,000 百万円35,900 百万円23,800\n"
               "今回発表予想（Ｂ） 288,800 40,000 35,400 23,800\n増   減   額（Ｂ－Ａ） 1,300 0 △500 0\n")
        g = _items(txt)
        self.assertEqual((g["営業収益"]["prev"], g["営業収益"]["new"]), ("287,500", "288,800"))
        self.assertTrue(all(r["verified"] for r in g.values()))

    def test_interim_and_full_year_have_period_2806(self):
        txt = ("2027 年3 月期第 2 四半期(中間期)業績予想数値の修正（2026 年 4 月 1 日～2026 年 9 月 30 日）\n"
               " 売 上 高 営業利益 経常利益 中間純利益 １株当たり 中間純利益 \n"
               "前 回 発 表 予 想 （Ａ） 百万円 8,000 百万円 65 百万円 130 百万円 120 円 銭 17.27 \n"
               "今 回 修 正 予 想 （Ｂ） 8,313 △67 24 45 6.48 \n増 減 額 （Ｂ－Ａ） 313 △132 △105 △75 \n"
               "（ ご 参 考 ） 前 期 実 績 \n（2026 年 3 月期第 2 四半期） 7,285 430 526 375 54.03 \n"
               "2027 年3 月期 通期業績予想数値の修正（2026 年 4 月 1 日～2027 年 3 月31 日）\n"
               " 売 上 高 営業利益 経常利益 当期純利益 １株当たり 当期純利益 \n"
               "前 回 発 表 予 想 （Ａ） 百万円 15,900 百万円 10 百万円 111 百万円 107 円 銭 15.40 \n"
               "今 回 修 正 予 想 （Ｂ） 15,957 △304 △177 △160 △23.03 \n増 減 額 （Ｂ－Ａ） 57 △314 △288 △267 \n")
        rows = [e for e in extract_document([txt], CTX) if e["kind"] == "forecast_item" and e["item"] == "営業利益"]
        by = {r["prev"]: r for r in rows}
        self.assertIn("中間期", by["65"]["impact_period"])
        self.assertIn("通期", by["10"]["impact_period"])
        self.assertEqual(by["10"]["new"], "△304")
        self.assertTrue(by["10"]["verified"])

    def test_sentence_with_year_is_not_a_table_row_1870(self):
        txt = "前回発表予想 修正後\n（注1）売上高、営業利益、経常利益及び親会社株主に帰属する当期純利益については、2026 年8月7日に公表した予想を修正しました。"
        self.assertEqual(_items(txt), {})

    def test_ratio_table_is_not_forecast_7236(self):
        txt = "前回予想 修正後\n売上高 77,511 100 82,268 100 4,757 6.1 168,000 100\n営業利益 5,393 7.0 5,576 6.8 183 3.4 11,900 7.1\n"
        self.assertEqual(_items(txt), {})

    def test_unchanged_rows_not_registered(self):
        # 前回と今回が同じ値は「修正」ではないので登録しない(住友化学4005の「60,000 60,000 -」、南海9044の営業利益)
        self.assertEqual(_items("前回発表予想 修正後\n売上収益 60,000 60,000 -\n"), {})
        txt = ("営 業 収 益 営 業 利 益 経 常 利 益 親会社株主に帰属す る 当 期 純 利 益\n"
               "前回発表予想（Ａ） 百万円287,500 百万円40,000 百万円35,900 百万円23,800\n"
               "今回発表予想（Ｂ） 288,800 40,000 35,400 23,800\n増   減   額（Ｂ－Ａ） 1,300 0 △500 0\n")
        self.assertEqual(sorted(_items(txt)), ["営業収益", "経常利益"])

    def test_same_item_many_rows_not_verified_4005(self):
        txt = ("前回発表予想 修正後\nアグロ＆ライフ\n売上収益 560,000 570,000 10,000\n"
               "ICT\n売上収益 590,000 610,000 20,000\n合計\n売上収益 2,360,000 2,490,000 130,000\n")
        rows = [e for e in extract_document([txt], CTX) if e["kind"] == "forecast_item"]
        self.assertEqual(len(rows), 3)
        self.assertFalse(any(r["verified"] for r in rows))
        self.assertEqual(rows[0]["section"], "アグロ＆ライフ")

    def test_subsidiary_document_flagged(self):
        txt = "前回発表予想 修正後\n売上高 100 110 10\n"
        ctx = dict(CTX, title="連結子会社（ユタカフーズ株式会社）の業績予想の修正に関するお知らせ")
        rows = extract_document([txt], ctx)
        self.assertTrue(rows)
        for r in rows:
            self.assertTrue(r["needs_review"])
            self.assertIn("子会社", r["note"])


class TestEarningsDate(unittest.TestCase):
    def test_time_formats(self):
        self.assertEqual(parse_time("午後3時30分から"), "15:30")
        self.assertEqual(parse_time("10時半開始"), "10:30")
        self.assertEqual(parse_time("15時00分"), "15:00")
        self.assertEqual(parse_time("開始 15:00～16:00"), "15:00")
        self.assertIsNone(parse_time("約3時間を予定"))
        self.assertIsNone(parse_time("9月30日15時点の残高"))

    def test_next_earnings_date_with_time(self):
        ev = extract_page("次回決算発表予定日は2027年2月5日（金）15時00分です。", 1, CTX)
        e = [x for x in ev if x["kind"] == "earnings"][0]
        self.assertEqual((e["target"]["start"], e["time_text"]), ("2027-02-05", "15:00"))

    def test_setsumeikai_datetime(self):
        ev = extract_page("決算説明会 開催日時 2026年11月13日（金） 午後4時30分～", 1, CTX)
        e = [x for x in ev if x["kind"] == "earnings"][0]
        self.assertEqual((e["target"]["start"], e["time_text"]), ("2026-11-13", "16:30"))

    def test_no_time_written_stays_none(self):
        ev = extract_page("決算発表日は2026年11月12日です。", 1, CTX)
        e = [x for x in ev if x["kind"] == "earnings"][0]
        self.assertEqual(e["target"]["start"], "2026-11-12")
        self.assertIsNone(e["time_text"])

    def test_time_of_another_date_not_borrowed(self):
        ev = extract_page("決算発表予定日は2026年11月12日、決算説明会は2026年11月13日15時00分です。", 1, CTX)
        e = [x for x in ev if x["kind"] == "earnings" and x["target"]["start"] == "2026-11-12"][0]
        self.assertIsNone(e["time_text"])

    def test_past_date_and_undated_not_registered(self):
        self.assertEqual([x for x in extract_page("前回の決算発表日は2026年8月7日でした。", 1, CTX) if x["kind"] == "earnings"], [])
        s = ("上期(単位:百万円)下期速報開示について当社は、決算期日の翌日から決算発表日までの一定期間を沈黙期間としておりますが、"
             "投資家の皆様に対し当社業績に関するリアルタイムでの情報提供を行うことを目的とし、月次の個別売上高が判明した時点で、速報")
        self.assertEqual(extract_page(s, 1, dict(CTX, title="2027年3月期10月度売上高推移速報についてのお知らせ （個別）")), [])


class TestFalsePositivesV6(unittest.TestCase):
    """検証レポート(2026-11-03)などで誤りと確認された原文。拾ってはいけない。"""

    def test_rejected(self):
        bad = [
            ("2026年9月長崎諫早工場第1工場竣工資源調達リスクと環境負荷低減への取り組み名称京セラ株式会社長崎諫早工場投資金額2028.3期までに約680億円投資予定", "決算説明会資料"),
            ("製品の構成、提供開始時期、料金、販売体制などの詳細な計画は、決定次第改めてお知らせいたします。", "お知らせ"),
            ("具体的には、AI学習支援ツール「AI BOAT」の提供開始をはじめ、生成AI活用の方針策定から実務への導入・定着までを支援するコンサルティングサービスの提供を開始するなど、", "決算短信"),
            ("2026/10/15ロックウェルオートメーションのクラウド型MES「PLEX」の販売を開始 2026/10/13日本デジタル分散型金融協会への参画を通じ、発展を目指す", "決算説明資料"),
            ("新規施設の稼働開始•新規事業開発も積極的に実施予定•期末配当予想は20円。", "決算説明資料"),
            ("ご利用に応じた列車運行体制の適正化及びCBM（状態基準保全）に対応した新型車両の導入などの大規模な設備投資を計画しております。", "決算短信"),
            ("為替レート変動（円安）の影響額売上高約+630億円/税引前利益約+120億円為替の影響を除いた場合:前年同期比増収増益", "決算説明会資料"),
            ("平均為替レート（変更なし）米ドル:155円、ユーロ:180円為替の影響を除いた場合", "決算説明会資料"),
            ("為替影響と鶏肉原料価格の高騰により減益△4△11FY2027/3上期事業利益", "決算説明資料"),
            ("本件につきましては、適時開示の要否に関する確認が十分でなかったことにより、開示が遅延いたしました。", "お知らせ"),
            ("また、有用な薬効を確認できない場合や副作用など安全性への懸念が生じた場合研究開発の延長や中止の判断が行われるなど、研究開発には不確実性が存在します。", "事業計画及び成長可能性に関する事項について"),
            ("責任追及等の訴えを提起することを請求するものです。遅延損害金の支払いを求める", "お知らせ"),
            ("加えて、医薬品の上市までには開発の失敗や遅延のリスクを伴います。", "決算説明資料"),
            ("2026年5月1日開催の取締役会において、自己株式の取得を決議し、2026年9月18日に取得を終了いたしました。", "業績予想の修正に関するお知らせ"),
            ("また、自動車業界においては、北米市場が堅調に推移し、通期の販売見通しが上方修正されるなど、良好な市場環境が継続いたしました。", "決算短信"),
        ]
        for s, title in bad:
            ev = extract_page(s, 1, dict(CTX, title=title))
            self.assertEqual([e["kind"] for e in ev], [], s[:30])

    def test_buyback_status_report_not_a_plan(self):
        s = "2026年8月3日開催の取締役会における決議内容 （2）取得する株式の総数:4,000万株を上限とする"
        self.assertEqual(extract_page(s, 1, dict(CTX, title="自己株式の取得状況に関するお知らせ")), [])
        self.assertIn("buyback", [e["kind"] for e in extract_page(s, 1, dict(CTX, title="自己株式取得に係る事項の決定に関するお知らせ"))])

    def test_kyocera_future_production_is_found(self):
        ev = extract_page("長崎諫早工場では2027年春より本格的に生産を開始します。", 1, CTX)
        e = [x for x in ev if x["kind"] == "production"][0]
        self.assertEqual((e["target"]["start"], e["target"]["precision"]), ("2027-03-01", "season"))

    def test_real_schedule_change_kept(self):
        ev = extract_page("本共同持株会社の成立日（本株式移転の効力発生日）の変更に伴う本経営統合のスケジュールの変更は、以下のとおりです。", 1, CTX)
        self.assertIn("delay", [e["kind"] for e in ev])
        ev = extract_page("完工時期が大幅に遅れる見通しであるとの連絡を受けました。", 1, CTX)
        self.assertIn("delay", [e["kind"] for e in ev])

    def test_title_quote_reference_not_alliance(self):
        s = "2025年10月8日付当社プレスリリース「SBI証券との業務提携を通じた投資事業への参入」をご参照ください。"
        self.assertEqual([e for e in extract_page(s, 1, CTX) if e["kind"] == "alliance"], [])


class TestV7(unittest.TestCase):
    """rule-v7: 検証レポート(rule-v6 再検証)の指摘。実際の原文で確認。"""

    def test_fullwidth_dot_dividend_2551(self):
        txt = ("１．配当の内容\n 決定額 直近の配当予想 （2025 年11 月４日） 前期実績 （2025 年９月期） \n"
               "基 準 日 2026 年９月20 日 2026 年９月20 日  2025 年９月20 日 \n"
               "１株当たり配当金   円  銭 ４０．００  円  銭 ３０．００  円   銭  ５０．００ \n配 当 金 総 額 89 百万円 ― 112 百万円 \n")
        r = _items(txt)["1株当たり配当金"]
        self.assertEqual((r["prev"], r["new"], r["diff"]), ("30円00銭", "40円00銭", 10.0))

    def test_period_and_unit_kept(self):
        txt = ("2027 年3 月期第 2 四半期(中間期)業績予想数値の修正（2026 年 4 月 1 日～2026 年 9 月 30 日）\n"
               " 売 上 高 営業利益 経常利益 中間純利益 １株当たり 中間純利益 \n"
               "前 回 発 表 予 想 （Ａ） 百万円 8,000 百万円 65 百万円 130 百万円 120 円 銭 17.27 \n"
               "今 回 修 正 予 想 （Ｂ） 8,313 △67 24 45 6.48 \n増 減 額 （Ｂ－Ａ） 313 △132 △105 △75 \n"
               "2027 年3 月期 通期業績予想数値の修正（2026 年 4 月 1 日～2027 年 3 月31 日）\n"
               " 売 上 高 営業利益 経常利益 当期純利益 １株当たり 当期純利益 \n"
               "前 回 発 表 予 想 （Ａ） 百万円 15,900 百万円 10 百万円 111 百万円 107 円 銭 15.40 \n"
               "今 回 修 正 予 想 （Ｂ） 15,957 △304 △177 △160 △23.03 \n増 減 額 （Ｂ－Ａ） 57 △314 △288 △267 \n")
        rows = [e for e in extract_document([txt], CTX) if e["kind"] == "forecast_item" and e["item"] == "売上高"]
        self.assertEqual([(r["impact_period"].split()[-1], r["unit"], r["verified"]) for r in rows],
                         [("中間期", "百万円", True), ("通期", "百万円", True)])
        self.assertIn("[中間期]", rows[0]["summary"])
        self.assertIn("8,000百万円", rows[0]["summary"])

    def test_same_item_same_period_twice_not_verified(self):
        t = ("2027年3月期通期業績予想数値の修正\n売上高 営業利益\n前回発表予想（Ａ） 百万円100 百万円10\n今回修正予想（Ｂ） 110 12\n増減額（Ｂ－Ａ） 10 2\n")
        rows = [e for e in extract_document([t + t], dict(CTX)) if e["kind"] == "forecast_item"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not r["verified"] for r in rows))

    def test_table_derived_revision_up_6467(self):
        txt = ("３．2027年３月期通期連結業績予想数値の修正（2026年４月１日～2027年３月31日）\n（単位：百万円）\n"
               "売上高 営業利益 経常利益\n親会社株主\nに帰属する\n当期純利益\n１株当たり\n当期純利益\n"
               "前回発表予想（Ａ） 11,650 150 63 10 １円11銭\n今回修正予想（Ｂ） 12,600 454 417 402 44円43銭\n"
               "増減額（Ｂ－Ａ） 950 304 354 392\n増減率（％） 8.2 202.7 561.9 ―\n")
        ctx = dict(CTX, title="業績予想及び配当予想の修正に関するお知らせ")
        ev = extract_document([txt], ctx)
        g = {e["item"]: e for e in ev if e["kind"] == "forecast_item"}
        self.assertEqual((g["営業利益"]["prev"], g["営業利益"]["new"]), ("150", "454"))
        self.assertEqual(g["1株当たり当期純利益"]["new"], "44円43銭")
        up = [e for e in ev if e["kind"] == "revision_up"]
        self.assertEqual(len(up), 1)
        self.assertIn("表の数値", up[0]["summary"])

    def test_table_derived_revision_down_two_periods_2806(self):
        txt = ("2027 年3 月期第 2 四半期(中間期)業績予想数値の修正（2026 年 4 月 1 日～2026 年 9 月 30 日）\n"
               " 売 上 高 営業利益 経常利益 中間純利益 １株当たり 中間純利益 \n"
               "前 回 発 表 予 想 （Ａ） 百万円 8,000 百万円 65 百万円 130 百万円 120 円 銭 17.27 \n"
               "今 回 修 正 予 想 （Ｂ） 8,313 △67 24 45 6.48 \n増 減 額 （Ｂ－Ａ） 313 △132 △105 △75 \n"
               "2027 年3 月期 通期業績予想数値の修正（2026 年 4 月 1 日～2027 年 3 月31 日）\n"
               " 売 上 高 営業利益 経常利益 当期純利益 １株当たり 当期純利益 \n"
               "前 回 発 表 予 想 （Ａ） 百万円 15,900 百万円 10 百万円 111 百万円 107 円 銭 15.40 \n"
               "今 回 修 正 予 想 （Ｂ） 15,957 △304 △177 △160 △23.03 \n増 減 額 （Ｂ－Ａ） 57 △314 △288 △267 \n")
        ctx = dict(CTX, title="業績予想の修正に関するお知らせ")
        down = [e for e in extract_document([txt], ctx) if e["kind"] == "revision_down"]
        self.assertEqual(sorted(e["impact_period"].split()[-1] for e in down), ["中間期", "通期"])

    def test_mixed_direction_gives_no_table_revision(self):
        txt = ("売上高 営業利益 経常利益\n前回発表予想（Ａ） 百万円100 百万円10 百万円10\n今回修正予想（Ｂ） 110 12 8\n増減額（Ｂ－Ａ） 10 2 △2\n")
        ctx = dict(CTX, title="業績予想の修正に関するお知らせ")
        self.assertEqual([e for e in extract_document([txt], ctx) if e["kind"] in ("revision_up", "revision_down")], [])

    def test_unit_oku_8053(self):
        txt = "前回発表予想 修正後\n親会社の所有者に帰属する当期利益 6,300億円 6,700億円 400億円 6.3％\n"
        r = _items(txt)["親会社の所有者に帰属する当期利益"]
        self.assertEqual((r["unit"], r["verified"]), ("億円", True))
        self.assertIn("6,300億円", r["summary"])

    def test_adjustment_table_is_not_revision_7162(self):
        s = ("営業収益が1,268百万円押し下げられている点を考慮（当該金額を加算）すると、其々1,268百万円上方修正"
             "営業収益が69百万円押し下げられている点を考慮（当該金額を加算）すると、其々69百万円上方修正")
        self.assertEqual([e for e in extract_page(s, 1, dict(CTX, title="決算説明資料")) if e["kind"] == "revision_up"], [])
        s = "取引による一時的な影響を考慮した実質ベースでは、営業収益及びセグメント損益はそれぞれ1,268百万円上方修正され、114百万円のセグメント損失"
        self.assertEqual([e for e in extract_page(s, 1, dict(CTX, title="決算説明資料")) if e["kind"] == "revision_up"], [])

    def test_already_launched_is_not_plan_5187(self):
        s = "上期で新製品2品目の発売をしており、従来品の拡販とあわせて販売を強化する計画"
        self.assertEqual([e for e in extract_page(s, 8, dict(CTX, title="決算説明資料")) if e["kind"] == "launch"], [])

    def test_facility_opening_is_not_mass_production_7366(self):
        s = "海外事業は当面ネブラスカ州で強度行動障害者向けサービス拡大・ラインナップ強化を進める、新規施設の稼働開始•新規事業開発も積極的に実施予定"
        self.assertEqual([e for e in extract_page(s, 25, dict(CTX, title="決算説明資料")) if e["kind"] == "production"], [])

    def test_completed_subsidiary_not_alliance_3580(self):
        s = "当社は2026年8月に株式会社ユニフの全株式を取得し子会社化し、連結の範囲に含めております。"
        self.assertEqual([e for e in extract_page(s, 4, CTX) if e["kind"] == "alliance"], [])

    def test_kyocera_production_after_completed_event_6971(self):
        # 実際のページ(2026-10-30)。同じ文に「竣工」(完了済み)と「2027年春より本格的に生産を開始」(予定)が並ぶ
        s = ("決算ハイライト｜最近のトピック2026年9月長崎諫早工場第1工場竣工資源調達リスクと環境負荷低減への取り組み名称京セラ株式会社長崎諫早工場"
             "投資金額2028.3期までに約680億円投資予定主要製品半導体製造装置用ファインセラミック部品生産計画順次生産設備を導入しており、"
             "2027年春より本格的に生産を開始2031.3期以降250億円／年")
        ev = [e for e in extract_page(s, 4, dict(CTX, title="2027年3月期 上期 決算説明会資料")) if e["kind"] == "production"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["target"]["start"], "2027-03-01")
        self.assertNotIn("竣工", ev[0]["quote"][:20])

    def test_launch_goal_year_653A(self):
        ev = extract_page("中長期的には2030年頃の上市を目指します。", 37, dict(CTX, title="東京証券取引所グロース市場への上場に伴う当社決算情報等のお知らせ"))
        e = [x for x in ev if x["kind"] == "launch"][0]
        self.assertEqual(e["target"]["start"], "2030-01-01")
        self.assertTrue(e["needs_review"])   # 年のみ → 要確認のまま
        # 同じ資料の定型リスク文は拾わない
        self.assertEqual(extract_page("医薬品の上市までには開発の失敗や遅延のリスクを伴います。", 40, CTX), [])

    def test_delay_new_date_3070(self):
        ctx = dict(CTX, title="（変更）「系統蓄電所向けの蓄電池の受注契約締結に関するお知らせ」の一部変更に関するお知らせ", pubdate="2026-11-02 15:00:00")
        s = ("静岡県藤枝市の完工時期については令和９年 10月頃を見込んでおり、現在、送配電事業者の再接続検討の回答を待っている段階であります。")
        ev = [e for e in extract_page(s, 1, ctx) if e["kind"] == "delay"]
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["target"]["start"], ev[0]["target"]["end"]), ("2027-10-01", "2027-10-31"))
        # 題名が変更・延期でない資料の「時期は○年」は延期にしない
        self.assertEqual([e for e in extract_page("発売時期は2027年6月を見込んでおります。", 1, CTX) if e["kind"] == "delay"], [])

    def test_applied_fx_rate_7236(self):
        s = "※業績予想における適用為替レート USD: 158.5, THB: 4.95, CNY: 22.99, CZK: 7.52, IDR: 0.0094, VND: 0.0061, EUR: 183.49"
        self.assertIn("fx", [e["kind"] for e in extract_page(s, 5, dict(CTX, title="2026年度第2四半期決算説明会資料"))])
        # 実績の為替レート表は拾わない
        self.assertEqual([e for e in extract_page("USD/円 144.82 162.45 157.33 THB/円 4.43 4.87 4.7", 5, CTX) if e["kind"] == "fx"], [])


class TestV8(unittest.TestCase):
    def kinds(self, s, **kw):
        return [e for e in extract_page(s, 1, dict(CTX, **kw))]

    def test_recap_in_briefing_not_alliance(self):
        s = "WCS ABYAKTA NAWASENA（インドネシア）を子会社化し、ローカル市場へ参入。"
        self.assertEqual([e for e in self.kinds(s, title="2026年度第２四半期決算実績ならびに中期経営計画の進捗") if e["kind"] == "alliance"], [])
        s = "インドの現地法人設立準備、業務提携の締結、今後ライセンスを追加する。"
        self.assertEqual([e for e in self.kinds(s, title="2026年12月期 第3四半期 決算説明資料") if e["kind"] == "alliance"], [])
        self.assertEqual([e for e in self.kinds("2025/8 資本業務提携4件を実施", title="統合報告書2026") if e["kind"] == "alliance"], [])

    def test_past_form_not_alliance_even_for_plain_title(self):
        self.assertEqual([e for e in self.kinds("WCSを子会社化し、ローカル市場へ参入しました。") if e["kind"] == "alliance"], [])
        self.assertEqual([e for e in self.kinds("2025年9月に株式会社本田の全株式を取得し子会社化(百万円)") if e["kind"] == "alliance"], [])

    def test_new_disclosure_still_alliance(self):
        ev = [e for e in self.kinds("当社は、A社と資本業務提携契約を締結いたしました。", title="資本業務提携に関するお知らせ") if e["kind"] == "alliance"]
        self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0]["needs_review"])   # 日付がない提携は確定扱いにしない
        self.assertFalse(ev[0]["confirmed"])
        ev = [e for e in self.kinds("本日開催の取締役会において、B社の株式を取得し子会社化することを決議いたしました。", title="B社の株式取得(子会社化)に関するお知らせ") if e["kind"] == "alliance"]
        self.assertEqual(len(ev), 1)
        ev = [e for e in self.kinds("当社は、D社と業務提携契約を締結いたしましたので、お知らせいたします。", title="業務提携に関するお知らせ") if e["kind"] == "alliance"]
        self.assertEqual(len(ev), 1)

    def test_tanshin_alliance_needs_review(self):
        ev = [e for e in self.kinds("自動車向け開発を手掛けるC社と資本業務提携契約を締結いたしました。", title="2027年3月期 第2四半期 決算短信〔IFRS〕(連結)") if e["kind"] == "alliance"]
        self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0]["needs_review"])
        self.assertFalse(ev[0]["confirmed"])

    def test_revision_still_extracted_in_briefing(self):
        s = "通期業績予想の経常利益を350億円に上方修正しました。"
        self.assertIn("revision_up", [e["kind"] for e in self.kinds(s, title="2026年度中間期決算説明資料")])

    def test_delay_neighbor_date_not_inherited(self):
        # 地点ごとに日付が違う: 次の文の日付(1地点だけ)を、地点を限らない延期の文に継承しない
        s = ("上記3カ所の完工時期が大幅に遅れる見通しであるとの連絡を受けました。"
             "なお、藤枝市の完工時期は令和9年10月頃を見込んでおり、長浜市と京丹後市は未定です。")
        ev = [e for e in self.kinds(s, pubdate="2026-11-02 15:00:00") if e["kind"] == "delay"]
        first = ev[0]
        self.assertIsNone(first["target"])
        self.assertTrue(first["needs_review"])
        self.assertIn("一部の地点", first["summary"])

    def test_delay_target_same_sentence_far(self):
        s = "発売時期を延期することとし、新たな発売時期は十分な検証を踏まえたうえで2027年10月を予定しております。"
        ev = [e for e in self.kinds(s) if e["kind"] == "delay"]
        self.assertEqual(ev[0]["target"]["start"], "2027-10-01")

    def test_delay_undecided_is_review_without_date(self):
        ev = [e for e in self.kinds("発売時期を延期いたします。新たな発売時期は未定です。") if e["kind"] == "delay"]
        self.assertEqual(len(ev), 1)
        self.assertIsNone(ev[0]["target"])
        self.assertTrue(ev[0]["needs_review"])
        self.assertIn("未定", ev[0]["summary"])
        self.assertFalse(ev[0]["confirmed"])

    def test_buyback_summary_has_period_and_limit(self):
        s = ("当社は、自己株式の取得を決議いたしました。2．取得する株式の総数:1,000,000株（上限）"
             "3．取得価額の総額:1,500,000,000円（上限）4．取得期間2026年11月4日から2027年3月31日まで")
        ev = [e for e in self.kinds(s, title="自己株式取得に係る事項の決定に関するお知らせ") if e["kind"] == "buyback"]
        self.assertTrue(ev)
        for k in ("2026年11月4日", "2027年3月31日", "1,000,000株", "1,500,000,000円"):
            self.assertIn(k, ev[0]["summary"])

    def test_buyback_progress_report_not_plan(self):
        s = "自己株式取得に係る事項の進捗状況。取得株式の総数:3,514,700株、取得価額の総額:785,928,000円"
        self.assertEqual([e for e in self.kinds(s, title="自己株式取得に係る事項の進捗状況に関するお知らせ") if e["kind"] == "buyback"], [])

    def test_version(self):
        self.assertEqual(self.kinds("新製品Aを2027年2月15日に発売する予定です。")[0]["extractor"], "rule-v11")


class TestV9(unittest.TestCase):
    TS = "2027年3月期 第2四半期 決算短信〔IFRS〕(連結)"

    def alli(self, s, title):
        return [e for e in extract_page(s, 1, dict(CTX, title=title)) if e["kind"] == "alliance"]

    def test_tanshin_dated_past_partnership_dropped(self):
        s = "当社は2026年7月にホテル会社と提携を締結し、本提携を通じて会員に訴求します。"
        self.assertEqual(self.alli(s, self.TS), [])
        self.assertEqual(self.alli("既存の提携をA社運航便まで拡大・拡充します。", self.TS), [])

    def test_order_intake_wording_not_alliance(self):
        s = "引き続き月額課金案件の受注獲得を推し進め、過去最高の売上に着地する見込みです。"
        self.assertEqual(self.alli(s, self.TS), [])
        s = "当社グループは、M&A(子会社化、事業譲受、資本参加等)を実施することにより事業を補完・強化できると考えており、積極的に推進します。"
        self.assertEqual(self.alli(s, "2026年9月期決算短信〔日本基準〕(連結)"), [])
        self.assertEqual(self.alli("海外拠点税前利益は5,644億円となりました。", "決算の概要"), [])

    def test_order_notice_is_not_alliance(self):
        pages = ["大型案件の受注に関するお知らせ 当社は、入札において、下記の大型案件を受注いたしましたので、お知らせいたします。"
                 "記 1．受注の概要 当社は、国内における以下の大型案件を受注しております。"]
        ev = [e for e in extract_document(pages, dict(CTX, title="大型案件の受注に関するお知らせ")) if e["kind"] == "alliance"]
        self.assertEqual(ev, [])

    def test_alliance_one_per_document_when_title_names_it(self):
        pages = ["株式会社Xの株式取得（子会社化）に関するお知らせ 当社は、取締役会において、X社の株式を取得し子会社化することを決議いたしました。"
                 "当社は、X社の株式を取得し子会社化することが企業価値の向上に資すると判断しました。"]
        ev = [e for e in extract_document(pages, dict(CTX, title="株式会社Xの株式取得（子会社化）に関するお知らせ")) if e["kind"] == "alliance"]
        self.assertEqual(len(ev), 1)

    def test_buyback_one_per_document_target_is_period(self):
        body = ("自己株式取得に係る事項の決定に関するお知らせ 当社は、自己株式取得に係る事項を決議いたしましたのでお知らせいたします。"
                "資本効率の向上のため、自己株式の取得を決定いたしました。"
                "取得する株式の総数:1,000,000株（上限）取得価額の総額:1,500,000,000円（上限）取得期間2026年11月4日から2027年3月31日まで")
        ev = [e for e in extract_document([body], dict(CTX, title="自己株式取得に係る事項の決定に関するお知らせ")) if e["kind"] == "buyback"]
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["target"]["start"], ev[0]["target"]["end"]), ("2026-11-04", "2027-03-31"))
        self.assertIn("上限 1,000,000株", ev[0]["summary"])

    def test_buyback_recap_in_briefing_dropped(self):
        s = "資本効率の向上のため自己株式取得を決定。取得する株式の総数:1,000,000株"
        self.assertEqual([e for e in extract_page(s, 27, dict(CTX, title="決算説明資料")) if e["kind"] == "buyback"], [])

    def test_merge_same_buyback_in_two_documents_keeps_notice(self):
        body = "自己株式取得に係る事項を決議いたしました。取得する株式の総数:500,000株 取得期間2026年11月4日から2027年3月31日まで"
        tan = extract_document([body], dict(CTX, title="2027年3月期 第2四半期 決算短信〔日本基準〕(連結)", url="https://example.invalid/tanshin.pdf"))
        notice = extract_document([body], dict(CTX, title="自己株式取得に係る事項の決定に関するお知らせ", url="https://example.invalid/notice.pdf"))
        tan = [e for e in tan if e["kind"] == "buyback"]
        notice = [e for e in notice if e["kind"] == "buyback"]
        self.assertEqual(tan[0]["id"], notice[0]["id"])
        for first, second in ((tan, notice), (notice, tan)):
            evs, _, _ = merge_events([], [dict(x) for x in first])
            evs, _, _ = merge_events(evs, [dict(x) for x in second])
            self.assertEqual(len(evs), 1)
            self.assertEqual(evs[0]["url"], "https://example.invalid/notice.pdf")
            self.assertEqual(evs[0]["title"], "自己株式取得に係る事項の決定に関するお知らせ")   # 題名とURLがずれない


class TestV10(unittest.TestCase):
    TS = "2027年3月期 第2四半期 決算短信〔日本基準〕(連結)"

    def k(self, s, kind, **kw):
        return [e for e in extract_page(s, 1, dict(CTX, **kw)) if e["kind"] == kind]

    def test_revision_recap_of_past_publication_dropped(self):
        s = "当社は、2026年10月26日付で公表した通期の業績予想を下方修正しました。"
        self.assertEqual(self.k(s, "revision_down", title=self.TS), [])
        # 修正の通知そのものは、前回予想の公表日を書いていても拾う
        s2 = "2026年8月7日付で公表した業績予想を下記のとおり上方修正いたします。"
        self.assertTrue(self.k(s2, "revision_up", title="通期業績予想の修正に関するお知らせ"))
        # 今般の修正も書かれていれば残し、要確認にする
        s3 = "2026年10月26日付で公表した予想を、今般さらに上方修正いたします。"
        ev = self.k(s3, "revision_up", title=self.TS)
        self.assertTrue(ev and ev[0]["needs_review"])

    def test_alliance_past_month_recap_dropped(self):
        self.assertEqual(self.k("7月にA社と資本業務提携契約を締結しました。", "alliance", title=self.TS), [])

    def test_order_title_without_alliance_word_dropped(self):
        self.assertEqual(self.k("当社は大型案件を受注いたしました。", "alliance", title="大型案件の受注に関するお知らせ"), [])
        self.assertTrue(self.k("当社はE社と業務提携契約を締結いたしました。", "alliance", title="業務提携及び大型案件の受注に関するお知らせ"))

    def test_joint_venture_quote_is_establishment_sentence(self):
        s = ("当社は、F社と合弁会社を設立することを決議いたしました。"
             "3．今後の見通し 当該子会社の設立に伴う2027年8月期の当社業績に与える影響は軽微と見込んでおります。")
        ev = self.k(s, "alliance", title="合弁会社設立のお知らせ")
        self.assertEqual(len(ev), 1)
        self.assertIn("合弁会社を設立", ev[0]["quote"])

    def test_buyback_monthly_report_not_new(self):
        s = ("自己株式取得のための市場買付けを、下記のとおり実施いたしましたのでお知らせいたします。記 １．買付期間 2026年10月１日から2026年10月31日まで "
             "２．買付株式数 0株 ３．買付総額 0円 【ご参考】 １．2026年４月30日開催の取締役会での決議内容 ・取得する株式の総数 200,000株（上限） "
             "・自己株式取得の日程 2026年５月１日から2027年３月31日まで")
        self.assertEqual(self.k(s, "buyback", title="自己株式の市場買付けに関するお知らせ"), [])

    def test_buyback_real_layout_shares_and_period(self):
        # 実際の書き方: 「取得し得る株式の総数」、数字の中や単位の前に空白が入る
        s = ("自己株式の取得に係る事項の決定に関するお知らせ 当社は、取締役会において、自己株式取得に係る事項について決議いたしましたのでお知らせいたします。\n"
             "２． 取得に係る事項の内容\n(1) 取得対象株式の種類    当社普通株式\n(2) 取得し得る株式の総数   750,000 株（上 限）\n"
             "(3) 株式の取得価額の総額   50,000,000 円（上限）\n(4) 取得期間         2026 年 11 月 4 日～ 2026年 12 月 31日\n")
        ev = self.k(s, "buyback", title="自己株式の取得に係る事項の決定に関するお知らせ")
        self.assertTrue(ev)
        self.assertIn("上限 750,000株", ev[0]["summary"])
        self.assertIn("50,000,000円", ev[0]["summary"])
        self.assertEqual((ev[0]["target"]["start"], ev[0]["target"]["end"]), ("2026-11-04", "2026-12-31"))
        self.assertFalse(ev[0]["needs_review"])

    def test_buyback_without_limit_is_review(self):
        ev = self.k("自己株式取得に係る事項を決議いたしました。", "buyback", title="自己株式取得に係る事項の決定に関するお知らせ")
        self.assertTrue(ev and ev[0]["needs_review"] and not ev[0]["confirmed"])

    def test_weak_events_without_date_are_review(self):
        for kind, s, title in (("launch", "新製品の発売を計画しています。", "お知らせ"),
                               ("delay", "発売時期を延期いたします。", "お知らせ"),
                               ("alliance", "G社と業務提携いたします。", "業務提携に関するお知らせ")):
            ev = self.k(s, kind, title=title)
            self.assertTrue(ev, kind)
            self.assertTrue(ev[0]["needs_review"], kind)
            self.assertFalse(ev[0]["confirmed"], kind)

    def test_delay_recap_of_past_decision_in_tanshin_dropped(self):
        s = "2026年7月3日開催の取締役会で決議した本経営統合のスケジュールの変更は、以下のとおりです。"
        self.assertEqual(self.k(s, "delay", title=self.TS), [])

    def test_merge_buyback_twin_without_shares(self):
        def ev(i, url, title, bb):
            return {"id": i, "kind": "buyback", "code": "5703", "announced_at": "2026-11-02 15:00:00", "url": url, "title": title,
                    "bb": bb, "checked_at": "x", "quote": i, "page": 1, "target_text": "x", "time_text": None}
        tan = ev("a", "https://example.invalid/t.pdf", "2027年3月期 第2四半期 決算短信", {"period": None, "shares": None, "amount": None})
        notice = ev("b", "https://example.invalid/n.pdf", "自己株式取得に係る事項の決定に関するお知らせ",
                    {"period": ("2026年11月4日", "2027年3月31日"), "shares": "600,000", "amount": "15億円"})
        evs, _, _ = merge_events([], [tan])
        evs, _, _ = merge_events(evs, [notice])
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["url"], "https://example.invalid/n.pdf")

    def test_forecast_items_core_operating_and_eps(self):
        from extract import extract_forecast_rows
        ctx = dict(CTX, title="業績予想の修正に関するお知らせ")
        t = ("2027年3月期通期連結業績予想数値の修正\n前回発表予想 今回修正予想 増減額 増減率\n"
             "コア営業利益 100 120 20 20.0\n営業利益 90 110 20 22.2\n当期純利益 50円00銭 60円00銭 10円00銭 20.0\n")
        rows = extract_forecast_rows(t, 1, ctx)
        names = [r["item"] for r in rows]
        self.assertEqual(names.count("コア営業利益"), 1)
        self.assertEqual(names.count("営業利益"), 1)
        eps = [r for r in rows if "1株当たり" in r["item"]]
        self.assertEqual([r["item"] for r in eps], ["1株当たり当期純利益"])   # 円で書かれた値は金額の純利益ではない
        self.assertEqual(eps[0]["unit"], "円")
        self.assertIn("円", eps[0]["summary"])


class TestV11(unittest.TestCase):
    TS = "2027年3月期 第2四半期 決算短信〔日本基準〕(連結)"
    DECK = "2026年度第2四半期決算説明資料"

    def k(self, s, kind, **kw):
        return [e for e in extract_page(s, 1, dict(CTX, **kw)) if e["kind"] == kind]

    # ---- 提携
    def test_alliance_recap_without_new_marker_dropped(self):
        s = "当社は、A社を連結子会社化することにより、重要顧客を基盤とする安定収益を取り込み、同社との連携をさらに強化します。"
        self.assertEqual(self.k(s, "alliance", title=self.TS), [])
        s = "業務提携先との協業により、新たなビジネスプランを検討しています。"
        self.assertEqual(self.k(s, "alliance", title="2026年9月期 決算のお知らせ"), [])

    def test_alliance_past_dated_resolution_dropped(self):
        s = "2026年7月31日開催の取締役会において、A社の株式を取得し子会社化することを決議しました。"
        self.assertEqual(self.k(s, "alliance", title=self.TS), [])

    def test_alliance_new_resolution_kept(self):
        s = "当社は、2026年11月3日開催の取締役会において、株式会社Bと資本業務提携契約を締結することを決議いたしました。"
        ev = self.k(s, "alliance", title="株式会社Bとの資本業務提携に関するお知らせ")
        self.assertEqual(len(ev), 1)
        # 相手先が読み取れない新規開示は要確認
        ev = self.k("当社は、本日、業務提携契約を締結いたしました。", "alliance", title="業務提携に関するお知らせ")
        self.assertTrue(ev and ev[0]["needs_review"])

    # ---- 自社株買い
    def test_buyback_disposal_to_trust_not_buyback(self):
        s = ("信託の受託者が当社株式を追加取得するための金銭を追加信託すること、また株式報酬として自己株式の処分を行うことについて決議いたしました。"
             "取得期間 2026年11月20日から2026年11月30日 取得株式の総数 101,800株 取得価額の総額 308,963,000円")
        self.assertEqual(self.k(s, "buyback", title="業績連動型株式報酬制度の継続に伴う追加出資及び自己株式の処分に関するお知らせ"), [])

    def test_buyback_split_lines_and_table_layout(self):
        # 実際の書式: 項目名が行をまたぎ、文字の間に空白が入る(東ソー型)
        s = ("当社は、2026年11月５日開催の取締役会において、自己株式取得に係る事項について決議しましたので、お知らせいたします。\n"
             "２．取得に係る事項の内容\n（１） 取得対象株式の種類  普通株式\n（２） 取得し 得 る \n株式の総数  \n12,000,000 株（上限）\n"
             "（発行済株式総数（自己株式を除く）に対する割合 3.90 ％）\n（３） 株式の取得価額の  \n総額  250 億円（上限）\n"
             "（４） 取得期間  2026 年11 月６日～2027 年３月31 日\n")
        ev = self.k(s, "buyback", title="自己株式取得に係る事項の決定に関するお知らせ", pubdate="2026-11-05 15:00:00")
        self.assertTrue(ev)
        self.assertIn("上限 12,000,000株", ev[0]["summary"])
        self.assertIn("250億円", ev[0]["summary"])
        self.assertEqual(ev[0]["target"]["end"], "2027-03-31")
        self.assertFalse(ev[0]["needs_review"])

    # ---- 修正イベントの抑止
    def test_revision_in_deck_is_review_and_capped(self):
        ctx = dict(CTX, title=self.DECK)
        pages = ["エレクトロニクス事業は利益を大きく上方修正。", "通期予想の営業利益を当初予想から上方修正。", "住宅事業は北米の需要を踏まえ上方修正。",
                 "売上高も上方修正している。"]
        ev = [e for e in extract_document(pages, ctx) if e["kind"] == "revision_up"]
        self.assertEqual(len(ev), 2)
        for e in ev:
            self.assertTrue(e["needs_review"])
            self.assertFalse(e["confirmed"])

    def test_revision_notice_not_downgraded(self):
        ev = self.k("通期の営業利益を上方修正いたします。", "revision_up", title="通期業績予想の修正に関するお知らせ")
        self.assertTrue(ev)
        self.assertFalse(ev[0]["needs_review"])

    # ---- 量産・為替
    def test_production_without_date_is_review(self):
        ev = self.k("高品質を強みに、複数案件を量産化予定。", "production", title=self.DECK)
        self.assertTrue(ev and ev[0]["needs_review"])

    def test_fx_garbled_numbers_review_and_clean_summary(self):
        s = "1.1786714534 経常利益151.91008018028141.87910118038（下期想定為替レート USD=150円） 設備投資110億円"
        ev = self.k(s, "fx", title=self.TS)
        self.assertTrue(ev and ev[0]["needs_review"])
        self.assertEqual(ev[0]["summary"], "想定為替レート: USD=150円")

    def test_delay_industry_general_remark_dropped(self):
        s = "人材不足による工期の遅延が業界全体の課題となっており、計画の見直しを進めています。"
        self.assertEqual(self.k(s, "delay", title="2026年度決算説明資料"), [])

    # ---- 配当
    def div(self, pages, title, pub="2026-11-05 15:00:00"):
        from extract import extract_dividend_events
        ctx = dict(CTX, title=title, pubdate=pub)
        return [e for p in pages for e in extract_dividend_events(p, 1, ctx)]

    def test_dividend_increase_table_with_blank_interim(self):
        t = ("期末配当予想の修正に関するお知らせ（増配）\n1．期末配当予想の修正\n1 株当たり配当金\n第２四半期末 期末 合 計\n"
             "前 回 発 表 予 想\n（2026年５月22 日発表） 35 円00 銭 35 円00 銭 70 円00 銭\n今 回 修 正 予 想  40 円00 銭 75 円00 銭\n"
             "当 期 実 績\n（202 7 年 ３ 月 期 ） 35 円00 銭  \n前 期 実 績\n（202 6 年 ３ 月 期 ） 30 円00 銭 30 円00 銭 60 円00 銭\n")
        ev = self.div([t], "期末配当予想の修正に関するお知らせ（増配）")
        self.assertEqual(len(ev), 1)
        e = ev[0]
        self.assertEqual((e["kind"], e["prev"], e["new"], e["direction"]), ("dividend", "70円00銭", "75円00銭", "増配"))
        self.assertTrue(e["verified"])          # 75 = 実績35 + 期末40
        self.assertFalse(e["confirmed"])
        self.assertIn("期末 35円00銭→40円00銭", e["summary"])
        self.assertEqual(e["impact_period"], "2027年3月期")

    def test_dividend_dash_column_and_interim_decision(self):
        t = ("1．剰余金の配当（中間配当）の内容\n決 定 額 直近の配当予想 前期実績\n基準日 2026年９月30日 同左 2025年９月30日\n"
             "１株当たり配\n当金 24 円 22 円 20 円\n配当金総額 32,083 百万円 － 27,193 百万円\n"
             "2．2027年3月期の期末配当予想の修正\n１株当たりの配当金（円）\n基準日 第２四半期末 期末 年間\n前回予想\n（2026年７月31日公表）\n22 円 22 円 44 円\n"
             "今回予想 － 24 円 48 円\n今期実績 24 円 － －\n")
        ev = self.div([t], "剰余金の配当（中間配当の増配）および期末配当予想の修正に関するお知らせ")
        by = {e["item"]: e for e in ev}
        self.assertEqual((by["年間配当"]["prev"], by["年間配当"]["new"], by["年間配当"]["direction"]), ("44円", "48円", "増配"))
        self.assertTrue(by["年間配当"]["verified"])
        self.assertEqual((by["中間配当(決定額)"]["prev"], by["中間配当(決定額)"]["new"]), ("22円", "24円"))

    def test_dividend_decrease_and_unchanged_directions(self):
        t = "前回予想 30円00銭 30円00銭 60円00銭 今回予想 25円00銭 25円00銭 50円00銭 第2四半期末 期末 合計"
        t = "配当予想の修正 第2四半期末 期末 合計 前回予想 30円00銭 30円00銭 60円00銭 今回予想 30円00銭 30円00銭 60円00銭 当期実績 30円00銭"
        ev = self.div([t], "配当予想の修正に関するお知らせ")
        self.assertEqual(ev[0]["direction"], "据置")
        t2 = t.replace("今回予想 30円00銭 30円00銭 60円00銭", "今回予想 25円00銭 25円00銭 50円00銭")
        self.assertEqual(self.div([t2], "配当予想の修正に関するお知らせ")[0]["direction"], "減配")

    def test_dividend_not_extracted_from_deck_or_tanshin(self):
        t = "前回予想 30円00銭 30円00銭 60円00銭 今回予想 35円00銭 35円00銭 70円00銭"
        self.assertEqual(self.div([t], "2026年度決算説明資料"), [])
        self.assertEqual(self.div([t], "2027年3月期 第2四半期 決算短信〔日本基準〕(連結)"), [])


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
