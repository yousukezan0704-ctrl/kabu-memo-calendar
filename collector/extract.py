"""IR本文(ページ単位のテキスト)から予定・変更点を取り出す（ルールベース。AI推測は使わない）。

各項目は 会社名・コード・発表日時・対象時期・要点・元URL・ページ・根拠原文 を持つ。
文中に書かれていない値は「記載なし」にし、補わない。
"""
import re
import hashlib
import datetime as dt
from dates_jp import parse_target, parse_time, norm

NONE = "記載なし"
EXT_VERSION = "rule-v7"

# (kind, 表示名, トリガー正規表現)  上から順に判定。1文が複数に当てはまってもよい。
RULES = [
    ("earnings", "決算発表", r"次回(?:の)?決算(?:短信)?(?:の)?発表(?:予定)?(?:日)?|決算発表(?:予定)?(?:日時|日)|決算(?:短信)?(?:の)?発表(?:を|は)?予定|決算説明会(?:の)?(?:開催日時|開催(?!の?有無)(?:予定)?|日時)"),
    ("revision_up", "上方修正", r"上方修正"),
    ("revision_down", "下方修正", r"下方修正"),
    ("forecast", "業績予想の変更", r"業績予想(?:の)?(?:修正|変更)|予想(?:値)?を(?:修正|変更)|配当予想(?:の)?(?:修正|変更)"),
    ("launch", "発売・販売開始", r"発売|販売を?開始|販売開始|サービス(?:を)?開始|提供を?開始|上市(?=[^。]{0,6}(?:目指|予定|計画|見込))"),
    ("development", "開発・試験・承認", r"承認申請|承認(?:を)?取得|承認(?:を)?受け|治験|臨床試験|開発(?:を)?開始|試作|実証実験|認証取得"),
    ("production", "工場・設備・量産", r"量産|工場(?:の)?(?:稼働|新設|建設|竣工)|稼働(?:を)?開始|(?<!需要)(?<!の)設備投資(?!需要)(?:を|の実施)|生産(?:能力|を)?(?:開始|増強)"),
    ("alliance", "提携・受注・海外", r"業務提携|資本提携|提携(?:契約|を|します|いたし)|受注(?:しました|いたしました|決定|内定|契約|獲得|のお知らせ)|を受注|海外(?:進出|展開|拠点)|子会社(?:の)?(?:設立|化)"),
    ("buyback", "自社株買い", r"自己株式(?:の)?取得に係る事項|自己株式取得枠|取得(?:する)?株式の総数|自己株式(?:の)?取得(?:を)?(?:決議|決定)|自社株買い(?:を)?(?:実施|決議|発表)"),
    ("delay", "延期・中止・条件変更", r"延期|中止(?!する場合|日|及び|事業)|撤回|(?:スケジュール|予定|条件)(?:の)?(?:変更|見直し)|遅れる|遅延|時期(?:については|は)(?=[^。]{0,12}(?:令和\d+年|\d{4}年))"),
]
# 発売・開発・量産は「これからの予定」の書き方のときだけ拾う（過去の実績・景況の説明を除く）
FUTURE_RE = re.compile(r"予定|見込み|見込まれ|計画|目指|開始(?:します|いたします|する)|(?:発売|申請|稼働|量産)(?:します|いたします|する)|する方針|方針です|(?:より|から)本格")
PAST_NARR_RE = re.compile(r"以来|好調|推移|ました。|発売後|前期に|前年同期|をはじめ|するなど|してまいりました|してきました")
# すでに終わった事実・時期が決まっていない文は「予定」にしない
PAST_DONE_RE = re.compile(r"竣工|完成し|開始(?:した|しました|いたしました)|発売(?:した|しました|いたしました)|稼働(?:した|しました)|(?:発売|開始)(?:を)?し(?:て|た)(?:おり|いる|き|い)|決定次第|未定|検討中|検討して|\d{4}/\d{1,2}/\d{1,2}")
PROD_CTX_RE = re.compile(r"工場|生産|量産|製造|プラント|ライン(?!ナップ)")
FACILITY_RE = re.compile(r"施設|店舗|事業所")
ADJUST_RE = re.compile(r"考慮|調整|実質ベース|押し下げ|押し上げ|影響を除|比較")
DELAY_NOISE_RE = re.compile(r"開示が|損害金|リスク|可能性|場合|おそれ|恐れ|不確実|警戒|懸念|下回|上回|影響|事業環境|予測|動向|研究開発")
DELAY_CTX_RE = re.compile(r"時期|予定|スケジュール|計画|発売|完工|稼働|開始|開発|工期|上市|竣工|成立日|期日")
# 資料の種類で除く（月次の速報・リスク情報・事業計画及び成長可能性の資料）
NOISE_TITLE_RE = re.compile(r"速報|月次|\d+月度|KPI")
RISK_TITLE_RE = re.compile(r"リスク|事業計画及び成長可能性")   # 延期・決算の判定には使わない(定型のリスク文が多い)
END_BUYBACK_TITLE_RE = re.compile(r"取得状況|取得結果|取得終了|取得完了")
SUBSIDIARY_TITLE_RE = re.compile(r"連結子会社.*業績予想|子会社の業績予想")
# 想定為替は「想定・前提・影響」と数字がそろうものだけ。ETFの換算レート等は除く
FX_CORE = re.compile(r"想定(?:為替)?レート|為替(?:レート)?(?:の)?前提|前提(?:為替)?レート|適用為替レート")
FX_AVG_RE = re.compile(r"平均為替|期中平均|実績レート|実績平均")
FX_NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*円|\$\s*\d|ドル|(?:USD|EUR|JPY|CNY|THB)\s*[:：]?\s*\d")
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


