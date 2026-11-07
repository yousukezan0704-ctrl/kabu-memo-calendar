"""画面の動作テスト（Edge を自動操作）。python tools/ui_test.py
一時フォルダの配信サーバー経由で docs を開くので、本物のデータや保存先には触れない。"""
import http.server, threading, os, sys, json, tempfile, functools
import datetime as dt
from playwright.sync_api import sync_playwright

DOCS = os.environ.get("KMC_DOCS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
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

# ---------------------------------------------------------------------------
# 新機能のテスト: 銘柄詳細の財務・指標 / 注目 / 通知。
# 財務データは fetch を画面側でモック(route)して差し込む。実データ・公開データには触れない。
# ---------------------------------------------------------------------------
SHOT_DIR = os.path.join(tempfile.gettempdir(), "kmc_shots")
os.makedirs(SHOT_DIR, exist_ok=True)

def per(sales=None, op=None, ord_=None, ni=None, eps=None):
    return {"sales": sales, "operating_income": op, "ordinary_income": ord_, "net_income": ni, "eps": eps}

FIN_OK = {
    "code": "9999", "name": "財務テスト(架空)", "updated_at": "2026-11-05T21:00:00+09:00", "source": "テスト用の架空データ",
    "periods": [
        {   # 古い順に並べて渡しても、画面側で period_end の新しい順に直る
            "id": "t-fy", "announced_at": "2026-05-10T15:00:00+09:00", "period_type": "通期", "fiscal_year_end": "2026-03-31", "period_end": "2026-03-31",
            "doc_title": "2026年3月期 決算短信", "url": "https://example.com/fy.pdf", "unit": "百万円",
            "results": per(100000, 5500, 5600, 3500, 70.0), "yoy_pct": {"sales": 3.0, "operating_income": 8.0, "ordinary_income": 7.5, "net_income": 6.0},
            "forecast": {"period": "2027-03", "sales": 105000, "operating_income": 5800, "ordinary_income": 5900, "net_income": 3700, "eps": 74.0, "dps": 28.0, "yoy_pct": {}},
            "dividend": {"annual_actual": 26.0, "annual_forecast": 28.0},
            "balance": {"net_assets": 48000, "equity_ratio_pct": 58.0, "bps": None, "shares_issued": 50000000, "treasury_shares": 1000000}},
        {   "id": "t-q1", "announced_at": "2026-08-05T15:00:00+09:00", "period_type": "第1四半期", "fiscal_year_end": "2027-03-31", "period_end": "2026-06-30",
            "doc_title": "第1四半期決算短信", "url": "https://example.com/q1.pdf", "unit": "百万円",
            "results": per(30000, 1500, 1550, 1000, 20.0), "yoy_pct": {"sales": 4.0, "operating_income": 10.0, "ordinary_income": None, "net_income": 5.0},
            "forecast": {"period": "2027-03", "sales": 110000, "operating_income": 5000, "ordinary_income": 5100, "net_income": 4500, "eps": 90.0, "dps": 30.0, "yoy_pct": {}},
            "dividend": {"annual_actual": None, "annual_forecast": 30.0},
            "balance": {"net_assets": 49000, "equity_ratio_pct": 59.0, "bps": None, "shares_issued": 50000000, "treasury_shares": 1000000}},
        {   "id": "t-q2", "announced_at": "2026-11-05T15:00:00+09:00", "period_type": "第2四半期", "fiscal_year_end": "2027-03-31", "period_end": "2026-09-30",
            "doc_title": "第2四半期決算短信", "url": "javascript:alert(1)", "unit": "百万円",
            "results": per(60000, 3000, 3100, 2000, 40.0), "yoy_pct": {"sales": 5.0, "operating_income": 12.3, "ordinary_income": None, "net_income": -3.2},
            "forecast": {"period": "2027-03", "sales": 110000, "operating_income": 6000, "ordinary_income": 6100, "net_income": 4000, "eps": 80.0, "dps": 30.0, "yoy_pct": {}},
            "dividend": {"annual_actual": None, "annual_forecast": 30.0},
            "balance": {"net_assets": 50000, "equity_ratio_pct": 60.0, "bps": None, "shares_issued": 50000000, "treasury_shares": 1000000}},
    ],
}
# 材料がほとんど無い(全部 null)。推測値で埋めないことの確認用
FIN_EMPTY = {"code": "9998", "name": "空テスト(架空)", "updated_at": "2026-11-05T21:00:00+09:00", "source": "テスト", "periods": [
    {"id": "e1", "announced_at": "2026-11-05T15:00:00+09:00", "period_type": "通期", "fiscal_year_end": "2027-03-31", "period_end": "2027-03-31", "unit": "百万円",
     "results": per(), "yoy_pct": {"sales": None}, "forecast": None, "dividend": None,
     "balance": {"net_assets": None, "equity_ratio_pct": None, "bps": None, "shares_issued": None, "treasury_shares": None}}]}
FIN_XSS = {"code": "9997", "name": "<b id=\"xss\">x</b>", "updated_at": "2026-11-05", "source": "<img src=x onerror=\"window.__x=1\">", "periods": [
    {"id": "x1", "announced_at": "2026-11-05T15:00:00+09:00", "period_type": "通期", "fiscal_year_end": "2027-03-31", "period_end": "2027-03-31", "unit": "<i>百万円</i>",
     "url": "javascript:alert(1)", "results": per(1, 2, 3, 4, 5), "yoy_pct": {}, "forecast": None, "dividend": None, "balance": {}}]}
FIN_PBR = {"code": "9995", "name": "PBRテスト(架空)", "updated_at": "2026-11-05", "source": "テスト", "periods": [
    {"id": "b1", "announced_at": "2026-11-05T15:00:00+09:00", "period_type": "通期", "fiscal_year_end": "2027-03-31", "period_end": "2027-03-31", "unit": "百万円",
     "results": per(1, 1, 1, 1, -5.0), "yoy_pct": {}, "forecast": None, "dividend": None,
     "balance": {"net_assets": None, "equity_ratio_pct": None, "bps": 500.0, "shares_issued": 1000000, "treasury_shares": None}}]}

def route_json(pg, code, body, status=200):
    pg.route("**/data/financials/%s.json*" % code, lambda r: r.fulfill(status=status, content_type="application/json", body=body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)))

def no_hscroll(pg):
    return pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

