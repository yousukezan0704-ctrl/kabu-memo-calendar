"""IR本文(ページ単位のテキスト)から予定・変更点を取り出す（ルールベース。AI推測は使わない）。

各項目は 会社名・コード・発表日時・対象時期・要点・元URL・ページ・根拠原文 を持つ。
文中に書かれていない値は「記載なし」にし、補わない。
"""
import re
import hashlib
import datetime as dt
from dates_jp import parse_target, parse_time, norm

NONE = "記載なし"
EXT_VERSION = "rule-v4"

# (kind, 表示名, トリガー正規表現)  上から順に判定。1文が複数に当てはまってもよい。
RULES = [
    ("earnings", "決算発表", r"決算発表(?:予定)?日|決算(?:短信)?(?:の)?発表(?:を|は)?予定|決算説明会(?:の)?開催(?!の?有無)(?:予定)?"),
    ("revision_up", "上方修正", r"上方修正"),
    ("revision_down", "下方修正", r"下方修正"),
    ("forecast", "業績予想の変更", r"業績予想(?:の)?(?:修正|変更)|予想(?:値)?を(?:修正|変更)|配当予想(?:の)?(?:修正|変更)"),
    ("launch", "発売・販売開始", r"発売|販売を?開始|販売開始|サービス(?:を)?開始|提供を?開始"),
    ("development", "開発・試験・承認", r"承認申請|承認(?:を)?取得|承認(?:を)?受け|治験|臨床試験|開発(?:を)?開始|試作|実証実験|認証取得"),
    ("production", "工場・設備・量産", r"量産|工場(?:の)?(?:稼働|新設|建設|竣工)|稼働(?:を)?開始|(?<!需要)(?<!の)設備投資(?!需要)(?:を|の実施)|生産(?:能力|を)?(?:開始|増強)"),
    ("alliance", "提携・受注・海外", r"業務提携|資本提携|提携(?:契約|を|します|いたし)|受注(?:しました|いたしました|決定|内定|契約|獲得|のお知らせ)|を受注|海外(?:進出|展開|拠点)|子会社(?:の)?(?:設立|化)"),
    ("buyback", "自社株買い", r"自己株式(?:の)?取得に係る事項|自己株式取得枠|取得(?:する)?株式の総数|自己株式(?:の)?取得(?:を)?(?:決議|決定)|自社株買い(?:を)?(?:実施|決議|発表)"),
    ("delay", "延期・中止・条件変更", r"延期|中止(?!する場合|日|及び|事業)|撤回|(?:スケジュール|予定|条件)(?:の)?(?:変更|見直し)|遅れる|遅延"),
]
# 発売・開発・量産は「これからの予定」の書き方のときだけ拾う（過去の実績・景況の説明を除く）
FUTURE_RE = re.compile(r"予定|見込み|見込まれ|計画|目指|開始(?:します|いたします|する)|(?:発売|申請|稼働|量産)(?:します|いたします|する)|方針|予定です")
PAST_NARR_RE = re.compile(r"以来|好調|推移|ました。|発売後|前期に|前年同期")
# 想定為替は「想定・前提・影響」と数字がそろうものだけ。ETFの換算レート等は除く
FX_CORE = re.compile(r"想定(?:為替)?レート|為替(?:レート)?(?:の)?前提|前提(?:為替)?レート|為替(?:の)?影響(?:額|を)|為替影響")
KIND_LABEL = {k: n for k, n, _ in RULES}
KIND_LABEL.update({"fx": "想定為替・為替影響", "forecast_item": "予想数値の変更"})

FORECAST_ITEMS = ["売上高", "営業利益", "経常利益", "親会社株主に帰属する当期純利益", "当期純利益",
                  "1株当たり当期純利益", "1株当たり配当金", "期末配当", "年間配当", "配当"]
IMPACT_RE = re.compile(r"(今期|当期|通期|当事業年度|当連結会計年度|来期|次期|翌期|来年度|次年度|"
                       r"第[1-4１-４]四半期|上半期|下半期|上期|下期|中期経営計画|\d{4}年\d{1,2}月期|\d{4}年度)")