def _mask_quotes(s):
    """「」『』の中(過去の開示の題名など)は判定に使わない。長さは同じにして位置をずらさない。"""
    return re.sub(r"[「『][^」』]{0,80}[」』]", lambda m: "〓" * len(m.group(0)), s)


def extract_page(page_text, page_no, ctx):
    """ctx: code,name,pubdate(iso str 'YYYY-MM-DD HH:MM:SS'),title,url,fy_end_month,checked_at"""
    base = dt.date.fromisoformat(ctx["pubdate"][:10])
    title = ctx.get("title", "")
    noise_doc = bool(NOISE_TITLE_RE.search(title))
    events = []
    for s in sentences(page_text):
        # 免責の定型文は対象外
        if re.search(r"将来の見通し|リスクや不確実|投資勧誘", s):
            continue
        sm = _mask_quotes(s)
        hits = []   # (kind, label, 該当位置)
        for k, n, rx in RULES:
            if noise_doc and k not in ("revision_up", "revision_down", "forecast"):
                continue
            if k in ("delay", "earnings") and RISK_TITLE_RE.search(title):
                continue
            ms = list(re.finditer(rx, sm))[:4]
            last_pos = -999
            for m in ms:
                if m.start() - last_pos < 60 and k != "earnings":
                    continue   # すぐ近くの同じ種類の一致は同じ話
                last_pos = m.start()
                # 「…の修正に関するお知らせ」のような題名の行は、中身ではないので除く
                if m and not re.match(r"(?:に関する|についての|の)?お知らせ", sm[m.end():m.end() + 12]) \
                   and not re.match(r"に関する", sm[m.end():m.end() + 4]):
                    hits.append((k, n, m))
        mf = FX_CORE.search(sm)
        if mf and not noise_doc and not re.search(r"ETF|上場投資信託|米国ドル建", title):
            near_fx = sm[max(0, mf.start() - 40): mf.end() + 60]
            if FX_NUM_RE.search(near_fx) and not FX_AVG_RE.search(near_fx):
                hits.append(("fx", KIND_LABEL["fx"], mf))
        for k, n, m in hits:
            # 根拠は該当語の前後だけ（表や長い見出しを丸ごと載せない）
            s_win = s[max(0, m.start() - 50): m.end() + 80]
            near = sm[max(0, m.start() - 25): m.end() + 35]
            if k == "earnings":
                # 決算発表の日付は、該当語より後ろ(または直前25字)に書かれたものだけを使う。
                if re.search(r"沈黙期間|決算期日の翌日", s):
                    continue
                s_win = s[max(0, m.start() - 25): m.end() + 80]
                tgt = parse_target(s[m.start():m.end() + 80], base, ctx.get("fy_end_month")) \
                    or parse_target(s_win, base, ctx.get("fy_end_month"))
            else:
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
                # 期間・季節・月が発表日より前に終わっているものも過去の事実
                elif k in ("launch", "development", "production", "delay", "alliance") \
                        and tgt.get("end") and tgt["end"] < base.isoformat():
                    continue
            if k in ("launch", "development", "production"):
                if PAST_DONE_RE.search(near):
                    continue
                if not FUTURE_RE.search(near) or (PAST_NARR_RE.search(near) and tgt is None):
                    continue
            if k == "production" and (not PROD_CTX_RE.search(near) or (FACILITY_RE.search(near) and not re.search(r"工場|生産|量産", near))):
                continue
            if k == "delay" and (DELAY_NOISE_RE.search(near) or not DELAY_CTX_RE.search(near)):
                continue
            if k == "buyback" and (END_BUYBACK_TITLE_RE.search(title) or re.search(r"取得を終了|終了いたしました", near)):
                continue
            if k == "alliance" and (re.search(r"ご参照|プレスリリース|開示事項の経過", s_win + title)
                                    or re.search(r"(?:子会社化|設立|取得|提携)(?:し|いたし)(?:た|ました|て)|完了", near)):
                continue
            if k == "delay" and re.search(r"時期(?:については|は)", near) and not re.search(r"変更|延期|遅", title + s):
                continue   # 「時期は○年」だけでは、変更後の日程かどうか分からない
            if k in ("revision_up", "revision_down") and ADJUST_RE.search(s_win):
                continue   # 前年比較などの調整表の説明で、業績予想の修正ではない
            if k in ("revision_up", "revision_down") and re.search(r"業界|市場", s_win) \
               and not re.search(r"業績予想|当社|連結", s_win):
                continue   # 業界・市場の見通しの話で、当社の業績予想ではない
            if k == "earnings":
                # 日付が書かれていない決算発表は予定として使えない（過去の説明の可能性が高い）
                if tgt is None or tgt["precision"] not in ("day", "month"):
                    continue
            ev = {
                "kind": k,
                "kind_label": n,
                "code": ctx["code"], "name": ctx["name"],
                "announced_at": ctx["pubdate"],
                "target": tgt,   # None のときは「記載なし」
                "target_text": tgt["raw"] if tgt else NONE,
                # 時刻は日付の直後に書かれたものだけ。書かれていなければ None（補わない）
                "time_text": (tgt or {}).get("time") if (tgt or {}).get("precision") == "day" else None,
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


RNG = r"[△▲\-]?\d[\d,]*(?:\.\d+)?"
ITEM_RE = re.compile(r"売上高|売上収益|営業収益|営業利益|経常利益|親会社株主に帰属する(?:当期|中間|四半期)純利益|親会社の所有者に帰属する(?:当期|中間|四半期)利益|"
                     r"1株当たり(?:当期|中間|四半期)純利益|1株当たり(?:当期|中間|四半期)利益|基本的1株当たり(?:当期|中間|四半期)利益|"
                     r"(?:当期|中間|四半期)純利益|(?:当期|中間|四半期)利益|1株当たり配当金|年間配当金")
# 数値1個 = 「14円00銭」「99円」「△304」「45,500～46,000」のどれか
TOK_RE = re.compile(r"(\d[\d,]*)\s*円\s*(\d{1,2})\s*銭|(\d[\d,]*(?:\.\d+)?)\s*円(?!\s*銭)|(" + RNG + r"(?:[～〜~]" + RNG + r")?)")
PREV_LABEL = re.compile(r"^前回(?:発表)?予想")
NEW_LABEL = re.compile(r"^(?:今回(?:修正)?予想|修正後(?:予想)?|今回発表予想|修正予想)")
PERIOD_RE = re.compile(r"\d{4}年\d{1,2}月期|通期|第[1-4]四半期|中間期|上半期|下半期|上期|下期")
COL_RE = re.compile(r"(?P<new>決定額|今回(?:修正|発表)?予想|修正後(?:予想)?|修正予想)|(?P<prev>直近の配当予想|直近に公表(?:され)?(?:てい)?る?(?:配当)?予想|前回(?:発表)?予想|直近予想)|(?P<last>前期実績|前期)")


def _val(tok):
    t = tok.replace(",", "").replace("△", "-").replace("▲", "-")
    try:
        return float(t)
    except ValueError:
        return None


def _tok_value(m):
    """TOK_RE の一致 -> (表示文字列, 数値 or None, 範囲(lo,hi) or None, 円か)"""
    if m.group(1) is not None:
        v = float(m.group(1).replace(",", "") + "." + m.group(2).rjust(2, "0"))
        return "%s円%s銭" % (m.group(1), m.group(2).rjust(2, "0")), v, None, True
    if m.group(3) is not None:
        return m.group(3) + "円", float(m.group(3).replace(",", "")), None, True
    tok = m.group(4)
    parts = re.split(r"[～〜~]", tok)
    vs = [_val(p) for p in parts]
    if len(parts) == 2 and None not in vs:
        return tok, None, (vs[0], vs[1]), False
    return tok, vs[0], None, False


def _tokens(text):
    return [_tok_value(m) for m in TOK_RE.finditer(text)]


def _money(s):
    m = re.match(r"(\d[\d,]*)円(?:(\d{1,2})銭)?", s)
    if not m:
        return None
    return float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))


