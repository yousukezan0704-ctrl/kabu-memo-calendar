"""公開前の検証(ゲート)。収集したデータを非公開リポジトリへ送る前に必ず通す。
使い方: python tools/validate_data.py <データのフォルダ> [前回のデータのフォルダ]
・構造の問題(壊れたJSON・IDの重複・件数の急減など)があれば、失敗(終了コード1)にして送らない。
・精度が確認できていない種類(HOLD_KINDS)の、確認済みでない項目は「保留」にして、公開用のデータから外す
  (外したものは held.json に残すので、データは失われない)。
・自動収集の再開前の精度検証で分かった弱点は、ここに足していく。"""
import json
import os
import sys

HOLD_KINDS = {"alliance"}          # 提携: 検証で5件中0件しか正しくなかった(rule-v10)
MAX_SHRINK = 0.2                    # 前回より20%超 減ったら異常とみなす
SAFE_UNDATED_EXTRACTORS = {"xbrl"}  # 日付なしでも確認済みにしてよいのは、公式XBRL由来だけ


def load(folder, name):
    p = os.path.join(folder, name)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def events_of(d):
    return d.get("events", d) if isinstance(d, dict) else (d or [])


def check(folder, prev_folder=None):
    """問題の一覧を返す(空なら合格)。"""
    problems = []
    try:
        ev_raw = load(folder, "events.json")
        load(folder, "ir_index.json")
        st = load(folder, "status.json")
    except ValueError as e:
        return ["JSONが壊れています: %s" % e]
    if ev_raw is None:
        return ["events.json がありません"]
    ev = events_of(ev_raw)
    ids = [x.get("id") for x in ev]
    if len(ids) != len(set(ids)):
        problems.append("イベントIDが重複しています(%d件)" % (len(ids) - len(set(ids))))
    for x in ev:
        if not x.get("id") or not x.get("kind") or not x.get("code") or not x.get("url"):
            problems.append("必須項目が欠けたイベント: %s" % x.get("id"))
            break
    for x in ev:
        t = x.get("target") or {}
        if x.get("confirmed") and not t.get("start") and x.get("extractor") not in SAFE_UNDATED_EXTRACTORS \
                and x.get("kind") not in ("revision_up", "revision_down", "forecast", "forecast_item", "earnings"):
            problems.append("日付がないのに確認済み: %s %s" % (x.get("code"), x.get("kind")))
            break
    if st is not None and st.get("complete") is False and st.get("failed", 0) > 5:
        problems.append("取得の失敗が多すぎます(%s件)" % st.get("failed"))
    if prev_folder:
        pe = load(prev_folder, "events.json")
        if pe is not None:
            n0, n1 = len(events_of(pe)), len(ev)
            if n0 >= 50 and n1 < n0 * (1 - MAX_SHRINK):
                problems.append("イベント数が急に減りました(%d→%d)" % (n0, n1))
    return problems


def hold(folder):
    """精度未確認の種類を、公開用の events.json から外して held.json へ移す。(外した件数)を返す。"""
    d = load(folder, "events.json")
    ev = events_of(d)
    keep, held = [], []
    for x in ev:
        (held if (x.get("kind") in HOLD_KINDS and not x.get("confirmed")) else keep).append(x)
    if isinstance(d, dict):
        d["events"] = keep
    else:
        d = keep
    with open(os.path.join(folder, "events.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    with open(os.path.join(folder, "held.json"), "w", encoding="utf-8") as f:
        json.dump({"reason": "精度が確認できていない種類のため、公開用から保留", "kinds": sorted(HOLD_KINDS), "events": held},
                  f, ensure_ascii=False, indent=1)
    return len(held)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    probs = check(argv[1], argv[2] if len(argv) > 2 else None)
    if probs:
        print("検証に失敗しました。送信しません:")
        for p in probs:
            print(" -", p)
        return 1
    print("検証に合格しました")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
