"""themes.json と sample.json（すべて架空のサンプル）を作る。実データではない。"""
import json, os, datetime as dt

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "data")
os.makedirs(root, exist_ok=True)

# テーマ名だけを用意し、銘柄は空にする。銘柄は「根拠を確認できたもの」だけを利用者が追加する。
themes = {"themes": [
    {"id": "jishin", "name": "地震", "stocks": []},
    {"id": "bousai", "name": "防災", "stocks": []},
    {"id": "denryoku", "name": "電力", "stocks": []},
    {"id": "handotai", "name": "半導体", "stocks": []},
    {"id": "zenkotai", "name": "全固体電池", "stocks": []},
]}

today = dt.date.today()
def d(n): return (today + dt.timedelta(days=n)).isoformat()
now = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")

def ev(i, kind, label, tgt, summary, quote, page=1, **kw):
    e = {"id": "sample%d" % i, "kind": kind, "kind_label": label, "code": "0000", "name": "サンプル工業(架空)",
         "announced_at": d(-3) + " 15:00:00", "target": tgt, "target_text": tgt["raw"] if tgt else "記載なし",
         "time_text": None, "impact_period": "記載なし", "summary": summary, "quote": quote, "page": page,
         "url": "", "title": "（架空）サンプルのIR", "checked_at": now, "origin": "official", "extractor": "sample",
         "confirmed": False, "needs_review": False}
    e.update(kw)
    return e

def day(date, raw, time=None):
    return {"raw": raw, "start": date, "end": date, "precision": "day", "needs_review": False, "reason": "", "time": time}

sample = {"is_sample": True, "note": "これは架空のデータです。実際の会社・IRではありません。", "events": [
    ev(1, "earnings", "決算発表", day(d(10), "%s 15時00分" % d(10)), "第2四半期決算を発表予定", "当社は第2四半期決算を%sに発表する予定です。" % d(10), time_text="15:00", confirmed=True),
    ev(2, "launch", "発売・販売開始", {"raw": "来春", "start": "%d-03-01" % (today.year + 1), "end": "%d-05-31" % (today.year + 1), "precision": "season", "needs_review": False, "reason": ""}, "新製品Aを来春に発売予定", "新製品Aを来春に発売する予定です。"),
    ev(3, "development", "開発・試験・承認", {"raw": "年度内", "start": None, "end": None, "precision": "fy", "needs_review": True, "reason": "会社の決算期が文中にないため期間を確定できない"}, "承認申請を年度内に行う予定", "年度内に承認申請を行う予定です。", needs_review=True),
    ev(4, "revision_up", "上方修正", None, "通期予想を上方修正", "通期の営業利益予想を上方修正いたします。", impact_period="通期"),
    ev(5, "production", "工場・設備・量産", day(d(45), "%s" % d(45)), "新工場の稼働開始予定", "新工場の稼働を%sに開始する予定です。" % d(45)),
], "themes": [
    {"id": "handotai", "name": "半導体", "stocks": [
        {"code": "0000", "name": "サンプル工業(架空)", "relation": "business", "evidence": "（架空）半導体製造装置の部品を製造と記載", "confirmed_at": d(-1)},
        {"code": "0001", "name": "サンプル商事(架空)", "relation": "price", "evidence": "（架空）過去に株価が連動して動いただけ。事業上の関係は確認できていない", "confirmed_at": d(-1)}]}]}

for name, obj in (("themes.json", themes), ("sample.json", sample)):
    with open(os.path.join(root, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
with open(os.path.join(root, "..", "manifest.webmanifest"), "w", encoding="utf-8") as f:
    json.dump({"name": "株メモカレンダー", "short_name": "株メモ", "start_url": "./", "scope": "./", "display": "standalone",
               "background_color": "#f5f7fa", "theme_color": "#1a56db", "lang": "ja",
               "icons": [{"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                         {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"}]}, f, ensure_ascii=False, indent=1)
print("ok")