def _num_of(s):
    return _money(s) if s.endswith(("円", "銭")) else _val(s)


def _bounds(t):
    return t[2] if t[2] else ((t[1], t[1]) if t[1] is not None else None)


def _period_above(lines, i):
    """表の見出し(「…通期…予想数値の修正」など)に書かれた対象期間を、8行以内で最も近いものから拾う。"""
    for j in range(i - 1, max(-1, i - 9), -1):
        l = lines[j]
        if re.search(r"ご参考|前期実績", l) or not re.search(r"業績予想|予想数値|修正", l):
            continue
        found = []
        for m in PERIOD_RE.finditer(l):
            if m.group(0) not in found:
                found.append(m.group(0))
        if found:
            return " ".join(found)
    return NONE


UNIT_RE = re.compile(r"億円|百万円|千円|万円")


def _unit_of(*texts):
    """見出しや行に書かれた金額の単位。書かれていなければ None（補わない）。"""
    for t in texts:
        m = UNIT_RE.search(t or "")
        if m:
            return m.group(0)
    return None


def _row(ctx, page_no, item, prev, new, line, verified, basis=None, period=NONE, diff_text=None, note=None, unit=None):
    """prev/new は表示用の文字列。数値化できるときだけ差を計算する。"""
    pv, nv = _num_of(prev), _num_of(new)
    diff = None if pv is None or nv is None else round(nv - pv, 6)
    if item.startswith("1株当たり") or prev.endswith(("円", "銭")):
        unit = None
    u = unit or ""
    if diff is not None:
        dtxt = "（差 %+g%s）" % (diff, u)
    elif diff_text:
        dtxt = "（差 %s%s）" % (diff_text, u)
    else:
        dtxt = ""
    return {
        "kind": "forecast_item", "kind_label": KIND_LABEL["forecast_item"],
        "code": ctx["code"], "name": ctx["name"], "announced_at": ctx["pubdate"],
        "target": None, "target_text": NONE, "time_text": None, "impact_period": period,
        "summary": "%s%s: 前回 %s%s → 今回 %s%s%s" % (
            item, "" if period == NONE else "[%s]" % period, prev, u, new, u, dtxt),
        "item": item, "unit": unit, "prev": prev, "new": new, "diff": diff, "diff_text": diff_text, "values": [prev, new],
        "verified": verified, "verify_basis": basis if verified else None, "note": note,
        "quote": _quote(line), "page": page_no, "url": ctx["url"], "title": ctx["title"],
        "checked_at": ctx["checked_at"], "origin": "official", "extractor": EXT_VERSION,
        "confirmed": False, "needs_review": not verified,
        "id": event_key(ctx["code"], "forecast_item", item + prev + new + ctx["pubdate"][:10]),
    }