FX_RE = re.compile(r"(想定(?:為替)?レート|為替レート|為替(?:の)?(?:影響|前提|相場)|円安|円高|米ドル|1ドル|ドル=|\$=)")
SENT_SPLIT = re.compile(r"(?<=[。！？\n])")
DATEISH = re.compile(r"(\d{1,4}年|\d{1,2}月|春|夏|秋|冬|年度内|来期|今期|来年度|次期|上期|下期|四半期)")


def sentences(text):
    t = norm(text).replace("\r", "")
    t = re.sub(r"[ 　\t]+", " ", t)
    # PDFは日本語の文字間に空白が入る（「2026年 11月 2日」）ので、英字どうし以外の空白は除く
    t = re.sub(r"(?<=[^\sA-Za-z]) +(?=[^\sA-Za-z])", "", t)
    # PDF抽出で途中改行された文をつなぐ（句点で終わる行以外は結合）
    t = re.sub(r"(?<![。！？\n])\n(?!\n)", "", t)
    out = []
    for s in SENT_SPLIT.split(t):
        s = s.strip()
        if 6 <= len(s):
            out.append(s)
    return out


def _quote(s, n=140):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _impact(s):
    m = IMPACT_RE.search(s)
    return m.group(1) if m else NONE


def event_key(code, kind, quote):
    base = "%s|%s|%s" % (code, kind, re.sub(r"[\s、。,.　]", "", quote)[:60])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def extract_page(page_text, page_no, ctx):
    """ctx: code,name,pubdate(iso str 'YYYY-MM-DD HH:MM:SS'),title,url,fy_end_month,checked_at"""
    base = dt.date.fromisoformat(ctx["pubdate"][:10])
    events = []
    for s in sentences(page_text):
        # 免責の定型文は対象外
        if re.search(r"将来の見通し|リスクや不確実|投資勧誘", s):
            continue
        hits = []   # (kind, label, 該当位置)
        for k, n, rx in RULES:
            m = re.search(rx, s)
            # 「…の修正に関するお知らせ」のような題名の行は、中身ではないので除く
            if m and not re.match(r"(?:に関する|についての|の)?お知らせ", s[m.end():m.end() + 12]) \
               and not re.match(r"に関する", s[m.end():m.end() + 4]):
                hits.append((k, n, m))
        mf = FX_CORE.search(s)
        if mf and re.search(r"\d", s[max(0, mf.start() - 40): mf.end() + 60]) and not re.search(r"ETF|上場投資信託|米国ドル建", ctx.get("title", "")):
            hits.append(("fx", KIND_LABEL["fx"], mf))
        for k, n, m in hits:
            # 根拠は該当語の前後だけ（表や長い見出しを丸ごと載せない）
            s_win = s[max(0, m.start() - 50): m.end() + 80]
            tgt = parse_target(s_win, base, ctx.get("fy_end_month")) if DATEISH.search(s_win) else None
            if tgt is not None:
                # 業績予想・為替の文に出てくる日付は「公表日」「期間」など参照用なので予定にしない
                if k in ("revision_up", "revision_down", "forecast", "fx"):
                    tgt = None
                # 決算期（2027年3月期）は予定日ではなく対象期間の説明
                elif tgt["precision"] == "fy" and tgt["reason"] == "決算期の指定":
                    tgt = None
                # 発表日より前の日付は過去の経緯（「○月○日に決議」など）であり、これからの予定ではない
                elif tgt["precision"] == "day" and tgt["start"] < base.isoformat():
                    tgt = None
            if k in ("launch", "development", "production"):
                if not FUTURE_RE.search(s_win) or (PAST_NARR_RE.search(s_win) and tgt is None):
                    continue
            if k == "earnings" and not re.search(r"予定|開催|発表", s_win):
                continue
            ev = {
                "kind": k,
                "kind_label": n,
                "code": ctx["code"], "name": ctx["name"],
                "announced_at": ctx["pubdate"],
                "target": tgt,   # None のときは「記載なし」
                "target_text": tgt["raw"] if tgt else NONE,
                "time_text": (tgt or {}).get("time") or (parse_time(s_win) if k == "earnings" else None),
                "impact_period": _impact(s_win) if k in ("revision_up", "revision_down", "forecast", "fx") else NONE,
                "summary": _quote(s_win, 90),
                "quote": _quote(s_win),
                "page": page_no,
                "url": ctx["url"],
                "title": ctx["title"],
                "checked_at": ctx["checked_at"],
                "origin": "official",       # 会社の公表資料から機械的に抽出
                "extractor": EXT_VERSION,
                "confirmed": bool(tgt and tgt["precision"] == "day" and not tgt["needs_review"]),
                "needs_review": bool(tgt and tgt["needs_review"]),
            }
            ev["id"] = event_key(ctx["code"], k, s_win)
            events.append(ev)
    return events


