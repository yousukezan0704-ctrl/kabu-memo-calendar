"""TDnet(適時開示)の新着を集めて、予定・変更点を抽出する。

使い方:  python collector/collect.py --days 3 --budget 150
 - 一覧は非公式の無料API(やのしん TDnet WebAPI)から取得。公式の有料APIは使わない。
 - 本文(PDF)は release.tdnet.info の公開ファイルを取得。1秒あけて取得する。
 - 取得上限(--budget)を超えた分は「未処理」のまま残し、次回以降に回す。課金は発生しない。
 - 秘密情報は不要。
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))
try:
    from history import classify_title
    from financials import parse_summary_zip, merge_period
    from history import earnings_history
    from financials import parse_revision_zip
    FIN_OK = True
except ImportError:  # 財務モジュール未導入でもIR収集は動く
    FIN_OK = False

    def classify_title(t):
        return 'その他'
from extract import extract_document, merge_events, is_correction, keep_event, EXT_VERSION  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data")
STATE = os.path.join(ROOT, "state", "seen.json")
WATCH = os.path.join(ROOT, "config", "watchlist.txt")
FIN_DIR = os.path.join(DATA, "financials")
HIST_DIR = os.path.join(DATA, "history")
API = "https://webapi.yanoshin.jp/webapi/tdnet/list/%s.json?limit=%d"
UA = "kabu-memo-calendar/1.0 (personal use; polite 1req/sec)"
JST = dt.timezone(dt.timedelta(hours=9))

# 本文を優先して読むタイトル語（予定・変更が書かれやすいもの）
PRIORITY = [
    (r"修正", 30), (r"決算発表|決算説明", 25), (r"決算短信", 20), (r"発売|販売開始|開始", 20),
    (r"承認|治験|開発", 20), (r"量産|工場|設備|稼働", 20), (r"提携|受注|進出|取得|自己株式", 18),
    (r"延期|中止|変更", 22), (r"配当", 15), (r"訂正", 22),
]
SKIP_TITLE = re.compile(r"コーポレート・ガバナンス|株主総会招集|議決権|大量保有|人事|役員|定款の一部変更")   # 「定款の定めに基づく自己株式の取得」(月次の取得状況)は対象外にしない


def http_get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)  # 書き込み途中で壊れないように置き換える


def watchlist():
    try:
        with open(WATCH, encoding="utf-8") as f:
            return {l.split("#")[0].strip().upper() for l in f if l.split("#")[0].strip()}
    except OSError:
        return set()


def fetch_index(day):
    raw = http_get(API % (day.strftime("%Y%m%d"), 3000))
    obj = json.loads(raw.decode("utf-8"))
    items = []
    for it in obj.get("items", []):
        t = it.get("Tdnet", {})
        url = t.get("document_url") or ""
        url = url.split("rd.php?", 1)[-1] if "rd.php?" in url else url
        xb = t.get("url_xbrl") or ""
        xb = xb.split("rd.php?", 1)[-1] if "rd.php?" in xb else xb
        items.append({
            "xbrl": xb,
            "id": str(t.get("id")), "code": (t.get("company_code") or "")[:4].upper(),
            "name": t.get("company_name") or "", "pubdate": t.get("pubdate") or "",
            "title": t.get("title") or "", "url": url,
        })
    return items


def score(item, wl):
    if SKIP_TITLE.search(item["title"]):
        return -1
    s = 100 if item["code"] in wl else 0
    for rx, w in PRIORITY:
        if re.search(rx, item["title"]):
            s += w
    return s


def make_actual_event(v, checked_at):
    """決算短信を発表した事実（TDnetの公表日時）。予定ではなく実績として区別する。"""
    d, t = v["pubdate"][:10], v["pubdate"][11:16]
    return {
        "id": "earn:" + v["id"], "kind": "earnings", "kind_label": "決算発表(実績)",
        "code": v["code"], "name": v["name"], "announced_at": v["pubdate"],
        "target": {"raw": v["pubdate"][:16], "start": d, "end": d, "precision": "day", "needs_review": False,
                   "reason": "", "time": t},
        "target_text": v["pubdate"][:16], "time_text": t, "impact_period": "記載なし",
        "summary": "決算短信を発表（実績）: " + v["title"][:40], "quote": v["title"][:140], "page": 1,
        "url": v["url"], "title": v["title"], "checked_at": checked_at, "origin": "official",
        "extractor": EXT_VERSION, "actual": True, "confirmed": True, "needs_review": False,
    }


class ImagePdf(Exception):
    """文字のない(画像だけの)PDF。失敗ではなく『自動では読めない』という別の区分にする。"""


IMPORTANT_IMG = re.compile(r"修正|配当|決算|業績|予想")


def fetch_pdf(url):
    """PDFを取得する。通信の途中切れ(末尾の%%EOFがない)は1回だけやり直す。"""
    last = None
    for _ in range(2):
        data = http_get(url)
        if b"%%EOF" in data[-2048:]:
            return data
        last = len(data)
        time.sleep(1)
    raise IOError("PDFが途中で切れています(%s バイト)" % last)


def make_image_event(v, checked_at):
    """画像だけのPDF: 本文を読めていない。数値や日付は出さず、タイトルと元資料リンクだけの『要確認』にする。"""
    d = v["pubdate"][:10]
    return {
        "id": "img:" + v["id"], "kind": "forecast", "kind_label": "予想変更(画像PDF・本文未確認)",
        "code": v["code"], "name": v["name"], "announced_at": v["pubdate"],
        "target": {"raw": "", "start": None, "end": None, "precision": "unknown", "needs_review": True,
                   "reason": "画像だけのPDFで本文を自動で読めない", "time": None},
        "target_text": "", "time_text": None, "impact_period": "記載なし",
        "summary": "資料が画像だけのため、内容を自動で読めていません（タイトルのみ）: " + v["title"][:50],
        "quote": v["title"][:140], "page": 1, "url": v["url"], "title": v["title"],
        "checked_at": checked_at, "origin": "official", "extractor": EXT_VERSION,
        "confirmed": False, "needs_review": True,
    }


_RV_NAMES = {"sales": ("売上高", "百万円"), "operating_income": ("営業利益", "百万円"),
             "ordinary_income": ("経常利益", "百万円"), "net_income": ("親会社株主に帰属する当期純利益", "百万円"),
             "eps": ("1株当たり当期純利益", "円")}
RV_VER = "xrv-2"   # 修正XBRLの処理を変えたら上げる(再処理のトリガー)
RV_KEY = RV_VER + "/" + EXT_VERSION   # 文章の再抽出(EXT_VERSION更新)のあとも、XBRLで置き換え直す
_RV_KIND = {"up": ("revision_up", "上方修正"), "down": ("revision_down", "下方修正")}
_TEXT_REV_KINDS = ("revision_up", "revision_down", "forecast", "forecast_item")


def _fmt_num(x, eps=False):
    if x is None:
        return None
    return ("{:,.2f}" if eps else "{:,.0f}").format(x)


def xbrl_revision_events(rec, v, checked_at):
    """公式XBRL(tse-rvfc)の『前回予想→今回予想』から、修正イベントと予想数値の行を作る。
    文章を読んだ推測ではなく、開示された数値そのもの。"""
    kind, label = _RV_KIND.get(rec.get("direction"), ("forecast", "予想変更(増減が混在・または判定不能)"))
    period = rec.get("period") or "記載なし"
    scope = rec.get("scope") or ""
    parts = []
    for it in rec.get("items", []):
        if it.get("item") in ("operating_income", "ordinary_income", "net_income", "sales") and it.get("prev") is not None and it.get("new") is not None:
            parts.append("%s %s→%s" % (_RV_NAMES[it["item"]][0], _fmt_num(it["prev"]), _fmt_num(it["new"])))
    base = {"code": v["code"], "name": v["name"], "announced_at": v["pubdate"], "target": None, "target_text": "記載なし",
            "time_text": None, "impact_period": period, "page": 1, "url": v["url"], "title": v["title"],
            "checked_at": checked_at, "origin": "official", "extractor": "xbrl", "history": []}
    main = dict(base, id="xrv:" + v["id"], kind=kind, kind_label=label, confirmed=True, needs_review=False,
                summary="公式の数値データ(XBRL)から[%s・%s]: %s" % (scope, period, "; ".join(parts) or "数値なし"),
                quote="; ".join(parts)[:140], note="公式XBRL(tse-rvfc)の前回発表予想と今回修正予想の数値から作成（文章からの推測ではない）")
    out = [main]

    def rows(scope_name, period_name, items):
        for it in items:
            if it.get("prev") is None or it.get("new") is None:
                continue
            name, unit = _RV_NAMES[it["item"]]
            eps = it["item"] == "eps"
            diff, pct = it.get("diff"), it.get("diff_pct")
            out.append(dict(base, id="xrvi:%s:%s:%s" % (v["id"], period_name, it["item"]), kind="forecast_item",
                            kind_label="予想数値の変更", impact_period=period_name,
                            summary="%s[%s]: 前回 %s%s → 今回 %s%s%s" % (
                                name, period_name, _fmt_num(it["prev"], eps), unit, _fmt_num(it["new"], eps), unit,
                                "（差 %s%s）" % (("%+g" % diff), unit) if diff is not None else ""),
                            item=name, unit=unit, prev=_fmt_num(it["prev"], eps), new=_fmt_num(it["new"], eps), diff=diff,
                            diff_text=("%+.1f%%" % pct) if pct is not None else None,
                            values=[_fmt_num(it["prev"], eps), _fmt_num(it["new"], eps)],
                            verified=True, verify_basis="公式XBRLの前回予想・今回予想の数値（増減は%s）" % (it.get("diff_source") or "不明"),
                            note=None, quote="%s %s %s" % (name, _fmt_num(it["prev"], eps), _fmt_num(it["new"], eps)),
                            confirmed=False, needs_review=False, section=scope_name))

    rows(scope, period, rec.get("items", []))
    for op in rec.get("other_periods") or []:
        rows(op.get("scope") or scope, op.get("period") or "記載なし", op.get("items", []))
    dv = rec.get("dividend") or {}
    q2, ye = dv.get("q2") or {}, dv.get("year_end") or {}
    odd = bool(q2.get("new") and ye.get("new") and not (0.2 <= ye["new"] / q2["new"] <= 5))
    for key, label in (("q2", "第2四半期末"), ("year_end", "期末")):
        d = dv.get(key) or {}
        if d.get("prev") is None or d.get("new") is None:
            continue
        out.append(dict(base, id="xrvd:%s:%s" % (v["id"], key), kind="forecast_item", kind_label="予想数値の変更",
                        impact_period=label, item="1株当たり配当(%s)" % label, unit="円", section="配当",
                        prev=_fmt_num(d["prev"], True), new=_fmt_num(d["new"], True), diff=round(d["new"] - d["prev"], 2),
                        diff_text=None, values=[_fmt_num(d["prev"], True), _fmt_num(d["new"], True)],
                        summary="1株当たり配当[%s]: 前回 %s円 → 今回 %s円" % (label, _fmt_num(d["prev"], True), _fmt_num(d["new"], True)),
                        verified=True, verify_basis="公式XBRLの配当予想の数値（差は計算）", confirmed=False,
                        needs_review=odd,
                        note="第2四半期末と期末の金額の桁が大きく違います。株式分割などの基準の違いかもしれません。元資料で確認してください" if odd else None,
                        quote="配当 %s→%s" % (_fmt_num(d["prev"], True), _fmt_num(d["new"], True))))
    return out


def pdf_pages(data):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    out, bad = [], 0
    for p in r.pages:
        try:
            out.append(p.extract_text() or "")
        except Exception:  # 1ページが壊れていても、読めたページは使う
            out.append("")
            bad += 1
    pdf_pages.unread = bad
    return out


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--budget", type=int, default=150)
    ap.add_argument("--retention-days", type=int, default=60)
    ap.add_argument("--fin-budget", type=int, default=200)
    ap.add_argument("--hist-budget", type=int, default=15)
    ap.add_argument("--rv-budget", type=int, default=60)
    a = ap.parse_args()

    now = dt.datetime.now(JST)
    checked_at = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    seen = load(STATE, {})
    events = load(os.path.join(DATA, "events.json"), {"events": []})["events"]
    wl = watchlist()
    errors = []

    # 1) 一覧(インデックス)取得
    index_ok_days = []
    for i in range(a.days):
        day = (now - dt.timedelta(days=i)).date()
        try:
            items = fetch_index(day)
        except Exception as e:  # ネットワーク失敗は記録して続行
            errors.append("一覧取得失敗 %s: %s" % (day, e))
            continue
        index_ok_days.append(day.isoformat())
        for it in items:
            if it["id"] not in seen:
                seen[it["id"]] = {"status": "pending", "cat": classify_title(it["title"]), **it}
            else:  # 以前の記録に分類・XBRLが無ければ補う（既存の状態は変えない）
                seen[it["id"]].setdefault("xbrl", it.get("xbrl", ""))
                seen[it["id"]].setdefault("cat", classify_title(it["title"]))
        time.sleep(1)

    # 抽出ルールが新しくなったら、読み終えた資料も当て直す（古いルールの項目は捨てる）
    # 元資料がまだ手元にあるものだけ捨てて取り直す。元資料が既に消えている項目（未来の予定など）は残す
    redo = set()
    for v in seen.values():
        if v['status'] == 'done' and v.get('ext') != EXT_VERSION:
            v['status'] = 'pending'
            redo.add(v['url'])
    events = [e for e in events if not (e.get('extractor') != EXT_VERSION and e.get('url') in redo)]
    # 失敗は最大3回まで再挑戦する（一時的な通信エラーや、読み取り部品の不足を直した後に拾えるように）
    for v in seen.values():
        if v["status"] == "failed" and v.get("tries", 1) < 6:
            v["status"] = "pending"
        # 以前は『定款』の語だけで外していた月次の自己株式取得状況などを、新しい対象外ルールで見直す
        if v["status"] == "skipped" and score(v, wl) >= 0:
            v["status"] = "pending"

    # 2) 本文取得（優先度順・上限つき）
    pending = [v for v in seen.values() if v["status"] == "pending"]
    pending.sort(key=lambda v: (-score(v, wl), v["pubdate"]))
    done_now = failed_now = 0
    for v in pending:
        if score(v, wl) < 0:
            v["status"] = "skipped"
            v["note"] = "対象外のタイトル（人事・総会招集・定款変更等）。本文は読んでいない"
            continue
        if done_now + failed_now >= a.budget:
            break
        if not v.get("url"):
            v["status"] = "failed"
            v["note"] = "資料URLなし"
            failed_now += 1
            continue
        try:
            pages = pdf_pages(fetch_pdf(v["url"]))
            text_len = sum(len(p) for p in pages)
            if text_len < 20:
                raise ImagePdf("文字を取り出せない(画像だけのPDF)")
            ctx = {"code": v["code"], "name": v["name"], "pubdate": v["pubdate"], "title": v["title"],
                   "url": v["url"], "checked_at": checked_at, "fy_end_month": None}
            new = extract_document(pages, ctx)
            if is_correction(v["title"]):
                for e in new:
                    e["correction"] = True
            events, _, _ = merge_events(events, new)
            v["status"] = "done"
            v["ext"] = EXT_VERSION
            v["events"] = len(new)
            v["pages"] = len(pages)
            v["checked_at"] = checked_at
            bad = getattr(pdf_pages, "unread", 0)
            if bad:
                v["note"] = "一部のページ(%d/%d)を読み取れませんでした。元資料で確認してください" % (bad, len(pages))
            else:
                v.pop("note", None)
            done_now += 1
        except ImagePdf:
            v["status"] = "image"
            v["note"] = "画像だけのPDFで、本文を自動で読めません。元資料で確認してください"
            v["checked_at"] = checked_at
            if IMPORTANT_IMG.search(v["title"]):
                events, _, _ = merge_events(events, [make_image_event(v, checked_at)])
            done_now += 1
        except Exception as e:
            v["status"] = "failed"
            v["tries"] = v.get("tries", 0) + 1
            v["note"] = "%s: %s" % (type(e).__name__, str(e)[:120])
            v["checked_at"] = checked_at
            failed_now += 1
            errors.append("%s %s %s" % (v["code"], v["title"][:20], v["note"]))
        time.sleep(1)

    # 2b) 決算短信の「発表実績」イベント: TDnetの公表日時そのもの（確定した事実。将来の予定ではない）
    for v in seen.values():
        if v.get("cat") == "決算短信" and v.get("pubdate"):
            ev = make_actual_event(v, checked_at)
            events, _, _ = merge_events(events, [ev])

    # 2c) 決算短信XBRLから財務数値を取り込む（売上・利益・前年同期比・会社予想・配当）
    fin = {"enabled": FIN_OK, "parsed": 0, "failed": 0, "pending": 0}
    if FIN_OK:
        todo = [v for v in seen.values() if v.get("cat") == "決算短信" and v.get("xbrl") and v.get("fin") != "done"
                and v.get("fin_tries", 0) < 3]
        todo.sort(key=lambda v: v["pubdate"], reverse=True)
        n = 0
        for v in todo:
            if n >= a.fin_budget:
                break
            n += 1
            try:
                rec = parse_summary_zip(http_get(v["xbrl"], timeout=60), {
                    "id": v["id"], "code": v["code"], "name": v["name"], "pubdate": v["pubdate"],
                    "title": v["title"], "url": v["url"]})
                if rec is None:
                    v["fin"] = "done"   # 決算短信ではない／サマリーなし。再挑戦しない
                    v["fin_note"] = "財務サマリーなし"
                else:
                    path = os.path.join(FIN_DIR, "%s.json" % v["code"])
                    doc = merge_period(load(path, None), rec, v["code"], v["name"])
                    doc["updated_at"] = checked_at
                    save(path, doc)
                    v["fin"] = "done"
                    fin["parsed"] += 1
            except Exception as e:
                v["fin_tries"] = v.get("fin_tries", 0) + 1
                v["fin_note"] = "%s: %s" % (type(e).__name__, str(e)[:100])
                fin["failed"] += 1
                errors.append("財務 %s %s" % (v["code"], v["fin_note"]))
            time.sleep(1)
        fin["pending"] = sum(1 for v in seen.values() if v.get("cat") == "決算短信" and v.get("xbrl") and v.get("fin") != "done" and v.get("fin_tries", 0) < 3)

    # 2d) 過去の決算発表日時の履歴（「昨年同期」の参考表示用）。対象は財務データのある会社とウォッチリスト。
    #     1回に取る会社数を絞り、25日たつまで再取得しない。取得に失敗しても既存ファイルは消さない。
    hist = {"enabled": FIN_OK, "fetched": 0, "failed": 0, "targets": 0}
    if FIN_OK:
        codes = {os.path.splitext(f)[0] for f in (os.listdir(FIN_DIR) if os.path.isdir(FIN_DIR) else []) if f.endswith(".json")}
        codes |= {c for c in wl if re.fullmatch(r"[0-9]{3}[0-9A-Z]", c)}
        hist["targets"] = len(codes)
        limit = (now - dt.timedelta(days=25)).strftime("%Y-%m-%d")
        todo = []
        for c in sorted(codes):
            old = load(os.path.join(HIST_DIR, "%s.json" % c), None)
            if not old or str(old.get("updated_at", ""))[:10] < limit:
                todo.append((str(old.get("updated_at", "")) if old else "", c))
        todo.sort()
        for _, c in todo[:a.hist_budget]:
            try:
                data = json.loads(http_get(API % (c, 300)).decode("utf-8"))
                items = [it.get("Tdnet", it) for it in data.get("items", [])]
                eh = earnings_history(items)[:16]
                if not eh and not items:
                    raise ValueError("一覧が空")
                save(os.path.join(HIST_DIR, "%s.json" % c), {
                    "code": c, "updated_at": checked_at, "source": "TDnet由来(非公式API経由・利用条件は未確認)",
                    "items": [{k: h.get(k) for k in ("pubdate", "period_type", "fiscal_label", "correction")} for h in eh]})
                hist["fetched"] += 1
            except Exception as e:
                hist["failed"] += 1
                errors.append("履歴 %s %s: %s" % (c, type(e).__name__, str(e)[:80]))
            time.sleep(1)

    # 2e) 業績予想の修正通知の公式XBRL(tse-rvfc): 画像PDFや文章から読めなかったものを補い、文章からの抽出と方向を照合する
    rv = {"enabled": FIN_OK, "parsed": 0, "added": 0, "checked_match": 0, "checked_mismatch": 0, "failed": 0}
    if FIN_OK:
        todo = [v for v in seen.values() if v.get("cat") == "業績修正" and v.get("xbrl") and v.get("rv") != RV_KEY
                and v.get("rv_tries", 0) < 3]
        todo.sort(key=lambda v: v["pubdate"], reverse=True)
        for v in todo[:a.rv_budget]:
            try:
                rec = parse_revision_zip(http_get(v["xbrl"], timeout=60), {
                    "id": v["id"], "code": v["code"], "name": v["name"], "pubdate": v["pubdate"],
                    "title": v["title"], "url": v["url"]})
                v["rv"] = RV_KEY
                if rec is None:
                    v["rv_note"] = "修正XBRLを読めない／対象外"
                else:
                    rv["parsed"] += 1
                    mine = [e for e in events if e.get("url") == v["url"] and e.get("kind") in _TEXT_REV_KINDS
                            and e.get("extractor") != "xbrl" and not str(e.get("id", "")).startswith("img:")]
                    # 方向の照合結果を数える(置き換える前に、文章からの抽出が正しかったかの目安になる)
                    want = {"up": "revision_up", "down": "revision_down"}.get(rec.get("direction"))
                    for e in mine:
                        if e["kind"] in ("revision_up", "revision_down") and want:
                            if e["kind"] == want:
                                rv["checked_match"] += 1
                            else:
                                rv["checked_mismatch"] += 1
                                errors.append("修正の方向不一致 %s %s" % (v["code"], v["title"][:20]))
                    # 公式XBRLを正とし、同じ通知の文章由来の修正イベントは置き換える(表の読み違い・別の表の混入を避ける)
                    drop = {id(e) for e in mine}
                    events = [e for e in events if id(e) not in drop and e.get("id") != "img:" + v["id"]]
                    events, _, _ = merge_events(events, xbrl_revision_events(rec, v, checked_at))
                    rv["added"] += 1
            except Exception as e:
                v["rv_tries"] = v.get("rv_tries", 0) + 1
                rv["failed"] += 1
                errors.append("修正XBRL %s %s: %s" % (v["code"], type(e).__name__, str(e)[:80]))
            time.sleep(1)

    # 3) 古いものを整理して保存
    cutoff = (now - dt.timedelta(days=a.retention_days)).strftime("%Y-%m-%d")
    seen = {k: v for k, v in seen.items() if v["pubdate"][:10] >= cutoff}
    # 古いIRを整理しても、これからの予定（発売・量産など）と、根拠(原文・URL)つきの項目は消さない
    events = [e for e in events if keep_event(e, cutoff, now.strftime("%Y-%m-%d"))]
    cnt = {"pending": 0, "done": 0, "failed": 0, "skipped": 0, "image": 0}
    for v in seen.values():
        cnt[v["status"]] = cnt.get(v["status"], 0) + 1
    listed = len(seen)
    complete = listed > 0 and cnt["skipped"] == 0 and cnt["image"] == 0 and cnt["pending"] == 0 and cnt["failed"] == 0 and len(index_ok_days) == a.days
    status = {
        "generated_at": checked_at,
        "is_sample": False,
        "range": {"days": a.days, "index_ok_days": sorted(index_ok_days)},
        "listed": listed, "done": cnt["done"], "pending": cnt["pending"],
        "failed": cnt["failed"], "skipped": cnt["skipped"], "image": cnt["image"],
        "complete": complete,  # 全件を全文精査できたときだけ True
        "period": {"from": min((v["pubdate"][:10] for v in seen.values()), default=None),
                   "to": max((v["pubdate"][:10] for v in seen.values()), default=None)},
        "oldest_pending": min((v["pubdate"][:10] for v in seen.values() if v["status"] == "pending"), default=None),
        "budget_per_run": a.budget,
        "financials": fin,
        "history": hist,
        "revisions_xbrl": rv,
        "last_run": {"at": checked_at, "ok": len(index_ok_days) > 0, "trigger": os.environ.get("GITHUB_EVENT_NAME", "local"),
                     "error": None if index_ok_days else "一覧を1日分も取得できませんでした: " + "; ".join(errors[:3])},
        "source_terms": "明確な許諾は未確認（やのしんは「情報収集・分析目的」とのみ記載、頻度制限・再配布の規定なし。JPX側の規約は確認できず）。個人利用・差分のみ・1秒間隔で運用し、停止指示があれば止める",
        "source": "TDnet(非公式API: webapi.yanoshin.jp)＋release.tdnet.info の公開PDF",
        "errors": errors[:30],
    }
    index_items = [{k: v.get(k) for k in ("id", "code", "name", "pubdate", "title", "url", "cat", "status", "note", "events", "pages", "checked_at")}
                   for v in sorted(seen.values(), key=lambda v: v["pubdate"], reverse=True)
                   if v["status"] in ("done", "failed", "image") or score(v, wl) >= 20]
    save(STATE, seen)
    save(os.path.join(DATA, "events.json"), {"generated_at": checked_at, "events": events})
    save(os.path.join(DATA, "ir_index.json"), {"generated_at": checked_at, "items": index_items[:3000]})
    save(os.path.join(DATA, "status.json"), status)
    print(json.dumps({k: status[k] for k in ("listed", "done", "pending", "failed", "skipped", "complete")}, ensure_ascii=False))
    if not index_ok_days:
        raise SystemExit("一覧を1日分も取得できませんでした（取得元の停止・通信失敗の可能性）")


def main():
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:  # 想定外の失敗も、公開画面で原因が分かるように記録してから失敗終了する
        st = load(os.path.join(DATA, "status.json"), {})
        st["last_run"] = {"at": dt.datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00"), "ok": False,
                          "trigger": os.environ.get("GITHUB_EVENT_NAME", "local"), "error": "%s: %s" % (type(e).__name__, str(e)[:300])}
        save(os.path.join(DATA, "status.json"), st)
        raise


if __name__ == "__main__":
    main()