def _check_diff(pt, nt, dt_tok):
    """差額欄の1項目が、前回・今回の値と計算で合うか。"""
    if dt_tok is None or dt_tok[0] in ("-", "－", "―"):
        return False
    pb, nb, db = _bounds(pt), _bounds(nt), _bounds(dt_tok)
    if pb is None or nb is None or db is None or pb[0] != pb[1]:
        return False
    return abs((nb[0] - pb[0]) - db[0]) < 1e-6 and abs((nb[1] - pb[0]) - db[1]) < 1e-6


DASH_TOK = re.compile(r"(" + RNG + r"(?:[～〜~]" + RNG + r")?)|(?<![\d])([-－―])(?![\d])")


def _diff_tokens(line):
    rest = re.sub(r"^増減額[（(][^）)]*[）)]", "", line)
    out = []
    for m in DASH_TOK.finditer(rest):
        if m.group(1):
            out.append(_tok_value(TOK_RE.match(m.group(1))))
        else:
            out.append(("-", None, None, False))
    return out


def _dividend_cols(lines, i):
    """配当表で、値の並び順(決定額/直近予想/前期実績 など)を見出し行から読む。分からなければ None。"""
    head = []
    for j in range(i - 1, max(-1, i - 9), -1):
        if re.match(r"^(?:1株当たり|配当金|効力発生日|配当原資)", lines[j]):
            break
        head.insert(0, lines[j])
    cols = [m.lastgroup for m in COL_RE.finditer(" ".join(head))]
    if "new" in cols and "prev" in cols:
        return cols
    return None


