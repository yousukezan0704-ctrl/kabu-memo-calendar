"""開示タイトルの分類と、「過去の決算短信の発表日時」の一覧。

注意: ここで出す日時は『過去の実績』であり、今回(次回)の確定時刻ではない。
reference_next() の戻り値は『昨年同期の発表日時(参考・未確定)』で、会社が公表した予定ではない。
"""
import datetime as dt
import re
import unicodedata

CATEGORIES = ("決算短信", "業績修正", "配当修正", "自社株", "決算説明資料", "その他")
PAST_NOTE = "過去の実績の発表日時です。今回の確定時刻ではありません。"
REF_LABEL = "昨年同期の発表日時(参考・未確定)"


def _n(s):
    return unicodedata.normalize("NFKC", s or "")


def classify_title(title):
    t = _n(title)
    # 補足・説明資料は「決算短信」を含んでいても資料のほうとして扱う
    if re.search(r"決算説明|決算補足|補足説明資料|補足資料|決算概要|決算スライド|決算プレゼン", t):
        return "決算説明資料"
    if "決算短信" in t:
        return "決算短信"
    if re.search(r"自己株式|自社株", t):
        return "自社株"
    has_div = "配当" in t
    # 「業績予想の修正」「業績予想及び配当予想の修正」は業績修正、配当だけの修正は配当修正
    if re.search(r"修正|変更|差異|上方|下方", t) and re.search(r"業績|通期予想|連結予想|見通し|差異", t):
        return "業績修正"
    if has_div and re.search(r"修正|増配|減配|無配|変更|予想", t):
        return "配当修正"
    return "その他"


def _period_type(title):
    t = _n(title)
    m = re.search(r"第\s*([123])\s*四半期", t)
    if m:
        return "第%s四半期" % m.group(1)
    if "中間期" in t:
        return "第2四半期"
    return "通期"


def _fiscal_label(title):
    m = re.search(r"(\d{4})年\s*(\d{1,2})月期", _n(title))
    return "%s年%s月期" % (m.group(1), int(m.group(2))) if m else None


def _pick(item, key):
    if key in item:
        return item[key]
    inner = item.get("Tdnet")
    if isinstance(inner, dict):
        return inner.get(key)
    return None


def earnings_history(items):
    """同じ会社の開示一覧(title, pubdate を持つ dict のリスト)から、
    過去の『決算短信』の発表日時を新しい順に返す。
    各要素: {"code","pubdate","period_type","fiscal_label","title","correction","kind":"過去の実績","note"}
    ※過去の実績であり、次回の確定時刻ではない。"""
    seen, out = set(), []
    for it in items or []:
        title = _pick(it, "title") or ""
        pub = _pick(it, "pubdate")
        if not pub or classify_title(title) != "決算短信":
            continue
        code = _pick(it, "company_code") or _pick(it, "code")
        ptype = _period_type(title)
        key = (code, pub, ptype)
        if key in seen:
            continue
        seen.add(key)
        out.append({"code": code, "pubdate": pub, "period_type": ptype,
                    "fiscal_label": _fiscal_label(title), "title": title,
                    "correction": "訂正" in title, "kind": "過去の実績", "note": PAST_NOTE})
    out.sort(key=lambda x: x["pubdate"], reverse=True)
    return out


def _to_date(x):
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x)[:10])


def _plus_year(d):
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # 2/29
        return d.replace(year=d.year + 1, day=28)


def reference_next(history, today, period_type=None):
    """今日以降でいちばん近い『昨年同期の発表日時(参考・未確定)』を返す。なければ None。
    昨年の発表日に1年を足した日(日付だけの目安。曜日は動く)を示す。会社の公表予定ではない。"""
    today = _to_date(today)
    best = None
    for h in history or []:
        if h.get("correction") or not h.get("pubdate"):
            continue
        if period_type and h.get("period_type") != period_type:
            continue
        orig = _to_date(h["pubdate"])
        shifted = _plus_year(orig)
        if shifted < today or orig > today:
            continue
        if best is None or shifted < best[0]:
            best = (shifted, h)
    if not best:
        return None
    shifted, h = best
    return {"label": REF_LABEL, "confirmed": False, "period_type": h.get("period_type"),
            "last_year_pubdate": h["pubdate"], "approx_date": shifted.isoformat(),
            "approx_time": str(h["pubdate"])[11:16] or None,
            "note": "昨年の実績からの目安です。会社が公表した予定ではありません。"}