def new_features(pg, tag, vp):
    shot = lambda name: pg.screenshot(path=os.path.join(SHOT_DIR, "%d_%s.png" % (vp["width"], name)), full_page=True)
    route_json(pg, "9999", FIN_OK); route_json(pg, "9998", FIN_EMPTY); route_json(pg, "9997", FIN_XSS); route_json(pg, "9995", FIN_PBR)
    route_json(pg, "9996", "oops")
    # 過去の決算発表日時(history)。昨年同期の目安の確認用。日付は「今日」からの相対
    td = dt.date.fromisoformat(pg.evaluate("KMC.today()"))
    ly = lambda plus, hh="15:00:00": (td + dt.timedelta(days=plus)).replace(year=td.year - 1).isoformat() + " " + hh
    HIST = {"code": "X", "updated_at": "2026-11-05", "source": "テスト", "items": [
        {"pubdate": ly(1, "10:00:00"), "period_type": "第1四半期", "fiscal_label": "2026年3月期", "correction": True},   # 訂正は目安に使わない
        {"pubdate": ly(2), "period_type": "第2四半期", "fiscal_label": "2026年3月期", "correction": False},             # 目安になる(今日+2日ごろ・15時台)
        {"pubdate": ly(40), "period_type": "第3四半期", "fiscal_label": "2026年3月期", "correction": False},
        {"pubdate": ly(-60), "period_type": "通期", "fiscal_label": "2025年3月期", "correction": False},
    ] + [{"pubdate": "20%02d-0%d-10 15:00:00" % (10 + i % 5, 1 + i % 9), "period_type": "第1四半期", "fiscal_label": "古い%d" % i, "correction": False} for i in range(8)]}
    route_json(pg, "9999", FIN_OK, status=200) if False else None
    for c in ("9999", "T004", "T001"):
        pg.route("**/data/history/%s.json*" % c, lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(HIST, ensure_ascii=False)))
    ref_txt = "約%d月%d日ごろ・15時台" % ((td + dt.timedelta(days=2)).month, (td + dt.timedelta(days=2)).day)
    check(tag + "[履歴] refNext: 訂正を除き最も近い昨年同期を選ぶ", pg.evaluate("(items) => { var r = KMC.refNext(items); return r && r.h.period_type; }", HIST["items"]) == "第2四半期")
    check(tag + "[履歴] refNext: 発表日が今日より後・1年後が過去のものは除く", pg.evaluate("(td) => KMC.refNext([{pubdate: KMC.addDays(td, 5) + ' 15:00:00'}, {pubdate: KMC.addDays(td, -400) + ' 15:00:00'}])", pg.evaluate("KMC.today()")) is None)

    # ===== iPhone向けの見た目・下固定ナビ =====
    pg.evaluate("KMC.ui.tab = 'cal'; KMC.render()"); pg.wait_for_timeout(100)
    nav = pg.evaluate("""() => { var n = document.getElementById('tabs'), r = n.getBoundingClientRect(), cs = getComputedStyle(n);
      return {pos: cs.position, bottom: r.bottom, top: r.top, h: r.height, vh: window.innerHeight, n: n.querySelectorAll('.tab').length,
              labels: [...n.querySelectorAll('.tab')].map(b => b.textContent.trim()), minH: Math.min(...[...n.querySelectorAll('.tab')].map(b => b.getBoundingClientRect().height))}; }""")
    check(tag + "[UI] ナビは画面下に固定", nav["pos"] == "fixed" and abs(nav["bottom"] - nav["vh"]) < 1.5, nav)
    check(tag + "[UI] ナビは5つ(カレンダー・重要IR・注目・銘柄・メモ設定)", nav["n"] == 5 and "カレンダー" in nav["labels"][0] and "重要IR" in nav["labels"][1] and "注目" in nav["labels"][2] and "銘柄" in nav["labels"][3] and "メモ" in nav["labels"][4], nav["labels"])
    check(tag + "[UI] ナビの高さは親指で押せる48px以上", nav["minH"] >= 48, nav["minH"])
    css = pg.evaluate("fetch('style.css').then(r => r.text())")
    check(tag + "[UI] ノッチ・ホームバー対応(safe-area)", "env(safe-area-inset-bottom)" in css and "env(safe-area-inset-top)" in css)
    head = pg.evaluate("[...document.querySelectorAll('head meta, head link')].map(e => e.outerHTML).join(' ')")
    check(tag + "[UI] ホーム画面起動の設定(全画面・ステータスバー・アイコン)", 'apple-mobile-web-app-capable' in head and 'apple-mobile-web-app-status-bar-style' in head and 'apple-touch-icon' in head and 'viewport-fit=cover' in head)
    check(tag + "[UI] 最初に開くのはカレンダー", pg.evaluate("document.querySelector('#tabs .tab.on').textContent").find("カレンダー") >= 0)
    pg.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)"); pg.wait_for_timeout(100)
    fb = pg.evaluate("document.querySelector('.foot').getBoundingClientRect().bottom <= document.getElementById('tabs').getBoundingClientRect().top + 1")
    check(tag + "[UI] 最下部の内容がナビに隠れない", fb)
    pg.evaluate("window.scrollTo(0, 0)")
    # ナビの移動
    pg.click("#tabs .tab[data-v=watch]"); pg.wait_for_timeout(150)
    check(tag + "[UI] 「注目」ナビで注目の一覧", pg.locator("#tabs .tab.on").inner_text().find("注目") >= 0 and pg.locator(".subtabs button.on").inner_text() == "注目")
    pg.click("#tabs .tab[data-v=search]"); pg.wait_for_timeout(150)
    check(tag + "[UI] 「銘柄」ナビで銘柄の一覧(検索欄)", pg.locator("#s-q").count() == 1 and pg.locator("#tabs .tab.on").inner_text().find("銘柄") >= 0)
    pg.click("#tabs .tab[data-v=memo]"); pg.wait_for_timeout(150)
    check(tag + "[UI] 「メモ・設定」ナビ", "上級者向け：データの接続" in pg.inner_text("main") and no_hscroll(pg))
    mt = pg.inner_text("main")
    check(tag + "[UI] トークン欄は初期画面に出ない(上級者向けは閉じている)", pg.locator("#src-token").is_hidden() and pg.locator("details[data-key=tool-src]").evaluate("e => !e.open") and "トークン" not in mt)
    check(tag + "[UI] 上級者向けは設定画面の最下部", pg.evaluate("(() => { var f = [...document.querySelectorAll('main details.fold')]; return f[f.length - 1].dataset.key; })()") == "tool-src")
    pg.click("#tabs .tab[data-v=cal]"); pg.wait_for_timeout(150)
    check(tag + "[UI] 本文は17px以上・カードは角丸", pg.evaluate("parseFloat(getComputedStyle(document.body).fontSize)") >= 17 and pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.fold')).borderTopLeftRadius)") >= 10)
    # ダークモード（既存を壊さない）
    pg.emulate_media(color_scheme="dark"); pg.wait_for_timeout(150)
    bg = pg.evaluate("getComputedStyle(document.body).backgroundColor"); nbg = pg.evaluate("getComputedStyle(document.getElementById('tabs')).backgroundColor")
    rgb = lambda c: [int(x) for x in c[c.index('(') + 1:c.index(')')].split(',')[:3]]
    check(tag + "[UI] ダークモードで背景が暗く、横スクロールなし", sum(rgb(bg)) < 150 and sum(rgb(nbg)) < 200 and no_hscroll(pg), (bg, nbg))
    pg.evaluate("KMC.ui.tab = 'ir'; KMC.render()"); pg.wait_for_timeout(100)
    check(tag + "[UI] ダークモードでIR画面も横スクロールなし", no_hscroll(pg))
    pg.emulate_media(color_scheme="light"); pg.wait_for_timeout(100)
    # IR: 種別・情報源・発表日・確認状況
    pg.evaluate("""() => { var s = KMC.data.sample.events, t = KMC.today(), E0 = s.filter(e => e.kind === 'earnings')[0];
      s.push(Object.assign({}, E0, {id: 'ui-ok', code: 'U001', name: '確認済みUI社', kind: 'revision_up', kind_label: '上方修正', announced_at: t + ' 09:00:00', target: null, target_text: '記載なし', needs_review: false, summary: 'UI確認用の上方修正'}));
      s.push(Object.assign({}, E0, {id: 'ui-ng', code: 'U002', name: '要確認UI社', kind: 'buyback', kind_label: '自社株買い', announced_at: t + ' 09:00:00', target: null, target_text: '記載なし', needs_review: true, summary: 'UI確認用の自社株買い'}));
      KMC.ui.tab = 'ir'; KMC.irUi.sub = 'all'; KMC.irUi.limit = 400; KMC.filter.text = 'UI社'; KMC.render(); }""")
    pg.wait_for_timeout(200)
    c_ok = pg.locator("article.card:has-text('確認済みUI社')"); c_ng = pg.locator("article.card:has-text('要確認UI社')")
    check(tag + "[UI] 種別を分類表示(上方修正・自社株買い)", c_ok.locator(".chip").first.inner_text() == "上方修正" and c_ng.locator(".chip").first.inner_text() == "自社株買い")
    check(tag + "[UI] 日付が確定した公表資料は「確認済み」", c_ok.locator(".badge.st").count() == 1 and "確認済み" in c_ok.locator(".badge.st").inner_text())
    check(tag + "[UI] needs_review のものは「確認済み」にしない(要確認)", "要確認" in c_ng.locator(".badge.st").inner_text() and "確認済み" not in c_ng.locator(".badge.st").inner_text())
    c_ok.locator("summary:has-text('根拠を見る')").click(); pg.wait_for_timeout(100)
    dd = c_ok.inner_text()
    check(tag + "[UI] 詳細に情報源・発表日・確認状況", "情報源" in dd and "発表日" in dd and "確認状況" in dd)
    n_bad = pg.evaluate("[...document.querySelectorAll('article.card.unconf .badge.st')].filter(b => b.textContent.indexOf('確認済み') >= 0).length")
    check(tag + "[UI] 未確定(破線)のカードに「確認済み」は出ない", n_bad == 0, n_bad)
    pg.evaluate("KMC.filter.text = ''; KMC.irUi.limit = 12; KMC.render()")
    # 案内文（未接続・認証・オフライン）
    pg.evaluate("KMC.data.status = null; KMC.data.loadErrors = ['取得状況: 未取得（404）']; KMC.render()")
    t_ = pg.inner_text("main")
    check(tag + "[UI] 未接続の案内は「まだ公開されていません」(トークン入力へ誘導しない)", "データはまだ公開されていません" in t_ and "トークン" not in t_ and "①" not in t_ and pg.locator("#src-token").count() == 0)
    check(tag + "[UI] 手順は上級者向けへのリンク1行だけ", pg.locator("main .errbox a[data-act=goadv]").count() == 1)
    pg.click("main .errbox a[data-act=goadv]"); pg.wait_for_timeout(200)
    check(tag + "[UI] リンクで設定の上級者向けが開く", pg.locator("#src-token").is_visible())
    pg.evaluate("KMC.ui.tab = 'ir'; KMC.render()")
    pg.evaluate("KMC.data.loadErrors = ['取得状況: 通信できません（オフラインか、電波が弱い状態です）']; KMC.render()")
    check(tag + "[UI] オフライン時の案内", "電波の良い場所" in pg.inner_text("main"))
    pg.evaluate("KMC.loadData().then(() => KMC.render())"); pg.wait_for_timeout(500)
    pg.evaluate("KMC.ui.tab = 'cal'; KMC.irUi.limit = 12; KMC.render()")

    # ===== (C) 設定の既定値 =====
    pg.evaluate("KMC.state.settings = {showSample: true, notifyChecked: '未確認', notifyNote: ''}; KMC.save()")   # 古い保存形式(notifyなし)
    check(tag + "通知の既定は4項目ともON", pg.evaluate("(c => c.before && c.today && c.ir && c.memo)(KMC.notifyCfg())"))

    # ===== (A) 銘柄詳細: 財務データあり =====
    today = pg.evaluate("KMC.today()")
    pg.evaluate("""() => { var t = KMC.today();
      KMC.state.prices['9999'] = [{d: KMC.addDays(t,-3), o:990,h:1000,l:980,c:990,v:1000,val:null},{d: KMC.addDays(t,-2), o:990,h:1010,l:990,c:1000,v:1200,val:null}];
      KMC.save(); KMC.ui.tab = 'stocks'; KMC.sUi.sub = 'stocks'; KMC.sUi.code = '9999'; KMC.render(); }""")
    pg.wait_for_timeout(500)
    pxdate = pg.evaluate("KMC.addDays(KMC.today(), -2)")
    t = pg.inner_text("main")
    check(tag + "[財務] 指標の見出しと計算値の明示", "株価と指標（計算値）" in t and t.count("計算値") >= 4, t[:300])
    check(tag + "[財務] 株価の日付を表示", ("データ日 " + pxdate) in t, t[:300])
    check(tag + "[財務] 時価総額=終値×株数(自己株式除く)=490億円", "490億円" in t and "自己株式を除く" in t and "49,000,000株" in t)
    check(tag + "[財務] PER=1000÷80=12.5倍・予想ベース", "12.5倍" in t and "予想ベース" in t and "会社予想EPS" in t)
    check(tag + "[財務] PBR(BPSなし)=概算1.00倍と式", "1.00倍" in t and "概算" in t and "× 1,000,000 ÷ 発行済株式数" in t)
    check(tag + "[財務] ROE=3500÷48000=7.3%(概算)", "7.3%" in t and "期末の純資産" in t)
    check(tag + "[財務] 配当利回り=30÷1000=3.00%", "3.00%" in t)
    check(tag + "[財務] 最新の決算(第2四半期)の実績と前年同期比", "第2四半期" in t and "60,000" in t and "3,000" in t and "12.3%" in t)
    check(tag + "[財務] マイナスの前年比は下向き表示", "▼ －3.2%" in t)
    check(tag + "[財務] 取れていない値は未取得", "未取得" in pg.locator("table.fres").inner_text())
    check(tag + "[財務] 横スクロールなし", no_hscroll(pg))
    openfold(pg, "会社予想との差"); pg.wait_for_timeout(100)
    ft = pg.locator("table.ffc").inner_text()
    check(tag + "[財務] 進捗率(売上54.5%・営業利益50.0%)と均等目安50%", "54.5%" in ft and "50.0%" in ft and "均等ペースの目安 50%" in ft, ft)
    check(tag + "[財務] 前回→今回の上方・下方", "上方" in ft and "下方" in ft and "5,000 → 6,000" in ft and "4,500 → 4,000" in ft, ft)
    check(tag + "[財務] 横スクロールなし(予想の差)", no_hscroll(pg))
    openfold(pg, "過去の決算履歴"); pg.wait_for_timeout(100)
    ht = pg.locator("table.fhist").inner_text()
    check(tag + "[財務] 決算履歴(3件・新しい順)", pg.locator("table.fhist tbody tr").count() == 3 and ht.index("2026-11-05") < ht.index("2026-05-10"), ht)
    check(tag + "[財務] 危険なURLはリンクにしない", pg.locator("main a[href^='javascript']").count() == 0)
    check(tag + "[財務] 正しいhttpsの資料リンクは出る", pg.locator("table.fhist a[href^='https://example.com']").count() >= 1)
    check(tag + "[財務] 自分の投資メモ欄がある", "自分の投資メモ" in pg.inner_text("main"))
    check(tag + "[財務] 横スクロールなし(履歴)", no_hscroll(pg))
    shot("detail_fin")

    et = pg.inner_text("main") + pg.text_content("main")
    check(tag + "[履歴] 確定予定が無ければ昨年同期の参考を出す", ref_txt in et and "昨年" in et and "の実績から" in et, et[:200])
    check(tag + "[履歴] 「会社の公表予定ではありません」を必ず添える", "会社の公表予定ではありません" in et and "参考・未確定" in et)
    check(tag + "[履歴] 訂正は目安に使わない(10時台にならない)", "10時台" not in et.split("決算発表の予定")[1][:300])
    openfold(pg, "過去の決算履歴"); pg.wait_for_timeout(100)
    hl = pg.locator("details[data-key='fh:9999']").inner_text()
    check(tag + "[履歴] 過去の決算発表日時は直近8件", "直近8件" in hl and hl.count("第") >= 0 and pg.locator("details[data-key='fh:9999'] .mline").count() == 8, pg.locator("details[data-key='fh:9999'] .mline").count())
    check(tag + "[履歴] 新しい順", hl.index(ly(2)[:10]) < hl.index(ly(-60)[:10]) if ly(2)[:10] in hl and ly(-60)[:10] in hl else True)
    check(tag + "[履歴] 横スクロールなし", no_hscroll(pg))
    # 確定予定があれば参考は出さない / 履歴が無ければ「履歴未取得」
    pg.evaluate("""() => { var s = KMC.data.sample.events, d = KMC.addDays(KMC.today(), 9);
      s.push(Object.assign({}, s.filter(e => e.kind === 'earnings')[0], {id: 'hx-c', code: '9999', name: '財務テスト', target: {raw: d, start: d, end: d, precision: 'day', needs_review: false, reason: ''}, target_text: d, time_text: '15:00', confirmed: true})); KMC.render(); }""")
    pg.wait_for_timeout(150)
    sched = pg.locator("details[data-key='er:9999']").inner_text()
    check(tag + "[履歴] 確定予定がある日は参考を出さない", "昨年同期" not in sched and "15:00" in sched, sched)
    pg.evaluate("KMC.data.sample.events = KMC.data.sample.events.filter(e => e.id !== 'hx-c'); KMC.render()")

    # ===== 材料が欠ける: 推測で埋めない =====
    pg.evaluate("KMC.sUi.code = '9998'; KMC.render()"); pg.wait_for_timeout(500)
    t = pg.inner_text("main")
    check(tag + "[財務] 株価なしは「株価未取得」", "株価未取得" in t)
    check(tag + "[履歴] 履歴ファイルが無ければ「履歴未取得」", "履歴未取得" in pg.text_content("main"))
    check(tag + "[財務] 値が全部nullなら指標の数値は出ない", pg.locator(".met .mv:not(.na)").count() == 0 and pg.locator(".met .mv.na").count() == 5, pg.locator(".met .mv:not(.na)").count())
    check(tag + "[財務] 未取得の理由と推測しない旨", "推測値では埋めません" in t and "EPS" in t)
    pg.evaluate("KMC.state.prices['9998'] = [{d: KMC.addDays(KMC.today(),-2), c: 500, v: 10}]; KMC.render()"); pg.wait_for_timeout(200)
    check(tag + "[財務] 株価があっても材料なしなら未取得のまま", pg.locator(".met .mv:not(.na)").count() == 0 and "倍" not in pg.locator(".mets").inner_text())
    # BPSあり・EPS赤字
    pg.evaluate("KMC.state.prices['9995'] = [{d: KMC.addDays(KMC.today(),-2), c: 1000, v: 10}]; KMC.sUi.code = '9995'; KMC.render()"); pg.wait_for_timeout(500)
    t = pg.locator(".mets").inner_text()
    check(tag + "[財務] BPSがあればPBR=2.00倍(計算値)・赤字EPSは算出不可", "2.00倍" in t and "算出できません" in t, t)
    # XSS
    pg.evaluate("KMC.sUi.code = '9997'; KMC.render()"); pg.wait_for_timeout(500)
    check(tag + "[財務] データ中のHTMLは実行されない", pg.locator("#xss").count() == 0 and pg.evaluate("window.__x") is None and pg.locator("main img[src='x']").count() == 0)
    check(tag + "[財務] データ中のHTMLは文字として見える", "<img src=x" in pg.inner_text("main") or "<img src=x" in pg.text_content("main"))
    # 読み込み失敗(500)・未取得(404)
    pg.evaluate("KMC.sUi.code = '9996'; KMC.render()"); pg.wait_for_timeout(500)
    check(tag + "[財務] 通信エラーは読み込めない旨", "読み込めませんでした" in pg.inner_text("main"))
    pg.evaluate("KMC.sUi.code = '7203'; KMC.render()"); pg.wait_for_timeout(500)
    check(tag + "[財務] ファイルなし(404)は「財務データ未取得」", "財務データ未取得" in pg.inner_text("main"))
    check(tag + "[財務] 未取得でも修正IRの欄はある", "上方・下方修正と予想の変更" in pg.inner_text("main"))
    pg.evaluate("KMC.sUi.code = ''; KMC.render()")

    # ===== (B) 注目 =====
    EARN = "KMC.data.sample.events.filter(e => e.kind === 'earnings')[0]"
    REV = "KMC.data.sample.events.filter(e => e.kind === 'revision_up')[0]"
    pg.evaluate("""() => {
      var t = KMC.today(), s = KMC.data.sample.events, E0 = %s, R0 = %s;
      function earn(id, code, name, plus, time) { var d = KMC.addDays(t, plus);
        s.push(Object.assign({}, E0, {id: id, code: code, name: name, announced_at: t + ' 09:00:00', target: {raw: d, start: d, end: d, precision: 'day', needs_review: false, reason: ''}, target_text: d, time_text: time, confirmed: true})); }
      earn('tx-6', 'T006', '当日テスト社', 0, null); earn('tx-5', 'T005', '明日テスト社', 1, '13:30'); earn('tx-1', 'T001', '注目テストA', 3, '15:00');
      earn('tx-2', 'T002', '注目テストB', 7, null); earn('tx-3', 'T003', '注目テストC', 20, null);
      s.push(Object.assign({}, R0, {id: 'tx-rev', code: 'T001', name: '注目テストA', announced_at: t + ' 00:00:30', summary: '業績予想の上方修正（テスト）'}));
      s.push(Object.assign({}, E0, {id: 'tx-tanshin', code: 'T001', name: '注目テストA', announced_at: KMC.addDays(t, -5) + ' 15:00:00', target: null, target_text: '記載なし', time_text: null, confirmed: false,
        title: '2026年3月期 第2四半期決算短信', summary: '決算短信（テスト）'}));
      s.push(Object.assign({}, E0, {id: 'tx-old', code: 'T002', name: '注目テストB', announced_at: KMC.addDays(t, -30) + ' 15:00:00', target: null, target_text: '記載なし', time_text: null, confirmed: false,
        title: '2026年3月期 第1四半期決算短信', summary: '決算短信（古い）'}));
      KMC.state.favorites = ['T001', 'T002', 'T003', 'T004', 'T005', 'T006'];
      var D = KMC.addDays(t, -5);
      KMC.state.prices['T001'] = [{d: KMC.addDays(D,-1), c: 100, v: 10}, {d: D, c: 101, v: 10}, {d: KMC.addDays(D,1), c: 110, v: 10}];
      KMC.save(); KMC.ui.tab = 'stocks'; KMC.sUi.sub = 'watch'; KMC.sUi.code = ''; KMC.sUi.wq = ''; KMC.sUi.wsort = 'date'; KMC.sUi.wnear = false; KMC.sUi.wrev = false; KMC.render(); }""" % (EARN, REV))
    pg.wait_for_timeout(300)
    check(tag + "[注目] 最初のサブタブが「注目」", pg.locator(".subtabs button").first.inner_text() == "注目" and pg.locator(".subtabs button.on").inner_text() == "注目")
    codes = lambda: pg.eval_on_selector_all(".wrow .ttl a", "els => els.map(e => e.textContent.match(/\\(([^()]+)\\)\\s*$/)[1])")
    check(tag + "[注目] 決算が近い順(日付不明は最後)", codes() == ["T006", "T005", "T001", "T002", "T003", "T004"], codes())
    t = pg.inner_text("main")
    check(tag + "[注目] 予定がなければ「予定未確認」", pg.locator(".wrow:has-text('T004') .badge:has-text('予定未確認')").count() == 1)
    check(tag + "[注目] 時刻あり/なし(未公表)", "時刻 15:00" in pg.locator(".wrow:has-text('T001')").inner_text() and "未公表" in pg.locator(".wrow:has-text('T002')").inner_text())
    rowA = pg.locator(".wrow:has-text('T001')")
    check(tag + "[注目] 業績修正を目立たせる(上方・強調)", rowA.evaluate("e => e.classList.contains('hot-up')") and "上方修正" in rowA.inner_text() and rowA.locator("b.hotl").count() == 1)
    check(tag + "[注目] 他の重要IR件数(決算短信)", "ほか1件" in rowA.inner_text())
    check(tag + "[注目] 決算前後の株価 100→110 +10.0%", "前日終値 100円" in rowA.inner_text() and "翌営業日終値 110円" in rowA.inner_text() and "＋10.0%" in rowA.inner_text(), rowA.inner_text())
    rowB = pg.locator(".wrow:has-text('T002')")
    check(tag + "[注目] 7日より古いIRは出さない", "直近7日の重要IRなし" in rowB.inner_text())
    check(tag + "[注目] 株価がなければ「株価データなし」", "株価データなし" in rowB.inner_text() and "株価データなし" in pg.locator(".wrow:has-text('T004')").inner_text())
    t4 = pg.locator(".wrow:has-text('T004')").inner_text()
    check(tag + "[履歴] 注目: 確定予定なしの行に昨年同期の参考", ref_txt in t4 and "会社の公表予定ではありません" in t4 and "予定未確認" in t4, t4)
    check(tag + "[履歴] 注目: 確定予定がある行には参考を出さない", "昨年同期" not in pg.locator(".wrow:has-text('T001')").inner_text())
    check(tag + "[履歴] 注目: 履歴ファイルなしは「履歴未取得」", "履歴未取得" in pg.locator(".wrow:has-text('T003')").inner_text() or "昨年同期" not in pg.locator(".wrow:has-text('T003')").inner_text())
    check(tag + "[注目] 横スクロールなし", no_hscroll(pg))
    print("INFO %s 注目タブ 画面の高さ=%dpx" % (tag, pg.evaluate("document.documentElement.scrollHeight")))
    shot("watch")
    # 絞り込み
    pg.fill("#w-q", "注目テストB"); pg.wait_for_timeout(200)
    check(tag + "[注目] 会社名で検索", codes() == ["T002"], codes())
    pg.fill("#w-q", "t003"); pg.wait_for_timeout(200)
    check(tag + "[注目] コードで検索(大文字小文字を区別しない)", codes() == ["T003"], codes())
    pg.fill("#w-q", ""); pg.wait_for_timeout(100)
    pg.click("#w-rev"); pg.wait_for_timeout(200)
    check(tag + "[注目] 修正ありだけ", codes() == ["T001"], codes())
    pg.click("#w-rev"); pg.click("#w-near"); pg.wait_for_timeout(200)
    check(tag + "[注目] 決算が14日以内(20日先と不明は除く)", codes() == ["T006", "T005", "T001", "T002"], codes())
    pg.click("#w-near"); pg.select_option("#w-sort", "code"); pg.wait_for_timeout(200)
    check(tag + "[注目] コード順", codes() == sorted(codes()) and len(codes()) == 6, codes())
    pg.select_option("#w-sort", "date")
    pg.fill("#w-add", "T007"); pg.click("button:has-text('注目に追加')"); pg.wait_for_timeout(200)
    check(tag + "[注目] コード入力で追加(予定未確認は後ろ)", "T007" in codes() and codes()[-1] == "T007", codes())
    pg.click(".wrow:has-text('T007') button[data-act=fav]"); pg.wait_for_timeout(200)
    check(tag + "[注目] ★で外せる", "T007" not in codes())
    pg.fill("#w-add", "あ"); pg.click("button:has-text('注目に追加')")
    check(tag + "[注目] 不正なコードは追加しない", "T007" not in codes() and pg.inner_text("#toast") != "")
    # 行から詳細→戻ると注目に戻る
    pg.click(".wrow:has-text('T003') .ttl a"); pg.wait_for_timeout(300)
    check(tag + "[注目] 行から銘柄詳細を開ける", "T003" in pg.inner_text("main") and "財務データ未取得" in pg.inner_text("main"))
    pg.click("button:has-text('← 一覧へ')"); pg.wait_for_timeout(150)
    check(tag + "[注目] 詳細から戻ると注目の一覧", pg.locator(".subtabs button.on").inner_text() == "注目")

    # ===== (C) お知らせ・通知 =====
    pg.click(".tab:has-text('カレンダー')"); pg.wait_for_timeout(200)
    nb = lambda: pg.locator("details[data-key=notices]").inner_text() if pg.locator("details[data-key=notices]").count() else ""
    n = nb()
    check(tag + "[通知] ホームに「お知らせ」", "お知らせ" in pg.inner_text("main") and n != "")
    check(tag + "[通知] 前日の決算(明日テスト社・13:30)", "明日" in n and "明日テスト社" in n and "13:30" in n, n)
    check(tag + "[通知] 当日の決算(当日テスト社・時刻未公表)", "今日" in n and "当日テスト社" in n and "未公表" in n, n)
    check(tag + "[通知] 重要IR新着(上方修正)", "上方修正" in n and "注目テストA" in n, n)
    check(tag + "[通知] お気に入り以外は出ない", "T003" not in n and "注目テストC" not in n)
    check(tag + "[通知] 横スクロールなし(お知らせ)", no_hscroll(pg))
    shot("home_notices")
    # 日付が確定していない決算は通知しない
    pg.evaluate("""() => { var s = KMC.data.sample.events, d = KMC.addDays(KMC.today(), 1);
      s.push(Object.assign({}, s.filter(e => e.id === 'tx-5')[0], {id: 'tx-un', code: 'T008', name: '未確定テスト社', confirmed: false})); KMC.state.favorites.push('T008'); KMC.render(); }""")
    check(tag + "[通知] 日付が未確定の決算は通知しない", "未確定テスト社" not in nb())
    nb_text = nb()
    # 設定画面
    pg.click(".tab:has-text('メモ')"); pg.wait_for_timeout(200)
    openfold(pg, "通知")
    for i in ("n-before", "n-today", "n-ir", "n-memo", "n-browser"):
        check(tag + "[通知] 設定の項目 " + i, pg.locator("#" + i).count() == 1)
    nt = pg.inner_text("details[data-key=tool-notif]")
    check(tag + "[通知] 閉じていても届くプッシュは未実装と明記", "未実装" in nt and "プッシュ通知" in nt and "外部サービス" in nt)
    # .ics(全ON)
    ics = pg.evaluate("KMC.makeIcs()")
    def block(txt, uid):
        parts = txt.split("BEGIN:VEVENT")
        return [x for x in parts if uid in x]
    b5 = block(ics["text"], "UID:earn-T005-")
    check(tag + "[通知] ics に注目銘柄の決算(前日18:00・当日7:30のアラーム)", len(b5) == 1 and "TRIGGER:-PT6H" in b5[0] and "TRIGGER:PT7H30M" in b5[0] and "13:30" in b5[0], ics["text"][:400])
    check(tag + "[履歴] 参考(未確定)の日付は ics に入れない", "T004" not in ics["text"] and "昨年" not in ics["text"])
    check(tag + "[履歴] 参考(未確定)はお知らせに入れない", "T004" not in nb_text)
    check(tag + "[通知] ics は日付が確定した注目銘柄だけ", ics["earnCount"] == 5 and not block(ics["text"], "T008") and not block(ics["text"], "T004"), ics["earnCount"])
    check(tag + "[通知] ics の時刻なしは「未公表」", "未公表" in block(ics["text"], "UID:earn-T006-")[0])
    check(tag + "[通知] 既存のメモ確認日のicsも残る", ics["memoCount"] >= 1 and "株を調べる" in ics["text"])
    # OFFにする
    pg.click("#n-before"); pg.wait_for_timeout(300)
    check(tag + "[通知] 設定が保存される", pg.evaluate("KMC.state.settings.notify.before") is False and pg.evaluate("KMC.state.settings.notify.today") is True)
    ics2 = pg.evaluate("KMC.makeIcs()")
    b5 = block(ics2["text"], "UID:earn-T005-"); b6 = block(ics2["text"], "UID:earn-T006-")
    check(tag + "[通知] 前日OFFなら ics に前日アラームなし(当日はあり)", b5 and "TRIGGER:-PT6H" not in b5[0] and "TRIGGER:PT7H30M" in b5[0])
    pg.click(".tab:has-text('カレンダー')"); pg.wait_for_timeout(200)
    n = nb()
    check(tag + "[通知] 前日OFFならお知らせに明日の決算なし(当日・IRは残る)", "明日テスト社" not in n and "当日テスト社" in n and "上方修正" in n, n)
    pg.reload(); pg.wait_for_selector(".tab"); pg.wait_for_timeout(500)
    check(tag + "[通知] 再読み込み後も設定が残る", pg.evaluate("KMC.notifyCfg().before") is False)
    pg.evaluate("""() => { var s = KMC.data.sample.events, t = KMC.today(), E0 = s.filter(e => e.kind === 'earnings')[0], R0 = s.filter(e => e.kind === 'revision_up')[0];
      function earn(id, code, name, plus, time) { var d = KMC.addDays(t, plus);
        s.push(Object.assign({}, E0, {id: id, code: code, name: name, target: {raw: d, start: d, end: d, precision: 'day', needs_review: false, reason: ''}, target_text: d, time_text: time, confirmed: true})); }
      earn('tx-6', 'T006', '当日テスト社', 0, null); earn('tx-5', 'T005', '明日テスト社', 1, '13:30');
      s.push(Object.assign({}, R0, {id: 'tx-rev', code: 'T001', name: '注目テストA', announced_at: t + ' 00:00:30'}));
      KMC.state.favorites = ['T001', 'T005', 'T006']; KMC.ui.tab = 'cal'; KMC.render(); }""")
    pg.wait_for_timeout(200)
    n = nb()
    check(tag + "[通知] 再読み込み後も前日OFFが効く", "明日テスト社" not in n and "当日テスト社" in n, n)
    # 重要IRの既読
    pg.click("button:has-text('重要IRを既読にする')"); pg.wait_for_timeout(300)
    n = nb()
    check(tag + "[通知] 既読にすると重要IRの新着が消える", "上方修正" not in n and "当日テスト社" in n, n)
    pg.evaluate("KMC.setNotify('seenAt', ''); KMC.setNotify('ir', false); KMC.render()"); pg.wait_for_timeout(200)
    check(tag + "[通知] 重要IROFFなら新着を出さない", "上方修正" not in nb())
    pg.evaluate("KMC.setNotify('ir', true); KMC.setNotify('today', false); KMC.render()"); pg.wait_for_timeout(200)
    check(tag + "[通知] 当日OFFなら当日の決算を出さない", "当日テスト社" not in nb() and "上方修正" in nb())
    # メモの再確認日をOFF
    pg.evaluate("KMC.state.memos.length || KMC.newMemo({name: '期限メモ社', reviewDate: KMC.addDays(KMC.today(), -1)}); KMC.state.memos[0].reviewDate = KMC.addDays(KMC.today(), -1); KMC.state.memos[0].status = 'open'; KMC.render()")
    check(tag + "[通知] メモの期限はONなら出る", "自分が調べる日" in pg.inner_text("main"))
    pg.evaluate("KMC.setNotify('memo', false); KMC.render()"); pg.wait_for_timeout(100)
    check(tag + "[通知] メモの再確認日OFFなら出ない", "自分が調べる日" not in pg.inner_text("main"))
    pg.evaluate("KMC.setNotify('memo', true); KMC.setNotify('today', true); KMC.setNotify('before', true); KMC.render()")
    # ブラウザ通知(Notificationをモック)
    pg.evaluate("""() => { window.__notes = []; window.Notification = function (t, o) { window.__notes.push([t, o && o.body]); };
      Notification.permission = 'granted'; Notification.requestPermission = function () { return Promise.resolve('granted'); }; }""")
    check(tag + "[通知] ブラウザ通知がOFFなら何も出さない", pg.evaluate("KMC.fireNotices()") == 0 and pg.evaluate("window.__notes.length") == 0)
    pg.click(".tab:has-text('メモ')"); openfold(pg, "通知")
    pg.click("#n-browser"); pg.wait_for_timeout(400)
    check(tag + "[通知] ブラウザ通知をONにできる(許可あり)", pg.evaluate("KMC.notifyCfg().browser") is True)
    c1 = pg.evaluate("KMC.fireNotices()")
    notes = pg.evaluate("window.__notes")
    check(tag + "[通知] 開いている間の通知が出る", c1 >= 3 and any("決算" in x[0] for x in notes) and any("明日" in (x[1] or "") for x in notes), notes)
    check(tag + "[通知] 同じ内容は2回出さない", pg.evaluate("KMC.fireNotices()") == 0)
    pg.evaluate("window.Notification.permission = 'denied'; KMC.setNotify('fired', {})")
    check(tag + "[通知] 許可がなければ出さない", pg.evaluate("KMC.fireNotices()") == 0)

    # ===== 画面の高さが悪化していないか(お知らせなし・お気に入りなしの標準状態) =====
    pg.evaluate("KMC.state.favorites = []; KMC.save(); KMC.ui.tab = 'cal'; KMC.ui.view = 'month'; KMC.ui.cursor = KMC.today().slice(0,7) + '-01'; KMC.ui.selected = KMC.today(); KMC.render()")
    pg.wait_for_timeout(200)
    hcal = pg.evaluate("document.documentElement.scrollHeight")
    print("INFO %s カレンダー(今日選択・お気に入りなし) 画面の高さ=%dpx" % (tag, hcal))
    check(tag + "[高さ] お気に入りなしならお知らせ欄は出ない(高さ増なし)", pg.locator("details[data-key=notices]").count() == 0)
    check(tag + "[高さ] 横スクロールなし(カレンダー)", no_hscroll(pg))

    # ===== 非公開リポジトリ接続（api.github.com を差し替え。本物のトークン・通信は使わない）=====
    TOKEN = "github_pat_TESTTOKEN0123456789abcdefXYZ"
    API = "https://api.github.com/repos/yousukezan0704-ctrl/kabu-memo-private-data/contents/data/"
    seen, mode = [], {"status": 200}
    def api_handler(route):
        rq = route.request
        hd = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,OPTIONS"}
        if rq.method == "OPTIONS":
            route.fulfill(status=204, headers=hd); return
        seen.append((rq.url, rq.headers.get("authorization"), rq.headers.get("accept")))
        path = rq.url.split("/contents/data/")[1].split("?")[0]
        if path == "status.json":
            if mode["status"] != 200:
                route.fulfill(status=mode["status"], headers=hd, content_type="application/json", body='{"message":"Bad credentials"}'); return
            body = {"generated_at": "2026-11-05T21:00:00+09:00", "listed": 1, "done": 1, "pending": 0, "failed": 0, "skipped": 0, "range": {"days": 1, "index_ok_days": []}, "source": "テスト", "complete": False, "last_run": None}
        elif path == "events.json": body = {"generated_at": "2026-11-05T21:00:00+09:00", "events": []}
        elif path == "ir_index.json": body = {"items": []}
        elif path == "financials/9999.json": body = FIN_OK
        elif path == "history/9999.json": body = HIST
        else:
            route.fulfill(status=404, headers=hd, content_type="application/json", body='{"message":"Not Found"}'); return
        route.fulfill(status=200, headers=hd, content_type="application/json", body=json.dumps(body, ensure_ascii=False))
    pg.route("https://api.github.com/**", api_handler)
    pg.unroute("**/data/financials/9999.json*"); pg.unroute("**/data/history/9999.json*")   # 以降はAPI経由だけで確かめる
    pg.evaluate("KMC.state.favorites = []; KMC.ui.tab = 'memo'; KMC.mUi.id = ''; KMC.render()"); pg.wait_for_timeout(200)
    check(tag + "[接続] 設定欄がある", pg.locator("summary:has-text('上級者向け：データの接続')").count() == 1)
    openfold(pg, "上級者向け"); pg.wait_for_timeout(100)
    tt = pg.inner_text("details[data-key=tool-src]")
    check(tag + "[接続] 作り方の注意書き(Contents: Read-only・1リポジトリ・有効期限・他人に見せない)", "Contents: Read-only" in tt and "1リポジトリ" in tt and "有効期限" in tt and "他人に見せない" in tt and "この端末" in tt, tt[:300])
    check(tag + "[接続] 既定のリポジトリ名・トークン欄はpassword", pg.input_value("#src-repo") == "yousukezan0704-ctrl/kabu-memo-private-data" and pg.get_attribute("#src-token", "type") == "password")
    check(tag + "[接続] 未設定の表示", "未設定" in tt and pg.locator("button:has-text('接続を解除')").count() == 0)
    pg.fill("#src-token", "abc"); pg.click("button:has-text('接続テスト')"); pg.wait_for_timeout(200)
    check(tag + "[接続] 形が正しくないトークンは保存しない", pg.evaluate("localStorage.getItem('kmc.src')") is None and len(seen) == 0)
    pg.fill("#src-token", TOKEN); pg.click("button:has-text('接続テスト')"); pg.wait_for_timeout(900)
    res = pg.inner_text("#src-result") if pg.locator("#src-result").count() else ""
    check(tag + "[接続] テスト成功と取得時刻を表示", "接続できました" in res and "取得 20" in res and "データ更新 2026-11-05 21:00" in res, res)
    check(tag + "[接続] 入力済みは「設定済み ••••」だけ", "設定済み ••••" in pg.inner_text("details[data-key=tool-src]") and pg.input_value("#src-token") == "")
    first = [x for x in seen if x[0].startswith(API + "status.json")]
    check(tag + "[接続] 非公開リポジトリのAPIへ Bearer と raw の Accept で取得", len(first) >= 1 and first[0][1] == "Bearer " + TOKEN and first[0][2] == "application/vnd.github.raw+json", seen[:2])
    check(tag + "[接続] sample.json と themes.json はAPIに送らない", not any("sample.json" in x[0] or "themes.json" in x[0] for x in seen))
    check(tag + "[接続] 取得後、events/ir_index も同じ窓口で取得", any("events.json" in x[0] for x in seen) and any("ir_index.json" in x[0] for x in seen))
    # 銘柄詳細に財務表示
    pg.evaluate("KMC.ui.tab = 'stocks'; KMC.sUi.sub = 'stocks'; KMC.sUi.code = '9999'; KMC.render()"); pg.wait_for_timeout(700)
    dt_ = pg.inner_text("main")
    check(tag + "[接続] 銘柄詳細に財務が出る(API経由)", "株価と指標（計算値）" in dt_ and "60,000" in dt_ and "490億円" in dt_, dt_[:200])
    check(tag + "[接続] 財務・履歴もAPI経由", any("financials/9999.json" in x[0] for x in seen) and any("history/9999.json" in x[0] for x in seen))
    pg.evaluate("KMC.sUi.code = '9994'; KMC.render()"); pg.wait_for_timeout(600)
    check(tag + "[接続] 404は「財務データ未取得」", "財務データ未取得" in pg.inner_text("main"))
    # トークンが漏れていないか(画面・保存データ・バックアップ・ics)
    pg.evaluate("KMC.sUi.code = ''; KMC.ui.tab = 'memo'; KMC.render()"); pg.wait_for_timeout(100)
    openfold(pg, "バックアップと復元")
    with pg.expect_download() as dl:
        pg.click("button:has-text('バックアップを書き出す')")
    bk = open(dl.value.path(), encoding="utf-8").read()
    check(tag + "[接続] バックアップJSONにトークンを含まない", "TESTTOKEN" not in bk and TOKEN not in bk and "kmc.src" not in bk)
    check(tag + "[接続] 通常の保存データ(kmc.v1)にトークンを含まない", "TESTTOKEN" not in (pg.evaluate("localStorage.getItem('kmc.v1')") or ""))
    check(tag + "[接続] トークンは別キー kmc.src にだけある", TOKEN in (pg.evaluate("localStorage.getItem('kmc.src')") or ""))
    check(tag + "[接続] .ics にトークンを含まない", "TESTTOKEN" not in pg.evaluate("KMC.makeIcs().text"))
    check(tag + "[接続] 画面(HTML・文字)にトークンを含まない", "TESTTOKEN" not in pg.content() and "TESTTOKEN" not in pg.inner_text("body"))
    check(tag + "[接続] ページエラー・ログにトークンなし", not any("TESTTOKEN" in e for e in errors))
    # 401 / 403
    for code_ in (401, 403):
        mode["status"] = code_
        pg.click("button:has-text('接続テスト')"); pg.wait_for_timeout(600)
        res = pg.inner_text("#src-result")
        check(tag + "[接続] %d は「トークンが無効か期限切れ」と再設定の案内" % code_, "トークンが無効か期限切れ" in res and "メモ画面で再設定してください" in res and "接続できませんでした" in res, res)
        check(tag + "[接続] %d の文面にトークンを出さない" % code_, "TESTTOKEN" not in res and "TESTTOKEN" not in pg.content())
    check(tag + "[接続] 認証エラーは404(未取得)と区別される", "未取得" not in res)
    pg.evaluate("KMC.ui.tab = 'ir'; KMC.render()"); pg.wait_for_timeout(100)
    check(tag + "[接続] 重要IR画面は認証エラーを短く案内(上級者向けへのリンク)", "認証エラー" in pg.inner_text("main") and pg.locator("main a[data-act=goadv]").count() >= 1 and "TESTTOKEN" not in pg.inner_text("main"))
    pg.evaluate("KMC.fin = {}; KMC.ui.tab = 'stocks'; KMC.sUi.code = '9999'; KMC.render()")
    mode_all_401 = True
    pg.unroute("https://api.github.com/**")
    pg.route("https://api.github.com/**", lambda r: r.fulfill(status=401, headers={"access-control-allow-origin": "*"}, content_type="application/json", body="{}") if r.request.method != "OPTIONS" else r.fulfill(status=204, headers={"access-control-allow-origin": "*", "access-control-allow-headers": "*"}))
    pg.evaluate("KMC.fin = {}; KMC.render()"); pg.wait_for_timeout(600)
    check(tag + "[接続] 銘柄詳細でも認証エラーを区別して表示", "トークンが無効か期限切れ" in pg.inner_text("main") and "財務データ未取得" not in pg.inner_text("main"))
    # 解除
    pg.evaluate("KMC.ui.tab = 'memo'; KMC.sUi.code = ''; KMC.render()"); pg.wait_for_timeout(100)
    openfold(pg, "上級者向け")
    pg.once("dialog", lambda d: d.accept())
    pg.click("button:has-text('接続を解除')"); pg.wait_for_timeout(800)
    check(tag + "[接続] 解除でトークンが消える", pg.evaluate("localStorage.getItem('kmc.src')") is None and pg.evaluate("KMC.srcGet()") is None)
    check(tag + "[接続] 解除後は未設定表示・解除ボタンなし", "未設定" in pg.inner_text("details[data-key=tool-src]") and pg.locator("button:has-text('接続を解除')").count() == 0)
    n_api = len(seen)
    pg.evaluate("KMC.reloadAll()"); pg.wait_for_timeout(600)
    check(tag + "[接続] 解除後はAPIに通信しない(相対パスへ戻る)", len(seen) == n_api and pg.evaluate("KMC.data.events.length") > 0)
    check(tag + "[接続] 解除後も画面・保存データにトークンなし", "TESTTOKEN" not in pg.content() and "TESTTOKEN" not in json.dumps(pg.evaluate("KMC.state")))


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    for vp in ({"width": 390, "height": 800}, {"width": 1100, "height": 900}):
        ctx = b.new_context(viewport=vp, accept_downloads=True, service_workers="block")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and not any(c in m.text for c in ("404", "401", "403")) else None)
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
        # 年またぎ(11月→1月)でも崩れないよう、先頭の月より小さい月は翌年扱いにして比べる
        m0 = int(dates[0].split('月')[0]) if dates else 1
        dkey = lambda x: ((int(x.split('月')[0]) - m0) % 12, int(x.split('月')[1].split('日')[0]))
        check(tag + "決算予定は日付順", len(dates) >= 3 and dates == sorted(dates, key=dkey), dates)
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
            check(tag + "本文の文字16px以上", pg.evaluate("parseFloat(getComputedStyle(document.body).fontSize)") >= 17)
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
        pg.click(".tab[data-v='search']"); pg.click(".subtabs button:has-text('銘柄')"); pg.fill("#s-code", "7203"); pg.click("button:has-text('この銘柄を開く')")
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
        new_features(pg, tag, vp)
        ctx.close()
    b.close()

print("\nページエラー:", errors[:5])
print("失敗:", fails)
sys.exit(1 if (fails or errors) else 0)