def extract_forecast_rows(page_text, page_no, ctx):
    """前回予想と今回予想を並べた表から、項目ごとの「前回→今回」を取り出す。
    表の向きは2通りに対応: (A)項目が行 (B)「前回予想」「今回予想」が行で項目が列。
    文書内の差額欄と計算が合ったものだけ verified とし、合わないものは「要確認」のままにする。
    「14円00銭」は円・銭をまとめて14.00として読む。配当表は列の見出し(決定額=今回、直近予想=前回)で向きを決める。"""
    t = norm(page_text)
    # 日本語の文字どうしの間の空白だけ除く（数字の区切りの空白は残す）
    lines = [re.sub(r"(?<=[^\sA-Za-z0-9]) (?=[^\sA-Za-z0-9])", "", re.sub(r"[ 　\t]+", " ", l).strip())
             for l in t.split("\n") if l.strip()]
    # 配当の「円銭 40．00」(全角ドット・円銭が値の前に付く書き方)は「40円00銭」にそろえる
    lines = [re.sub(r"円\s*銭\s*(\d[\d,]*)[.．](\d{2})", r"\1円\2銭", l) if re.match(r"^[\d.()（）※注]*(?:1株当たり)?配当金", l) else l
             for l in lines]
    if not re.search(r"前回(?:発表)?予想|修正後|今回修正|直近の配当予想|直近予想", " ".join(lines)):
        return []
    rows = []
    # (B) 前回行・今回行と、その直前までに現れた項目名の並び
    for i, l in enumerate(lines):
        if not PREV_LABEL.match(l):
            continue
        prev_txt = re.sub(r"^前回(?:発表)?予想[（(]?[A-Za-zＡ-Ｚ]?[）)]?", "", re.sub(r"[（(]\d{4}年\d{1,2}月\d{1,2}日(?:公表|発表)[）)]", "", l))
        ni = next((k for k in range(i + 1, min(len(lines), i + 3)) if NEW_LABEL.match(lines[k])), None)
        if ni is None:
            continue
        nxt = lines[ni]
        pt = _tokens(prev_txt)
        nt = _tokens(re.sub(r"^(?:今回(?:修正)?予想|修正後(?:予想)?|今回発表予想|修正予想)[（(]?[A-Za-zＡ-Ｚ]?[）)]?", "", nxt))
        # 見出し(項目名の行)は、直前4行まで。別の表の終わりに来たら止める
        hl = []
        for j in range(i - 1, max(-1, i - 9), -1):
            if re.match(r"^(?:増減|\(?（?ご参考|前期実績|今回|前回|実績値)", lines[j]):
                break
            hl.insert(0, lines[j])
        header = "".join(hl)   # 「親会社株主」「に帰属する」「当期純利益」のように行が分かれる見出しをつなぐ
        period = _period_above(lines, i)
        n = min(len(pt), len(nt))
        if n < 1:
            continue
        if all(x[3] for x in pt) and all(x[3] for x in nt) and re.search(r"配当", header):
            # 配当の前回・今回: 列は「第2四半期末」「期末」「合計」など
            labs = re.findall(r"第[1-4]四半期末|中間|期末|合計|年間", header)
            if not (len(pt) == len(nt) == len(labs)):
                continue
            for lab, a, b in zip(labs, pt, nt):
                rows.append(_row(ctx, page_no, "1株当たり配当金(%s)" % lab, a[0], b[0], l + " / " + nxt, True,
                                 "前回・今回の行見出しで確認", NONE))
            continue
        items = ITEM_RE.findall(header)
        if len(items) < n:
            continue
        items = items[-n:]
        dl = next((lines[k] for k in range(ni + 1, min(len(lines), ni + 3)) if lines[k].startswith("増減額")), None)
        dts = _diff_tokens(dl) if dl else []
        for k, (it, a, b) in enumerate(zip(items, pt[:n], nt[:n])):
            dtk = dts[k] if k < len(dts) else None
            ok = _check_diff(a, b, dtk)
            rows.append(_row(ctx, page_no, it, a[0], b[0], l + " / " + nxt, ok, "増減額の欄と計算が一致", period,
                             diff_text=(dtk[0] if dtk and dtk[0] != "-" else None),
                             unit=_unit_of(l, nxt, header)))
    # (A) 項目名で始まる行: 項目 前回 今回 [差額] [増減率]
    arows = []
    for i, l in enumerate(lines):
        if re.search(r"公表|基準日|決議|につき|となります|見込み|前年", l):
            continue
        m = re.match(r"^[\d.()（）※注]*(" + ITEM_RE.pattern + ")", l)
        if not m:
            continue
        rest = l[m.end():]
        # 文章(「売上高、営業利益…については、2026年8月7日に…」)や日付の入った行は表の行ではない
        if re.match(r"\s*[、，。はがをにの及と]", rest) or re.search(r"\d{1,4}年|\d{1,2}月\d{1,2}日", rest):
            continue
        toks = _tokens(rest)
        if len(toks) < 2:
            continue
        v = [x[1] for x in toks]
        # 売上高比率(構成比)の表: 「金額 比率 金額 比率 …」は前回・今回の表ではない
        if len(toks) >= 4 and all(x is not None for x in v[:4]) and v[1] <= 100 and v[3] <= 100 and v[0] > 100 and v[2] > 100:
            continue
        if m.group(1) in ("1株当たり配当金", "年間配当金") and all(x[3] for x in toks[:2]):
            cols = _dividend_cols(lines, i)
            if not cols or len(toks) < len(cols):
                continue   # 列の意味が見出しで確認できない配当行は登録しない
            vals = dict(zip(cols, toks))
            a, b = vals["prev"], vals["new"]
            arows.append(_row(ctx, page_no, m.group(1), a[0], b[0], l, True, "列の見出し(決定額/直近の配当予想)で確認", NONE))
            continue
        a, b = toks[0], toks[1]
        pv, nv = v[0], v[1]
        ok, basis = False, None
        if len(toks) >= 3 and pv is not None and nv is not None and v[2] is not None and abs((nv - pv) - v[2]) < 1e-6:
            ok, basis = True, "増減額の欄と計算が一致"
        elif len(toks) == 2 and pv is not None and pv == nv and re.search(r"\s[-－―]\s*$", rest):
            ok, basis = True, "増減額が「-」で前回と今回が同じ"
        prevl = lines[i - 1] if i else ""
        sect = prevl if (prevl and not re.search(r"\d", prevl) and len(prevl) <= 30 and not ITEM_RE.search(prevl)) else None
        r = _row(ctx, page_no, m.group(1), a[0], b[0], l, ok, basis, _period_above(lines, i),
                 unit=_unit_of(rest, *[lines[j] for j in range(i - 1, max(-1, i - 7), -1)]))
        r["section"] = sect
        arows.append(r)
    rows += arows
    # 同じ項目名・同じ期間の行が複数ある表は、事業別(セグメント)と連結、または中間期と通期が混ざっている可能性がある
    # → 区別できないので要確認に落とす（期間が違えば別の行として扱う）
    cnt = {}
    for r in rows:
        k = (r["item"], r["impact_period"])
        cnt[k] = cnt.get(k, 0) + 1
    for r in rows:
        if cnt[(r["item"], r["impact_period"])] > 1:
            r["verified"], r["verify_basis"], r["needs_review"] = False, None, True
            r["note"] = "同じ項目名・期間の行が複数あり、事業別/連結や中間期/通期の区別が確認できない"
    # 前回と今回が同じ値の行は、修正ではないので登録しない
    rows = [r for r in rows if r["diff"] != 0]
    return rows[:20]


