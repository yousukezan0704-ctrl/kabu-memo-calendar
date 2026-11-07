"""収集後の集計と重複チェック（読み取り専用）。使い方: python -X utf8 tools/check_data.py"""
import collections as C
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "docs", "data")


def main():
    ev = json.load(open(os.path.join(D, "events.json"), encoding="utf-8"))
    ev = ev.get("events", ev)
    st = json.load(open(os.path.join(D, "status.json"), encoding="utf-8"))
    print("件数:", len(ev), "| 抽出器:", dict(C.Counter(x.get("extractor") for x in ev)))
    print("種類:", dict(C.Counter(x["kind"] for x in ev)))
    print("要確認:", sum(1 for x in ev if x.get("needs_review")), "| 確認済み:", sum(1 for x in ev if x.get("confirmed")))
    ids = C.Counter(x["id"] for x in ev)
    print("ID重複:", sum(1 for v in ids.values() if v > 1))
    key = C.Counter((x["code"], x["kind"], x.get("item"), x.get("impact_period"), x.get("prev"), x.get("new"), x.get("url"))
                    for x in ev if x.get("kind") in ("forecast_item", "dividend"))
    print("内容の重複(予想数値・配当):", sum(1 for v in key.values() if v > 1))
    byurl = C.defaultdict(set)
    for x in ev:
        if x.get("kind") in ("dividend", "forecast_item") and "配当" in (x.get("item") or x.get("summary") or ""):
            byurl[x["url"]].add(x["kind"] + "/" + str(x.get("extractor")))
    both = [u for u, s in byurl.items() if len(s) > 1]
    print("同じ通知に配当が文章とXBRLで並ぶ:", len(both))
    print("配当イベント:", [(x["code"], x["summary"][:40], x.get("needs_review")) for x in ev if x["kind"] == "dividend"][:8])
    print("status:", {k: st[k] for k in ("complete", "counts", "revisions_xbrl") if k in st})


if __name__ == "__main__":
    main()
