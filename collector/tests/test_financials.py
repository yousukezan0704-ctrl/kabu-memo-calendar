"""財務数値(financials.py)と開示履歴(history.py)のテスト。
実行: cd collector/tests; python -m unittest test_financials
フィクスチャは実物の決算短信(公開IR)から数値タグだけを抜粋したもの。"""
import copy
import datetime as dt
import io
import os
import sys
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import financials as F  # noqa: E402
import history as H  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def make_zip(htm_text, inner="XBRLData/Summary/tse-acedjpsm-00000-20261102300000-ixbrl.htm"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(inner, htm_text.encode("utf-8"))
    return buf.getvalue()


def fixture_zip(name):
    with open(os.path.join(FIX, name + ".htm"), encoding="utf-8") as f:
        return make_zip(f.read())


def meta(title, id_=1, pub="2026-11-02 15:00:00"):
    return {"code": "00000", "name": "テスト", "pubdate": pub, "title": title, "url": "http://example/x.zip", "id": id_}


class TestParse(unittest.TestCase):
    def test_annual_results_forecast_dividend(self):
        r = F.parse_summary_zip(fixture_zip("annual_jgaap"), meta("2026年９月期 決算短信〔日本基準〕(連結)"))
        self.assertEqual(r["period_type"], "通期")
        self.assertEqual(r["fiscal_year_end"], "2026-09-20")
        self.assertEqual(r["period_end"], "2026-09-20")
        self.assertEqual(r["unit"], "百万円")
        # scale=6 -> 百万円。33,178 は 33178
        self.assertEqual(r["results"], {"sales": 33178, "operating_income": 892, "ordinary_income": 864,
                                        "net_income": 643, "eps": 287.24})
        # 前年同期比(%)。scale=-2 でも画面表記のまま。純利益は sign="-" で負
        self.assertEqual(r["yoy_pct"], {"sales": 0.9, "operating_income": 4.1, "ordinary_income": 0.7,
                                        "net_income": -9.7})
        # 通期の短信では、会社予想は「来期(Next)」の通期
        fc = r["forecast"]
        self.assertEqual((fc["period"], fc["sales"], fc["operating_income"], fc["ordinary_income"],
                          fc["net_income"], fc["eps"], fc["dps"]),
                         ("通期", 36790, 1135, 995, 726, 316.38, 40))
        self.assertEqual(fc["yoy_pct"]["operating_income"], 27.2)
        self.assertEqual(r["dividend"], {"annual_actual": 40, "annual_forecast": 40})
        self.assertEqual(r["balance"], {"net_assets": 7837, "equity_ratio_pct": 26.9, "bps": 3496.73,
                                        "shares_issued": 2296176, "treasury_shares": 54881})
        self.assertEqual(r["id"], 1)
        self.assertEqual(r["announced_at"], "2026-11-02 15:00:00")
        self.assertEqual(r["source"], "TDnet決算短信(XBRL)")

    def test_q2_negative_values_and_blank_yoy(self):
        r = F.parse_summary_zip(fixture_zip("q2_loss_jgaap"),
                                meta("2027年3月期 第2四半期（中間期）決算短信〔日本基準〕（連結）"))
        self.assertEqual(r["period_type"], "第2四半期")
        self.assertEqual(r["fiscal_year_end"], "2027-03-31")
        self.assertEqual(r["period_end"], "2026-09-30")
        # sign="-" -> 赤字は負の数
        self.assertEqual(r["results"]["operating_income"], -64)
        self.assertEqual(r["results"]["ordinary_income"], -60)
        self.assertEqual(r["results"]["net_income"], -55)
        self.assertEqual(r["results"]["sales"], 5802)
        # 赤字転換などで増減率が「―」の場合は数値タグが無い -> None(推測しない)
        self.assertIsNone(r["yoy_pct"]["operating_income"])
        self.assertEqual(r["yoy_pct"]["sales"], 0.2)
        # 四半期の短信では、会社予想は「当期」の通期
        self.assertEqual(r["forecast"]["sales"], 11525)
        self.assertEqual(r["forecast"]["operating_income"], -104)
        self.assertEqual(r["forecast"]["eps"], -51.17)
        self.assertEqual(r["forecast"]["dps"], 20)
        # 通期の確定配当は四半期の時点では無い
        self.assertIsNone(r["dividend"]["annual_actual"])
        self.assertEqual(r["dividend"]["annual_forecast"], 20)

    def test_ifrs_does_not_guess_missing_items(self):
        r = F.parse_summary_zip(fixture_zip("q3_ifrs"), meta("2026年12月期 第3四半期 決算短信〔ＩＦＲＳ〕（連結）"))
        self.assertEqual(r["period_type"], "第3四半期")
        self.assertEqual(r["results"]["sales"], 384947)
        self.assertEqual(r["results"]["net_income"], 51673)
        self.assertEqual(r["results"]["eps"], 98.7)
        # IFRSには経常利益が無い。税引前利益で代用しない
        self.assertIsNone(r["results"]["ordinary_income"])
        self.assertIsNone(r["results"]["operating_income"])
        # 予想の「利益」は親会社帰属ではない(少数株主を含む)ので純利益には入れない
        self.assertIsNone(r["forecast"]["net_income"])
        self.assertEqual(r["forecast"]["sales"], 520000)
        self.assertEqual(r["forecast"]["dps"], 70)
        self.assertEqual(r["balance"]["shares_issued"], 525634500)

    def test_no_forecast_is_none(self):
        r = F.parse_summary_zip(fixture_zip("q3_jgaap_noforecast"), meta("2026年12月期 第３四半期決算短信〔日本基準〕(連結)"))
        self.assertEqual(r["results"]["operating_income"], 666)
        self.assertEqual(r["yoy_pct"]["operating_income"], 67.8)
        self.assertTrue(all(r["forecast"][k] is None for k in ("sales", "operating_income", "net_income", "eps", "dps")))

    def test_nonconsolidated_uses_net_income_with_note(self):
        # 非連結の会社(実物の短信から抜粋): 純利益は NetIncome。注記が付く
        r = F.parse_summary_zip(fixture_zip("q2_nonconsol_jgaap"),
                                meta("2027年3月期 第2四半期（中間期）決算短信〔日本基準〕（非連結）"))
        self.assertEqual(r["period_type"], "第2四半期")
        self.assertEqual(r["basis"], "非連結")
        self.assertEqual(r["results"], {"sales": 3618, "operating_income": 255, "ordinary_income": 272,
                                        "net_income": 184, "eps": 64.96})
        self.assertEqual(r["yoy_pct"]["net_income"], -23.1)  # 元タグは sign="-" の 23.1
        self.assertEqual(r["forecast"]["net_income"], 690)
        self.assertEqual(r["forecast"]["yoy_pct"]["net_income"], 10.4)
        self.assertEqual(r["forecast"]["eps"], 242.35)
        self.assertIn("非連結", r["results_note"])
        self.assertNotIn("net_income", r.get("missing_reason", {}))

    def test_consolidated_does_not_fall_back_to_profit(self):
        # 連結書類では NetIncome(少数株主分を含みうる)や個別の値を親会社帰属の代わりにしない
        ctx = "CurrentYearDuration_ConsolidatedMember_ResultMember"
        sol = "CurrentYearDuration_NonConsolidatedMember_ResultMember"
        def ctxdef(c):
            return ('<xbrli:context id="%s"><xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate>'
                    '<xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>' % c)
        def fact(c, n, v):
            return '<ix:nonFraction name="tse-ed-t:%s" contextRef="%s" scale="6" format="ixt:numdotdecimal">%s</ix:nonFraction>' % (n, c, v)
        htm = ctxdef(ctx) + ctxdef(sol) + fact(ctx, "NetSales", "100") + fact(ctx, "NetIncome", "9") + fact(sol, "NetIncome", "7")
        r = F.parse_summary_zip(make_zip(htm), meta("2026年3月期 決算短信〔日本基準〕(連結)"))
        self.assertEqual(r["basis"], "連結")
        self.assertIsNone(r["results"]["net_income"])
        self.assertNotIn("results_note", r)
        self.assertIn("net_income", r["missing_reason"])

    def test_normal_records_have_basis_and_no_note(self):
        r = F.parse_summary_zip(fixture_zip("annual_jgaap"), meta("2026年９月期 決算短信〔日本基準〕(連結)"))
        self.assertEqual(r["basis"], "連結")
        self.assertNotIn("results_note", r)
        self.assertNotIn("missing_reason", r)

    def test_ifrs_missing_reason(self):
        r = F.parse_summary_zip(fixture_zip("q3_ifrs"), meta("2026年12月期 第3四半期 決算短信〔ＩＦＲＳ〕（連結）"))
        self.assertIn("ordinary_income", r["missing_reason"])
        self.assertIn("IFRS", r["missing_reason"]["ordinary_income"])
        self.assertIn("operating_income", r["missing_reason"])
        self.assertNotIn("net_income", r["missing_reason"])

    def test_not_earnings_returns_none(self):
        z = fixture_zip("annual_jgaap")
        self.assertIsNone(F.parse_summary_zip(z, meta("2026年９月期 決算補足説明資料")))
        self.assertIsNone(F.parse_summary_zip(b"not a zip", meta("2026年９月期 決算短信")))
        self.assertIsNone(F.parse_summary_zip(make_zip("<html></html>", "XBRLData/Attachment/x.htm"), meta("決算短信")))
        self.assertIsNone(F.parse_summary_zip(make_zip("<html></html>"), meta("決算短信")))

    def test_scale_sign_format_rules(self):
        def one(attrs, text, scale_ctx="CurrentYearDuration_ConsolidatedMember_ResultMember"):
            htm = ('<xbrli:context id="%s"><xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate>'
                   '<xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>'
                   '<ix:nonFraction name="tse-ed-t:NetSales" contextRef="%s" %s>%s</ix:nonFraction>'
                   % (scale_ctx, scale_ctx, attrs, text))
            r = F.parse_summary_zip(make_zip(htm), meta("2026年3月期 決算短信"))
            return r["results"]["sales"] if r else None  # 数値が1つも取れなければ書類ごと None
        self.assertEqual(one('scale="6" format="ixt:numdotdecimal"', "1,234"), 1234)
        self.assertEqual(one('scale="3" format="ixt:numdotdecimal"', "1,234"), 1.234)   # 千円表示 -> 百万円
        self.assertEqual(one('scale="6" sign="-" format="ixt:numdotdecimal"', "50"), -50)
        self.assertEqual(one('scale="6" format="ixt:zerodash"', "－"), 0)
        self.assertEqual(one('scale="6" format="ixt:num-dot-decimal"', "１，２００"), 1200)  # 全角数字
        self.assertIsNone(one('scale="6" xsi:nil="true"', ""))
        self.assertIsNone(one('scale="6"', "―"))  # 形式指定が無い記号は数値にしない


class TestMerge(unittest.TestCase):
    def rec(self, id_, fye="2026-03-31", pt="通期", pub="2026-05-10 15:00:00", end="2026-03-31", sales=100):
        return {"id": id_, "announced_at": pub, "period_type": pt, "fiscal_year_end": fye, "period_end": end,
                "doc_title": "t", "url": "u", "unit": "百万円", "results": {"sales": sales}, "source": F.SOURCE}

    def test_new_doc_and_sort(self):
        d = F.merge_period(None, self.rec(1), "12340", "テスト社")
        self.assertEqual((d["code"], d["name"]), ("12340", "テスト社"))
        self.assertIn("未確認", d["source"])
        d = F.merge_period(d, self.rec(2, pt="第1四半期", end="2026-06-30", fye="2027-03-31", pub="2026-08-05 15:00:00"),
                           "12340", "テスト社")
        self.assertEqual([p["id"] for p in d["periods"]], [2, 1])  # period_end の降順

    def test_same_id_not_duplicated_and_input_untouched(self):
        d = F.merge_period(None, self.rec(1), "1", "a")
        before = copy.deepcopy(d)
        d2 = F.merge_period(d, self.rec(1, sales=999), "1", "a")
        self.assertEqual(len(d2["periods"]), 1)
        self.assertEqual(d2["periods"][0]["results"]["sales"], 999)  # 同じ書類の再解析は解析結果を新しくする
        self.assertEqual(d, before)  # 引数は書き換えない

    def test_reparse_keeps_correction_links(self):
        d = F.merge_period(None, self.rec(1), "1", "a")
        d = F.merge_period(d, self.rec(2, pub="2026-05-20 15:00:00", sales=105), "1", "a")
        d = F.merge_period(d, self.rec(2, pub="2026-05-20 15:00:00", sales=106), "1", "a")
        by = {p["id"]: p for p in d["periods"]}
        self.assertEqual(len(d["periods"]), 2)
        self.assertEqual(by[2]["supersedes"], 1)  # 訂正の履歴を引き継ぐ
        self.assertEqual(by[2]["results"]["sales"], 106)

    def test_correction_keeps_history(self):
        d = F.merge_period(None, self.rec(1), "1", "a")
        d = F.merge_period(d, self.rec(2, pub="2026-05-20 15:00:00", sales=105), "1", "a")
        self.assertEqual(len(d["periods"]), 2)  # 旧は残す
        by = {p["id"]: p for p in d["periods"]}
        self.assertEqual(by[2]["supersedes"], 1)
        self.assertNotIn("supersedes", by[1])
        self.assertEqual(by[1]["results"]["sales"], 100)
        # 3回目の訂正は直前の版を指す
        d = F.merge_period(d, self.rec(3, pub="2026-06-01 15:00:00"), "1", "a")
        self.assertEqual({p["id"]: p for p in d["periods"]}[3]["supersedes"], 2)

    def test_out_of_order_backfill(self):
        d = F.merge_period(None, self.rec(2, pub="2026-05-20 15:00:00"), "1", "a")
        d = F.merge_period(d, self.rec(1, pub="2026-05-10 15:00:00"), "1", "a")
        by = {p["id"]: p for p in d["periods"]}
        self.assertEqual(by[1]["superseded_by"], 2)
        self.assertNotIn("supersedes", by[1])

    def test_different_period_is_not_correction(self):
        d = F.merge_period(None, self.rec(1), "1", "a")
        d = F.merge_period(d, self.rec(2, pt="第1四半期", end="2026-06-30", fye="2027-03-31"), "1", "a")
        self.assertTrue(all("supersedes" not in p for p in d["periods"]))


class TestHistory(unittest.TestCase):
    def test_classify(self):
        c = H.classify_title
        self.assertEqual(c("2027年3月期 第2四半期（中間期）決算短信〔日本基準〕（連結）"), "決算短信")
        self.assertEqual(c("2026年９月期 決算短信〔日本基準〕(連結)"), "決算短信")
        self.assertEqual(c("2027年3月期 第2四半期決算補足説明資料"), "決算説明資料")
        self.assertEqual(c("2026年12月期 第3四半期 決算説明会資料"), "決算説明資料")
        self.assertEqual(c("業績予想の修正に関するお知らせ"), "業績修正")
        self.assertEqual(c("通期業績予想及び配当予想の修正に関するお知らせ"), "業績修正")
        self.assertEqual(c("配当予想の修正（増配）に関するお知らせ"), "配当修正")
        self.assertEqual(c("自己株式の取得に係る事項の決定に関するお知らせ"), "自社株")
        self.assertEqual(c("役員の異動に関するお知らせ"), "その他")

    ITEMS = [
        {"company_code": "1", "title": "2026年3月期 決算短信〔日本基準〕(連結)", "pubdate": "2026-05-12 15:00:00"},
        {"company_code": "1", "title": "2026年3月期 第2四半期（中間期）決算短信〔日本基準〕(連結)", "pubdate": "2025-11-10 15:00:00"},
        {"company_code": "1", "title": "2026年3月期 第1四半期決算短信〔日本基準〕(連結)", "pubdate": "2025-08-08 15:30:00"},
        {"company_code": "1", "title": "2026年3月期 第3四半期決算短信〔日本基準〕(連結)", "pubdate": "2026-02-10 15:00:00"},
        {"company_code": "1", "title": "業績予想の修正に関するお知らせ", "pubdate": "2025-12-01 15:00:00"},
        {"company_code": "1", "title": "2026年3月期 決算補足説明資料", "pubdate": "2026-05-12 15:00:00"},
        {"company_code": "1", "title": "2026年3月期 決算短信〔日本基準〕(連結)", "pubdate": "2026-05-12 15:00:00"},  # 重複
    ]

    def test_history_only_earnings_past_marked(self):
        h = H.earnings_history(self.ITEMS)
        self.assertEqual([x["period_type"] for x in h], ["通期", "第3四半期", "第2四半期", "第1四半期"])
        self.assertEqual(h[0]["pubdate"], "2026-05-12 15:00:00")
        self.assertEqual(h[0]["kind"], "過去の実績")
        self.assertIn("確定時刻ではありません", h[0]["note"])
        self.assertEqual(h[0]["fiscal_label"], "2026年3月期")
        # tdnet 生の形({"Tdnet": {...}})も受け付ける
        self.assertEqual(len(H.earnings_history([{"Tdnet": self.ITEMS[0]}])), 1)

    def test_reference_next(self):
        h = H.earnings_history(self.ITEMS)
        r = H.reference_next(h, dt.date(2026, 6, 1))   # 5/12は過ぎた -> 次は昨年8/8の1年後
        self.assertEqual(r["period_type"], "第1四半期")
        self.assertEqual(r["last_year_pubdate"], "2025-08-08 15:30:00")
        self.assertEqual(r["approx_date"], "2026-08-08")
        self.assertFalse(r["confirmed"])
        self.assertIn("参考・未確定", r["label"])
        r = H.reference_next(h, "2026-11-03")           # 昨年11/10 -> 2026-11-10
        self.assertEqual((r["period_type"], r["approx_date"]), ("第2四半期", "2026-11-10"))
        self.assertIsNone(H.reference_next([], "2026-11-03"))
        self.assertIsNone(H.reference_next(h, "2026-11-20", period_type="第2四半期"))


if __name__ == "__main__":
    unittest.main()