def extract_forecast_rows(page_text, page_no, ctx):
    """「前回発表予想」を含むページから、項目名+数値の行を拾う（差分の素材）。"""
    t = norm(page_text)
    if not re.search(r"前回(?:発表)?予想|修正後|今回修正", t):
        return []
    rows = []
    for line in t.split("\n"):
        line = line.strip()
        if re.search(r"公表|基準日|決議|決定額|につき|となります|見込み", line):
            continue
        if not any(re.match(r"^[\d\s.()（）※注]*" + re.escape(it), line) for it in FORECAST_ITEMS):
            continue
        nums = re.findall(r"[△▲\-]?\d[\d,]*(?:\.\d+)?", line.split(next(i for i in FORECAST_ITEMS if i in line), 1)[1])
        if len(nums) >= 2:
            item = next(i for i in FORECAST_ITEMS if i in line)
            rows.append({
                "kind": "forecast_item", "kind_label": KIND_LABEL["forecast_item"],
                "code": ctx["code"], "name": ctx["name"], "announced_at": ctx["pubdate"],
                "target": None, "target_text": NONE, "time_text": None,
                "impact_period": _impact(t[:600]),
                "summary": "%s: %s" % (item, " → ".join(nums[:3])),
                "values": nums[:4], "item": item,
                "quote": _quote(line), "page": page_no, "url": ctx["url"], "title": ctx["title"],
                "checked_at": ctx["checked_at"], "origin": "official", "extractor": EXT_VERSION,
                "confirmed": False, "needs_review": True,   # 列の意味(前回/今回)は人の目で確認
                "id": event_key(ctx["code"], "forecast_item", line + ctx["pubdate"][:10]),
            })
    return rows


def extract_document(pages, ctx):
    """pages: [str,...] (1ページ目が先頭)。重複は id で除去。"""
    seen, out = set(), []
    for i, p in enumerate(pages, 1):
        for ev in extract_page(p, i, ctx) + extract_forecast_rows(p, i, ctx):
            if ev["id"] in seen:
                continue
            seen.add(ev["id"])
            out.append(ev)
    return out[:40]  # 1資料あたりの上限（異常な量を避ける）


def is_correction(title):
    return bool(re.search(r"訂正|修正版|一部変更|変更のお知らせ.*(?:訂正|差替)|差替", title or ""))


def merge_events(existing, new):
    """同じidは重複登録せず、内容が変わった場合のみ履歴に残す。"""
    by_id = {e["id"]: e for e in existing}
    added = updated = 0
    for ev in new:
        old = by_id.get(ev["id"])
        if not old:
            ev["history"] = []
            by_id[ev["id"]] = ev
            added += 1
            continue
        keys = ("target_text", "time_text", "quote", "url", "page")
        if any(old.get(k) != ev.get(k) for k in keys):
            old.setdefault("history", []).append({k: old.get(k) for k in keys + ("announced_at", "checked_at")})
            for k in keys + ("target", "announced_at", "checked_at", "summary", "confirmed", "needs_review"):
                old[k] = ev.get(k)
            updated += 1
        else:
            old["checked_at"] = ev["checked_at"]
    return list(by_id.values()), added, updated
