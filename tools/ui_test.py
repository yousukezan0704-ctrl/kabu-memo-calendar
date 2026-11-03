"""画面の動作テスト（Edge を自動操作）。python tools/ui_test.py
一時フォルダの配信サーバー経由で docs を開くので、本物のデータや保存先には触れない。"""
import http.server, threading, os, sys, json, tempfile, functools
from playwright.sync_api import sync_playwright

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DOCS)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass
H = functools.partial(Quiet, directory=DOCS)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/index.html" % srv.server_address[1]

fails, errors = [], []
def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name + (" " + str(info) if not cond else ""))
    if not cond: fails.append(name)

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    for vp in ({"width": 390, "height": 800}, {"width": 1100, "height": 900}):
        ctx = b.new_context(viewport=vp, accept_downloads=True)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "404" not in m.text else None)
        pg.goto(URL); pg.wait_for_selector(".grid"); pg.wait_for_timeout(500)
        tag = "[%dpx] " % vp["width"]
        check(tag + "月表示が出る", pg.locator(".cell").count() > 20)
        check(tag + "横スクロールなし", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
        check(tag + "サンプル表示", "サンプル" in pg.inner_text("main"))
        check(tag + "時期別の予定欄", "時期別の予定" in pg.inner_text("main"))
        pg.click("button:has-text('一覧')"); pg.wait_for_timeout(200)
        check(tag + "一覧に決算が出る", "決算" in pg.inner_text("main"))
        # IR
        pg.click(".tab:has-text('重要IR')"); pg.wait_for_timeout(300)
        t = pg.inner_text("main")
        check(tag + "取得状況が出る", "取得状況" in t and "未処理" in t)
        check(tag + "未完了の警告", "完了していません" in t)
        check(tag + "根拠原文とページ", "該当ページ" in t and "最終確認" in t)
        # メモ作成・自動保存・再確認日
        pg.click(".tab:has-text('メモ')"); pg.click("button:has-text('新しいメモ')")
        pg.fill("[data-f=name]", "テスト会社"); pg.fill("[data-f=reason]", "理由テスト")
        pg.click("button:has-text('明日')"); pg.wait_for_timeout(900)
        check(tag + "保存済み表示", "保存済み" in pg.inner_text("#savestate"), pg.inner_text("#savestate"))
        pg.click("button:has-text('日付を消す')"); pg.click("button:has-text('今日')") if False else None
        pg.evaluate("KMC.state.memos[0].reviewDate = KMC.addDays(KMC.today(), -2); KMC.save()"); pg.wait_for_timeout(600)
        pg.click("button:has-text('メモ一覧へ')")
        check(tag + "期限超過がホームに出る", "期限超過" in pg.inner_text("main"))
        pg.reload(); pg.wait_for_selector(".tab"); pg.click(".tab:has-text('メモ')")
        check(tag + "再読み込み後も残る", "テスト会社" in pg.inner_text("main"))
        # ics
        with pg.expect_download() as dl:
            pg.click("button:has-text('.ics')")
        ics = open(dl.value.path(), encoding="utf-8").read()
        check(tag + "ics に VALARM", "VALARM" in ics and "テスト会社" in ics)
        # バックアップ→復元
        with pg.expect_download() as dl:
            pg.click("button:has-text('バックアップを書き出す')")
        bk = dl.value.path()
        pg.evaluate("KMC.state.memos = []; KMC.save()"); pg.reload(); pg.wait_for_selector(".tab"); pg.click(".tab:has-text('メモ')")
        check(tag + "消した状態", "テスト会社" not in pg.inner_text("main"))
        pg.once("dialog", lambda d: d.accept())
        pg.set_input_files("#restore-file", bk); pg.wait_for_timeout(500)
        check(tag + "復元で戻る", "テスト会社" in pg.inner_text("main"))
        # 壊れたバックアップ
        bad = os.path.join(tempfile.gettempdir(), "bad_kmc.json"); open(bad, "w").write("{oops")
        pg.set_input_files("#restore-file", bad); pg.wait_for_timeout(300)
        check(tag + "壊れたバックアップを拒否", "テスト会社" in pg.inner_text("main"))
        # 株価CSV
        pg.click(".tab:has-text('銘柄・テーマ')"); pg.fill("#s-code", "7203"); pg.click("button:has-text('この銘柄を開く')")
        check(tag + "株価未取得表示", "未取得" in pg.inner_text("main"))
        rows = ["日付,始値,高値,安値,終値,出来高"]
        import datetime as dt
        d0 = dt.date(2026, 9, 1); n = 0; d = d0
        while n < 30:
            if d.weekday() < 5:
                n += 1; rows.append("%s,100,101,99,%d,%d" % (d.isoformat(), 100 + n, 1000 if n < 30 else 5000))
            d += dt.timedelta(days=1)
        csvp = os.path.join(tempfile.gettempdir(), "p_kmc.csv"); open(csvp, "w", encoding="utf-8").write("\n".join(rows))
        pg.set_input_files("#csv-file", csvp); pg.wait_for_timeout(400)
        t = pg.inner_text("main")
        check(tag + "出来高比 5.00倍", "5.00倍" in t, t[:300])
        check(tag + "比較期間(20日分)", "20日分" in t)
        check(tag + "チャート", pg.locator("svg.chart").count() == 1)
        check(tag + "推奨・仕手の断定文言なし", "推奨" not in t and "仕手株です" not in t)
        # 分割
        pg.fill("#split-date", "2026-09-20"); pg.click("button:has-text('株式分割日を登録')"); pg.wait_for_timeout(200)
        t = pg.inner_text("main")
        check(tag + "分割で比較不可", "分割" in t and "比較できません" in t)
        # テーマ
        pg.click("button:has-text('← 一覧へ')"); pg.click(".seg button:has-text('テーマ')")
        t = pg.inner_text("main")
        check(tag + "テーマ5種", all(x in t for x in ["地震", "防災", "電力", "半導体", "全固体電池"]))
        check(tag + "関係の区別", "事業上の関係" in t and "株価が反応しただけ" in t)
        pg.click("button:has-text('突発材料')")
        check(tag + "ニュース未接続表示", "未接続" in pg.inner_text("main"))
        ctx.close()
    b.close()

print("\nページエラー:", errors[:5])
print("失敗:", fails)
sys.exit(1 if (fails or errors) else 0)
