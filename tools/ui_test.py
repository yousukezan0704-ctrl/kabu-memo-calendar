"""画面の動作テスト（Edge を自動操作）。python tools/ui_test.py
一時フォルダの配信サーバー経由で docs を開くので、本物のデータや保存先には触れない。"""
import http.server, threading, os, sys, json, tempfile, functools
import datetime as dt
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
def openfold(pg, text):
    """折りたたみ(<details>)の見出しを探して、閉じていれば開く"""
    sm = pg.locator("summary:has-text('%s')" % text).first
    if sm.evaluate("e => !e.parentElement.open"):
        sm.click()

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
        check(tag + "サンプル表示", "サンプル" in pg.text_content("main"))
        check(tag + "時期別の予定欄", "時期別の予定" in pg.inner_text("main"))
        check(tag + "時期別の予定は初期は閉じている", pg.locator("details[data-key=bucket]").evaluate("e => !e.open"))
        check(tag + "月の各日は点と件数(バーなし)", pg.locator(".cell .dots i").count() >= 1 and pg.locator(".cell .cnt").count() >= 1 and pg.locator(".mini").count() == 0)
        check(tag + "月の点は1日3個まで", pg.evaluate("[...document.querySelectorAll('.cell .dots')].every(d => d.children.length <= 3)"))
        check(tag + "絞り込みは折りたたみ(初期は閉)", pg.locator("details[data-key=filter]").evaluate("e => !e.open"))
        # 件数の多い日(実データの11/2)を選ぶ
        pg.evaluate("KMC.ui.cursor = '2026-11-01'; KMC.render()"); pg.wait_for_timeout(100)
        pg.click(".cell[data-date='2026-11-02']"); pg.wait_for_timeout(200)
        ng = pg.locator(".daypanel details.grp").count()
        check(tag + "多い日は種類グループに分かれる", ng >= 3, ng)
        okopen = pg.evaluate("[...document.querySelectorAll('.daypanel details.grp[open] > summary')].every(s => /決算|自分の確認/.test(s.textContent))")
        check(tag + "グループは初期は閉(決算と自分の確認だけ開く)", okopen)
        hh = pg.evaluate("document.documentElement.scrollHeight")
        print("INFO %s カレンダー(11/2選択・初期) 画面の高さ=%dpx" % (tag, hh))
        check(tag + "11/2の画面が長すぎない", hh < 6000, hh)
        gl = pg.locator(".daypanel details.grp > summary").first
        gl.click(); pg.wait_for_timeout(100)
        check(tag + "グループを開くとカードが見える", pg.locator(".daypanel details.grp[open] article.card").count() >= 1)
        pg.evaluate("KMC.ui.selected = KMC.today(); KMC.ui.cursor = KMC.today().slice(0,7) + '-01'; KMC.render()")
        pg.click("button:has-text('一覧')"); pg.wait_for_timeout(200)
        check(tag + "一覧に決算が出る", "決算" in pg.inner_text("main"))
        check(tag + "一覧は日付ごとの見出し", pg.locator("h4.dh").count() >= 1)
        # IR
        pg.click(".tab:has-text('重要IR')"); pg.wait_for_timeout(300)
        t = pg.inner_text("main")
        check(tag + "取得状況が出る", "取得状況" in t and "未処理" in t)
        check(tag + "未完了の警告", "完了していません" in t)
        check(tag + "根拠は初期は閉じている", pg.locator("article blockquote").first.is_hidden())
        pg.locator("article summary:has-text('根拠を見る')").first.click()
        check(tag + "根拠原文とページ", "該当ページ" in pg.inner_text("main") and "最終確認" in pg.inner_text("main"))
        # ---- すっきり整理の確認（折りたたみ・コンパクトなカード）----
        check(tag + "取得状況は1行の要約", "件中" in t and "読了" in t and "自動取得" in t, t[:300])
        check(tag + "取得状況の詳細は折りたたみ", pg.locator("details[data-key=cov-detail]").evaluate("e => !e.open"))
        hh = pg.evaluate("document.documentElement.scrollHeight")
        print("INFO %s 重要IR(初期表示) 画面の高さ=%dpx" % (tag, hh))
        check(tag + "重要IRの画面が長すぎない", hh < 12000, hh)
        check(tag + "IRカードは初期20件まで", pg.locator("main article.card").count() <= 20)
        check(tag + "カード1行目に種類と会社", pg.locator("main article.card .l1 .chip").count() >= 1 and pg.locator("main article.card .l3").count() >= 1)
        check(tag + "絞り込みは初期は閉じている", pg.locator("details[data-key=filter]").evaluate("e => !e.open") and "絞り込み中" not in pg.inner_text("main"))
        openfold(pg, "絞り込み")
        pg.fill("#f-text", "サンプル"); pg.wait_for_timeout(200)
        check(tag + "入力しても折りたたみが閉じない", pg.locator("details[data-key=filter]").evaluate("e => e.open"))
        check(tag + "絞り込み中の表示", "絞り込み中" in pg.inner_text("summary:has-text('絞り込み')"))
        pg.fill("#f-text", "")
        # 決算発表の予定（サンプル=架空データで確認）
        pg.click("button:has-text('決算発表の予定')"); pg.wait_for_timeout(200)
        t = pg.inner_text("main")
        check(tag + "決算予定の一覧が出る", "決算発表の予定（今後）" in t and pg.locator("table.earn tbody tr").count() >= 3, t[:200])
        check(tag + "時刻なしは未公表", "未公表" in pg.inner_text("table.earn") and "15:00" in pg.inner_text("table.earn"))
        check(tag + "決算予定がサンプルと明記", "サンプル" in pg.inner_text("table.earn"))
        dates = pg.eval_on_selector_all("table.earn tbody tr td:first-child b", "els => els.map(e => e.textContent)")
        check(tag + "決算予定は日付順", len(dates) >= 3 and dates == sorted(dates, key=lambda x: (int(x.split('月')[0]), int(x.split('月')[1].split('日')[0]))), dates)
        # 予想の比較
        pg.click("button:has-text('予想の比較')"); pg.wait_for_timeout(200)
        t = pg.inner_text("main")
        check(tag + "予想比較の表", pg.locator("table.cmp").count() >= 1 and "前回予想" in pg.text_content("table.cmp") and "今回予想" in pg.text_content("table.cmp"), t[:200])
        check(tag + "未確認行は原文で確認", pg.locator("table.cmp tr.unver").count() >= 1 and "原文で確認" in t)
        check(tag + "差の表示(増減)", pg.locator("table.cmp .up").count() >= 1 and pg.locator("table.cmp .down").count() >= 1)
        check(tag + "実データの予想比較も出る", pg.locator("table.cmp tbody tr").count() > 6)
        check(tag + "予想比較で横スクロールなし", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
        if vp["width"] < 500:
            hs = pg.evaluate("[...document.querySelectorAll('.irsub button, .tab, main button')].filter(b=>b.offsetParent).map(b=>b.getBoundingClientRect().height)")
            check(tag + "ボタンの高さ44px以上", min(hs) >= 43.5, min(hs))
            check(tag + "本文の文字16px以上", pg.evaluate("parseFloat(getComputedStyle(document.body).fontSize)") >= 16)
        # 新フィールド(note/verify_basis/section/diff_text/impact_period)の表示
        pg.evaluate("""() => { var s = KMC.data.sample.events;
          s.push(Object.assign({}, s.filter(e => e.kind === 'forecast_item')[0], {id: 'sample-nf', item: '幅テスト項目', prev: '10〜12', new: '11〜13', diff: null,
            diff_text: '＋1（下限・上限とも）', verified: false, note: '注記テスト文', verify_basis: '列の見出しによる', section: '連結業績予想', impact_period: '通期'}));
          s.push(Object.assign({}, s.filter(e => e.kind === 'forecast_item')[0], {id: 'sample-nf2', item: '根拠テスト', verified: true, verify_basis: '列の見出しによる'}));
          KMC.render(); }""")
        pg.wait_for_timeout(200)
        ct = pg.text_content("main")
        check(tag + "注記(note)表示", "注記テスト文" in ct)
        check(tag + "diff_text表示", "＋1（下限・上限とも）" in ct)
        check(tag + "対象期間・見出し・確認の根拠", "対象期間: 通期" in ct and "見出し: 連結業績予想" in ct and "確認の根拠: 列の見出しによる" in ct)
        check(tag + "根拠の区別", "列の見出しで確認" in ct and "差額が一致" in ct)
        pg.click("button:has-text('すべて')"); pg.wait_for_timeout(200)
        t = pg.inner_text("main")
        ct = pg.text_content("main")
        check(tag + "種類ごとの注意書き", "種類ごとの注意" in t and "誤りが残る可能性" in ct and "自社株買い" in ct)
        openfold(pg, "絞り込み"); pg.fill("#f-text", "サンプル"); pg.wait_for_timeout(200)
        check(tag + "カードに自動抽出・要確認バッジ", pg.locator("article .badge:has-text('自動抽出・要確認')").count() >= 1)
        pg.fill("#f-text", "")
        pg.reload(); pg.wait_for_selector(".tab"); pg.click(".tab:has-text('重要IR')")
        # unit・表由来の修正イベント・note
        pg.evaluate("""() => { var s = KMC.data.sample.events;
          s.push(Object.assign({}, s.filter(e => e.kind === 'forecast_item')[0], {id: 'sample-un', item: '単位テスト[通期]', prev: '123', new: '456', diff: 333, unit: '億円', verified: true, note: null}));
          s.push(Object.assign({}, s.filter(e => e.kind === 'revision_up')[0], {id: 'sample-table-r', note: '表の数値から機械的に判定テスト', name: '表由来テスト社'}));
          s.push(Object.assign({}, s.filter(e => e.kind === 'earnings')[0], {id: 'sample-tn', note: '短信注記テスト', name: '短信注記社'}));
          KMC.render(); }""")
        pg.wait_for_timeout(200)
        pg.click("button:has-text('予想の比較')"); pg.wait_for_timeout(200)
        check(tag + "unit表示", "456億円" in "".join(pg.text_content("main").split()))
        pg.click("button:has-text('すべて')"); openfold(pg, "絞り込み"); pg.fill("#f-text", "表由来テスト"); pg.wait_for_timeout(200)
        t = pg.inner_text("main")
        check(tag + "表の数値から判定バッジ+note", "表の数値から判定" in t and "表の数値から機械的に判定テスト" in t, t[-300:])
        pg.fill("#f-text", "短信注記"); pg.wait_for_timeout(200)
        check(tag + "カードのnote表示", "短信注記テスト" in pg.inner_text("main"))
        pg.fill("#f-text", "")
        # 自動更新の失敗・停止の表示（画面内の状態だけ差し替える。実データは変えない）
        real = json.load(open(os.path.join(DOCS, "data", "status.json"), encoding="utf-8"))
        def with_status(st):
            pg.evaluate("st => { KMC.data.status = st; KMC.render(); }", st); pg.wait_for_timeout(200)
        now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
        bad = dict(real, generated_at=now, last_run={"at": now, "ok": False, "trigger": "schedule", "error": "テスト用の失敗"})
        with_status(bad)
        check(tag + "失敗の表示", "自動取得は失敗しました" in pg.inner_text("main") and "テスト用の失敗" in pg.inner_text("main"))
        old = dict(real, generated_at=(dt.datetime.now() - dt.timedelta(days=9)).isoformat(timespec="seconds"), last_run={"at": now, "ok": True, "trigger": "schedule", "error": None})
        with_status(old)
        check(tag + "停止の表示", "止まっている可能性" in pg.inner_text("main"))
        pg.click(".tab:has-text('カレンダー')")
        check(tag + "カレンダー側にも警告", "止まっている可能性" in pg.inner_text("main"))
        pg.click(".tab:has-text('重要IR')")
        with_status(dict(real, generated_at=now, last_run=None))
        pg.click("button:has-text('すべて')")
        check(tag + "last_runなしでも壊れない", "取得状況" in pg.inner_text("main") and "表示でエラー" not in pg.inner_text("main") and "止まっている可能性" not in pg.inner_text("main"))
        pg.evaluate("KMC.loadData().then(() => KMC.render())"); pg.wait_for_timeout(300)
        pg.click("button:has-text('すべて')")
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
        openfold(pg, "通知")
        with pg.expect_download() as dl:
            pg.click("button:has-text('.ics')")
        ics = open(dl.value.path(), encoding="utf-8").read()
        check(tag + "ics に VALARM", "VALARM" in ics and "テスト会社" in ics)
        # バックアップ→復元
        openfold(pg, "バックアップと復元")
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
        openfold(pg, "株価データの取り込み")
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
        pg.click("button:has-text('← 一覧へ')"); pg.click(".subtabs button:has-text('テーマ')")
        t = pg.text_content("main")
        check(tag + "テーマ5種", all(x in t for x in ["地震", "防災", "電力", "半導体", "全固体電池"]))
        check(tag + "関係の区別", "事業上の関係" in t and "株価が反応しただけ" in t)
        pg.click(".subtabs button:has-text('突発材料')")
        check(tag + "ニュース未接続表示", "未接続" in pg.inner_text("main"))
        ctx.close()
    b.close()

print("\nページエラー:", errors[:5])
print("失敗:", fails)
sys.exit(1 if (fails or errors) else 0)
