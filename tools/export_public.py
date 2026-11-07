"""公開用JSONへの変換（許可リスト方式）。**今は公開しない。** 出力先 public_out/ は git に入れない。
使い方: python tools/export_public.py [出力フォルダ]
方針:
・許可リストにある項目だけを書き出す。リストにない項目は自動的に落ちる（新しい項目が混ざらない）。
・確認済み(confirmed)または公式XBRL由来で、要確認(needs_review)でないものだけ。保留の種類(提携)は含めない。
・PDFの文章・引用(quote, summary, note, reason_text)は含めない。数値・日付・分類・銘柄だけ。
・メモ・保有銘柄・トークンはブラウザ内にあり、この変換の入力(docs/data)には存在しない。
・公開するかどうかはユーザーが決める。TDnetの利用条件が未確認のため、公開の実行はしない。"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import validate_data  # noqa: E402

EVENT_FIELDS = ["id", "kind", "kind_label", "code", "name", "announced_at", "impact_period", "item", "unit",
                "prev", "new", "diff", "page", "url", "origin", "confirmed", "checked_at"]
TARGET_FIELDS = ["start", "end", "precision"]
FORBIDDEN = {"quote", "summary", "note", "reason_text", "target_text", "memo", "token", "kmc.src"}


def publishable(x):
    if x.get("needs_review") or x.get("kind") in validate_data.HOLD_KINDS:
        return False
    return bool(x.get("confirmed")) or x.get("extractor") == "xbrl"


def convert(x):
    o = {k: x[k] for k in EVENT_FIELDS if k in x}
    t = x.get("target")
    if isinstance(t, dict):
        o["target"] = {k: t.get(k) for k in TARGET_FIELDS}
    o["source"] = "TDnet/公式XBRL" if x.get("extractor") == "xbrl" else "TDnet"
    o["status"] = "確認済み"
    return o


def export(src, dst):
    os.makedirs(dst, exist_ok=True)
    ev = validate_data.events_of(validate_data.load(src, "events.json"))
    out = [convert(x) for x in ev if publishable(x)]
    with open(os.path.join(dst, "events.json"), "w", encoding="utf-8") as f:
        json.dump({"events": out, "note": "検証済みの項目のみ（許可リスト方式で変換）"}, f, ensure_ascii=False, indent=1)
    return len(ev), len(out)


def main():
    dst = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "public_out")
    n0, n1 = export(os.path.join(ROOT, "docs", "data"), dst)
    print("変換: %d 件中 %d 件を書き出しました（公開はしていません）→ %s" % (n0, n1, dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
