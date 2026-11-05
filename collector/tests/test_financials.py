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


def rev_zip(htm_text, inner="tse-rvfc-00000-20261102000000-ixbrl.htm"):
    return make_zip(htm_text, inner)


def rev_fixture(name):
    with open(os.path.join(FIX, name + ".htm"), encoding="utf-8") as f:
        return rev_zip(f.read())


def rev_fact(name, ctx, val, scale=6, sign="", nil=False):
    if nil:
        return '<ix:nonFraction name="tse-ed-t:%s" contextRef="%s" xsi:nil="true"/>' % (name, ctx)
    sg = ' sign="-"' if sign else ""
    return '<ix:nonFraction name="tse-ed-t:%s" contextRef="%s" scale="%d"%s format="ixt:numdotdecimal">%s</ix:nonFraction>' % (
        name, ctx, scale, sg, val)


def rev_doc(*facts):
    return "<html><body>" + "".join(facts) + "</body></html>"


class TestRevision(unittest.TestCase):
    """業績予想の修正(tse-rvfc)。フィクスチャは実物(東計電算4746・ほくほくFG8377)の数値タグだけの抜粋。"""

    def test_consolidated_and_nonconsolidated_annual(self):
        r = F.parse_revision_zip(rev_fixture("revision_consol_nonconsol"), meta("業績予想の修正に関するお知らせ"))
        self.assertEqual((r["kind"], r["scope"], r["period"]), ("業績予想修正", "連結", "通期"))
        self.assertEqual((r["code"], r["announced_date"]), ("4746", "2026-11-02"))
        self.assertEqual((r["period_start"], r["period_end"]), ("2026-01-01", "2026-12-31"))
        self.assertEqual(r["basis"], "公式XBRL(tse-rvfc)")
        it = {i["item"]: i for i in r["items"]}
        self.assertEqual([it[k][x] for k in ("sales", "operating_income", "ordinary_income", "net_income")
                          for x in ("prev", "new")], [21884, 21884, 6825, 6425, 7879, 7479, 8601, 8323])
        self.assertEqual((it["sales"]["diff"], it["sales"]["diff_pct"]), (0, 0))
        self.assertEqual((it["operating_income"]["diff"], it["operating_income"]["diff_pct"]), (-400, -5.9))
        self.assertEqual((it["ordinary_income"]["diff"], it["ordinary_income"]["diff_pct"]), (-400, -5.1))
        self.assertEqual((it["net_income"]["diff"], it["net_income"]["diff_pct"]), (-278, -3.2))
        self.assertEqual(it["net_income"]["diff_source"], "XBRL")
        # EPS は増減がXBRLに無いので 今回-前回 を計算し、そう明記する
        self.assertEqual((it["eps"]["prev"], it["eps"]["new"], it["eps"]["diff"]), (119.3, 115.45, -3.85))
        self.assertEqual(it["eps"]["diff_source"], "計算")
        self.assertIsNone(it["eps"]["diff_pct"])
        self.assertEqual(r["direction"], "down")
        self.assertTrue(r["reason_text"])
        nc = r["non_consolidated"]
        self.assertEqual((nc["scope"], nc["period"], nc["direction"]), ("非連結", "通期", "down"))
        nit = {i["item"]: i for i in nc["items"]}
        self.assertNotIn("operating_income", nit)  # 個別は営業利益のタグが無い -> 作らない
        self.assertEqual((nit["net_income"]["prev"], nit["net_income"]["new"], nit["net_income"]["diff"]), (8590, 8312, -278))
        self.assertEqual(r["other_periods"], [])
        self.assertIsNone(r["dividend"])

    def test_q2_other_period_and_dividend(self):
        r = F.parse_revision_zip(rev_fixture("revision_q2_dividend"), meta("業績予想及び配当予想の修正に関するお知らせ"))
        self.assertEqual((r["scope"], r["period"]), ("連結", "通期"))
        it = {i["item"]: i for i in r["items"]}
        o = it["ordinary_income"]
        self.assertEqual((o["prev"], o["new"], o["diff"], o["diff_pct"]), (89000, 108500, 19500, 21.9))
        self.assertNotIn("sales", it)
        self.assertEqual(r["direction"], "up")
        self.assertEqual(len(r["other_periods"]), 1)
        q2 = r["other_periods"][0]
        self.assertEqual((q2["scope"], q2["period"], q2["period_end"]), ("連結", "第2四半期累計", "2026-09-30"))
        self.assertEqual([(i["item"], i["prev"], i["new"]) for i in q2["items"]],
                         [("ordinary_income", 45000, 59500), ("net_income", 31500, 42000), ("eps", 26.51, 35.32)])
        d = r["dividend"]
        self.assertEqual((d["q2"], d["year_end"]), ({"prev": 75, "new": 95}, {"prev": 7.5, "new": 9.5}))
        self.assertNotIn("annual", d)  # 年間は前期実績にしか無い -> 作らない

    def test_direction_and_computed_diff(self):
        def doc(pairs):
            f = []
            for name, (prev, new) in pairs.items():
                f.append(rev_fact(name, "CurrentYearDuration_ConsolidatedMember_PreviousMember_ForecastMember", prev))
                f.append(rev_fact(name, "CurrentYearDuration_ConsolidatedMember_CurrentMember_ForecastMember", new))
            return rev_zip(rev_doc(*f))
        r = F.parse_revision_zip(doc({"OperatingIncome": ("1,000", "1,200"), "OrdinaryIncome": ("1,000", "900")}), None)
        self.assertEqual(r["direction"], "mixed")
        oi = r["items"][0]
        self.assertEqual((oi["diff"], oi["diff_pct"], oi["diff_source"], oi["pct_source"]), (200, 20.0, "計算", "計算"))
        up = F.parse_revision_zip(doc({"OperatingIncome": ("1,000", "1,200"), "OrdinaryIncome": ("1,000", "1,000")}), None)
        self.assertEqual(up["direction"], "up")
        flat = F.parse_revision_zip(doc({"OperatingIncome": ("1,000", "1,000"), "NetSales": ("5", "9")}), None)
        self.assertEqual(flat["direction"], "flat")  # 売上は判定に使わない
        self.assertIsNone(F.parse_revision_zip(doc({"NetSales": ("5", "9")}), None)["direction"])
        down = F.parse_revision_zip(doc({"OperatingIncome": ("1,000", "800"), "OrdinaryIncome": ("1,000", "1,000")}), None)
        self.assertEqual(down["direction"], "down")

    def test_nil_and_range_members_are_not_used(self):
        cur = "CurrentYearDuration_ConsolidatedMember_CurrentMember_"
        prv = "CurrentYearDuration_ConsolidatedMember_PreviousMember_"
        htm = rev_doc(
            rev_fact("OperatingIncome", prv + "ForecastMember", "100"),
            rev_fact("OperatingIncome", prv + "LowerMember", "", nil=True),
            rev_fact("OperatingIncome", cur + "ForecastMember", "", nil=True),   # 今回が空 -> None
            rev_fact("OperatingIncome", cur + "LowerMember", "999"),              # レンジ側に値が入っても採用しない
            rev_fact("OperatingIncome", cur + "UpperMember", "888"),
            rev_fact("OrdinaryIncome", cur + "ForecastMember", "70", sign="-"),   # sign="-" は負
            rev_fact("OrdinaryIncome", prv + "ForecastMember", "50", sign="-"))
        r = F.parse_revision_zip(rev_zip(htm), None)
        it = {i["item"]: i for i in r["items"]}
        o = it["operating_income"]
        self.assertEqual((o["prev"], o["new"], o["diff"]), (100, None, None))
        o = it["ordinary_income"]
        self.assertEqual((o["prev"], o["new"], o["diff"]), (-50, -70, -20))

    def test_inconsistent_diff_is_flagged(self):
        c = "CurrentYearDuration_ConsolidatedMember_"
        htm = rev_doc(rev_fact("OrdinaryIncome", c + "PreviousMember_ForecastMember", "100"),
                      rev_fact("OrdinaryIncome", c + "CurrentMember_ForecastMember", "150"),
                      rev_fact("AmountChangeOrdinaryIncome", c + "CurrentMember_ForecastMember", "40"))
        it = F.parse_revision_zip(rev_zip(htm), None)["items"][0]
        self.assertEqual((it["diff"], it["diff_consistent"]), (40, False))

    def test_not_revision_returns_none(self):
        self.assertIsNone(F.parse_revision_zip(b"not a zip", None))
        self.assertIsNone(F.parse_revision_zip(fixture_zip("annual_jgaap"), meta("決算短信")))  # 決算短信のzip
        self.assertIsNone(F.parse_revision_zip(rev_fixture("revision_consol_nonconsol"), meta("決算短信〔日本基準〕(連結)")))
        self.assertIsNone(F.parse_revision_zip(rev_zip("<html><body></body></html>"), None))


if __name__ == "__main__":
    unittest.main()
