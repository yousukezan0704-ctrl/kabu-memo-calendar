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
from extract import extract_document, merge_events, is_correction, EXT_VERSION  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data")
STATE = os.path.join(ROOT, "state", "seen.json")
WATCH = os.path.join(ROOT, "config", "watchlist.txt")
API = "https://webapi.yanoshin.jp/webapi/tdnet/list/%s.json?limit=%d"
UA = "kabu-memo-calendar/1.0 (personal use; polite 1req/sec)"
JST = dt.timezone(dt.timedelta(hours=9))

# 本文を優先して読むタイトル語（予定・変更が書かれやすいもの）
PRIORITY = [
    (r"修正", 30), (r"決算発表|決算説明", 25), (r"決算短信", 20), (r"発売|販売開始|開始", 20),
    (r"承認|治験|開発", 20), (r"量産|工場|設備|稼働", 20), (r"提携|受注|進出|取得|自己株式", 18),
    (r"延期|中止|変更", 22), (r"配当", 15), (r"訂正", 22),
]
SKIP_TITLE = re.compile(r"コーポレート・ガバナンス|株主総会招集|議決権|大量保有|人事|役員|定款")


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
        items.append({
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


def pdf_pages(data):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    return [(p.extract_text() or "") for p in r.pages]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--budget", type=int, default=150)
    ap.add_argument("--retention-days", type=int, default=60)
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
                seen[it["id"]] = {"status": "pending", **it}
        time.sleep(1)

    # 抽出ルールが新しくなったら、読み終えた資料も当て直す（古いルールの項目は捨てる）
    events = [e for e in events if e.get('extractor') == EXT_VERSION]
    for v in seen.values():
        if v['status'] == 'done' and v.get('ext') != EXT_VERSION:
            v['status'] = 'pending'
    # 失敗は最大3回まで再挑戦する（一時的な通信エラーや、読み取り部品の不足を直した後に拾えるように）
    for v in seen.values():
        if v["status"] == "failed" and v.get("tries", 1) < 3:
            v["status"] = "pending"

    # 2) 本文取得（優先度順・上限つき）
    pending = [v for v in seen.values() if v["status"] == "pending"]
    pending.sort(key=lambda v: (-score(v, wl), v["pubdate"]))
    done_now = failed_now = 0
    for v in pending:
        if score(v, wl) < 0:
            v["status"] = "skipped"
            v["note"] = "対象外のタイトル（人事・総会等）。本文は読んでいない"
            continue
        if done_now + failed_now >= a.budget:
            break
        if not v.get("url"):
            v["status"] = "failed"
            v["note"] = "資料URLなし"
            failed_now += 1
            continue
        try:
            pages = pdf_pages(http_get(v["url"]))
            text_len = sum(len(p) for p in pages)
            if text_len < 20:
                raise ValueError("文字を取り出せない(画像PDFの可能性)")
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
            done_now += 1
        except Exception as e:
            v["status"] = "failed"
            v["tries"] = v.get("tries", 0) + 1
            v["note"] = "%s: %s" % (type(e).__name__, str(e)[:120])
            v["checked_at"] = checked_at
            failed_now += 1
            errors.append("%s %s %s" % (v["code"], v["title"][:20], v["note"]))
        time.sleep(1)

    # 3) 古いものを整理して保存
    cutoff = (now - dt.timedelta(days=a.retention_days)).strftime("%Y-%m-%d")
    seen = {k: v for k, v in seen.items() if v["pubdate"][:10] >= cutoff}
    events = [e for e in events if e["announced_at"][:10] >= cutoff or e.get("target", None)]
    cnt = {"pending": 0, "done": 0, "failed": 0, "skipped": 0}
    for v in seen.values():
        cnt[v["status"]] = cnt.get(v["status"], 0) + 1
    listed = len(seen)
    complete = listed > 0 and cnt["skipped"] == 0 and cnt["pending"] == 0 and cnt["failed"] == 0 and len(index_ok_days) == a.days
    status = {
        "generated_at": checked_at,
        "is_sample": False,
        "range": {"days": a.days, "index_ok_days": sorted(index_ok_days)},
        "listed": listed, "done": cnt["done"], "pending": cnt["pending"],
        "failed": cnt["failed"], "skipped": cnt["skipped"],
        "complete": complete,  # 全件を全文精査できたときだけ True
        "period": {"from": min((v["pubdate"][:10] for v in seen.values()), default=None),
                   "to": max((v["pubdate"][:10] for v in seen.values()), default=None)},
        "oldest_pending": min((v["pubdate"][:10] for v in seen.values() if v["status"] == "pending"), default=None),
        "budget_per_run": a.budget,
        "source_terms": "明確な許諾は未確認（やのしんは「情報収集・分析目的」とのみ記載、頻度制限・再配布の規定なし。JPX側の規約は確認できず）。個人利用・差分のみ・1秒間隔で運用し、停止指示があれば止める",
        "source": "TDnet(非公式API: webapi.yanoshin.jp)＋release.tdnet.info の公開PDF",
        "errors": errors[:30],
    }
    index_items = [{k: v.get(k) for k in ("id", "code", "name", "pubdate", "title", "url", "status", "note", "events", "pages", "checked_at")}
                   for v in sorted(seen.values(), key=lambda v: v["pubdate"], reverse=True)
                   if v["status"] in ("done", "failed") or score(v, wl) >= 20]
    save(STATE, seen)
    save(os.path.join(DATA, "events.json"), {"generated_at": checked_at, "events": events})
    save(os.path.join(DATA, "ir_index.json"), {"generated_at": checked_at, "items": index_items[:3000]})
    save(os.path.join(DATA, "status.json"), status)
    print(json.dumps({k: status[k] for k in ("listed", "done", "pending", "failed", "skipped", "complete")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
