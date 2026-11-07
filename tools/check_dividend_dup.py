"""配当が文章側とXBRL側で並んでいる通知を表示（読み取り専用）。"""
import json
import os

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "data")
ev = json.load(open(os.path.join(D, "events.json"), encoding="utf-8"))
ev = ev.get("events", ev)
by = {}
for x in ev:
    if x["kind"] == "dividend" or (x["kind"] == "forecast_item" and "配当" in (x.get("item") or "")):
        by.setdefault(x["url"], []).append(x)
for u, xs in by.items():
    if len({x["kind"] for x in xs}) > 1:
        print(u)
        for x in xs:
            print("  ", x["kind"], x.get("extractor"), x["id"], x.get("title", "")[:30], "|", x["summary"][:50])