def extract_document(pages, ctx):
    """pages: [str,...] (1ページ目が先頭)。重複は id で除去。"""
    seen, out = set(), []
    sub = bool(SUBSIDIARY_TITLE_RE.search(ctx.get("title", "")))
    for i, p in enumerate(pages, 1):
        for ev in extract_page(p, i, ctx) + extract_forecast_rows(p, i, ctx):
            if ev["id"] in seen:
                continue
            seen.add(ev["id"])
            if sub and ev["kind"] in ("forecast", "forecast_item", "revision_up", "revision_down"):
                ev["needs_review"] = True
                ev["note"] = "連結子会社の業績予想の資料。この銘柄コードの会社自身の予想ではない可能性"
                if ev["kind"] == "forecast_item":
                    ev["verified"], ev["verify_basis"] = False, None
            out.append(ev)
    # 表の数値(前回予想→今回予想)から、利益の上方・下方修正を機械的に判定して追加する。
    # 文章に「上方修正」と書かれていなくても、修正のお知らせ表で利益項目の差が全部同じ向きの場合だけ。
    if not sub and re.search(r"予想.*修正|修正.*予想", ctx.get("title", "")):
        groups = {}
        for ev in out:
            if ev["kind"] == "forecast_item" and ev["verified"] and ev.get("diff")                and re.search(r"営業利益|経常利益|純利益|当期利益|中間利益|四半期利益", ev["item"])                and not ev["item"].startswith(("1株当たり", "基本的1株当たり")):
                groups.setdefault((ev["page"], ev["impact_period"]), []).append(ev)
        for (page, per), evs in groups.items():
            signs = {1 if e["diff"] > 0 else -1 for e in evs}
            if len(signs) != 1:
                continue
            kind = "revision_up" if 1 in signs else "revision_down"
            if any(e["kind"] == kind and e["page"] == page and "table" not in e["id"] and not e.get("note") for e in out):
                continue   # 同じページの文章から既に拾っている
            q = _quote("; ".join("%s %s→%s" % (e["item"], e["prev"], e["new"]) for e in evs))
            out.append({
                "kind": kind, "kind_label": KIND_LABEL[kind], "code": ctx["code"], "name": ctx["name"],
                "announced_at": ctx["pubdate"], "target": None, "target_text": NONE, "time_text": None,
                "impact_period": per, "summary": "表の数値から判定: " + q, "quote": q, "page": page,
                "url": ctx["url"], "title": ctx["title"], "checked_at": ctx["checked_at"], "origin": "official",
                "extractor": EXT_VERSION, "confirmed": False, "needs_review": False,
                "note": "文章ではなく、前回予想・今回予想の表の差(増減額欄と一致)から機械的に判定",
                "id": event_key(ctx["code"], kind, "table%s%s%s" % (page, per, q)),
            })
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


def keep_event(e, cutoff, today):
    """古いIRの整理で残す項目。cutoff より新しい発表、またはこれからの時期を指す予定は消さない。
    時期が確定していない（要確認）予定も、発表から1年は残す。"""
    if (e.get("announced_at") or "")[:10] >= cutoff:
        return True
    t = e.get("target")
    if not t or e["kind"] in ("forecast", "forecast_item", "revision_up", "revision_down", "fx"):
        return False
    end = t.get("end") or t.get("start")
    if end:
        return end >= today
    one_year_ago = (dt.date.fromisoformat(today) - dt.timedelta(days=365)).isoformat()
    return (e.get("announced_at") or "")[:10] >= one_year_ago
