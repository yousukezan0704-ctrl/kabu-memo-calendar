"""日本語の日付表現を読み取る。

方針: 根拠のない補完はしない。年や事業年度が文中から決まらないものは
needs_review=True にして、原文(raw)と理由(reason)を必ず残す。
"""
import re
import datetime as dt
import calendar

_ZEN = str.maketrans("０１２３４５６７８９：／", "0123456789:/")
SEASONS = {"春": (3, 5), "夏": (6, 8), "秋": (9, 11), "冬": (12, 2)}


def norm(s):
    return (s or "").translate(_ZEN)


def _eom(y, m):
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def _season_range(year, s):
    a, b = SEASONS[s]
    if s == "冬":
        return dt.date(year, 12, 1), _eom(year + 1, 2)
    return dt.date(year, a, 1), _eom(year, b)


def _res(raw, start, end, precision, review=False, reason="", **extra):
    d = {
        "raw": raw,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "precision": precision,
        "needs_review": review,
        "reason": reason,
    }
    d.update(extra)
    return d


def _wareki(m):
    return 2018 + int(m)  # 令和N年 -> 2018+N


def parse_time(text):
    """会社が書いた時刻だけを返す。無ければ None。
    対応: 15時30分 / 15:30 / 15時 / 午後3時30分 / 10時半。「3時間」「15時点」は時刻ではない。
    複数あるときは文中で最も前にあるもの。"""
    t = norm(text)
    best = None
    for m in re.finditer(r"(午前|午後)?\s*(\d{1,2})\s*時\s*(?:(\d{1,2})\s*分|(半))?(?![間点])", t):
        h = int(m.group(2))
        mi = 30 if m.group(4) else int(m.group(3) or 0)
        if m.group(1) == "午後" and h < 12:
            h += 12
        if 0 <= h <= 24 and 0 <= mi < 60:
            best = (m.start(), h, mi)
            break
    m = re.search(r"(?<![\d:])(\d{1,2}):(\d{2})(?!\d)", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 24 and 0 <= mi < 60 and (best is None or m.start() < best[0]):
            best = (m.start(), h, mi)
    return None if best is None else "%02d:%02d" % (best[1], best[2])


def _time_after(t, pos):
    """日付の直後(30字以内)にある時刻だけを返す。次の日付や文の終わりを越えては探さない。"""
    seg = t[pos:pos + 30]
    cut = re.search(r"\d{1,4}年\d|\d{1,2}月\d{1,2}日|。", seg)
    if cut:
        seg = seg[:cut.start()]
    return parse_time(seg)


def parse_target(text, base, fy_end_month=None):
    """文から対象時期を1つ読み取る。base は発表日(date)。見つからなければ None。"""
    t = norm(text)

    # 1) 年月日が全部書いてある
    m = re.search(r"(令和)?(\d{1,4})年(\d{1,2})月(\d{1,2})日", t)
    if m:
        y = _wareki(m.group(2)) if m.group(1) else int(m.group(2))
        try:
            d = dt.date(y, int(m.group(3)), int(m.group(4)))
            return _res(m.group(0), d, d, "day", time=_time_after(t, m.end()))
        except ValueError:
            return _res(m.group(0), None, None, "unknown", True, "存在しない日付")

    # 2) 月日のみ（年は発表日から推定。推定した事実は残す）
    m = re.search(r"(?<![\d年])(\d{1,2})月(\d{1,2})日", t)
    if m:
        mo, da = int(m.group(1)), int(m.group(2))
        try:
            d = dt.date(base.year, mo, da)
        except ValueError:
            return _res(m.group(0), None, None, "unknown", True, "存在しない日付")
        # 発表日より半年以上前なら翌年とみなす（1月の発表で12月決算など）
        if (base - d).days > 180:
            d = dt.date(base.year + 1, mo, da)
        return _res(m.group(0), d, d, "day", False, "", year_inferred=True,
                    time=_time_after(t, m.end()))

    # 3) 「2027年3月期」= 決算期
    m = re.search(r"(令和)?(\d{4}|\d{1,2})年(\d{1,2})月期", t)
    if m:
        y = _wareki(m.group(2)) if m.group(1) else int(m.group(2))
        mo = int(m.group(3))
        end = _eom(y, mo)
        s = _eom(y - 1 if mo == 12 else y - 1, mo) + dt.timedelta(days=1)
        return _res(m.group(0), s, end, "fy", False, "決算期の指定")

    # 4) 年+月
    m = re.search(r"(令和)?(\d{4}|\d{1,2})年(\d{1,2})月(上旬|中旬|下旬|末|頃|ごろ)?", t)
    if m:
        y = _wareki(m.group(2)) if m.group(1) else int(m.group(2))
        mo = int(m.group(3))
        if 1 <= mo <= 12:
            return _res(m.group(0), dt.date(y, mo, 1), _eom(y, mo), "month")

    # 5) 年+季節 / 年度
    m = re.search(r"(\d{4})年(?:度)?(春|夏|秋|冬)", t)
    if m:
        s, e = _season_range(int(m.group(1)), m.group(2))
        return _res(m.group(0), s, e, "season")
    m = re.search(r"(令和)?(\d{4}|\d{1,2})年度", t)
    if m:
        y = _wareki(m.group(2)) if m.group(1) else int(m.group(2))
        if fy_end_month:
            end = _eom(y + (1 if fy_end_month < 4 else 0), fy_end_month) if fy_end_month != 12 else _eom(y, 12)
            start = _eom(end.year - 1, end.month) + dt.timedelta(days=1)
            return _res(m.group(0), start, end, "fy")
        return _res(m.group(0), dt.date(y, 4, 1), _eom(y + 1, 3), "fy", True,
                    "決算期不明のため4月始まりと仮定")

    # 6) 来春・今春・春
    m = re.search(r"(来|今|本)?(春|夏|秋|冬)(?![季期])", t)
    if m and (m.group(1) or re.search(r"(春|夏|秋|冬)(?:頃|ごろ|以降|までに|中|に|から)", t)):
        pre, s = m.group(1), m.group(2)
        cur_s, cur_e = _season_range(base.year, s)
        prev_s, prev_e = _season_range(base.year - 1, s)  # 冬(12-2)が年をまたぐ場合の前年分
        if pre in ("来",):
            # 同じ季節が今年まだ終わっていなければ「来」の意味が曖昧
            ongoing_or_future = cur_e >= base or prev_e >= base
            ys, ye = _season_range(base.year + 1, s)
            if ongoing_or_future:
                return _res(m.group(0), ys, ye, "season", True,
                            "発表日の時点で今年の%sがまだ終わっておらず、来%sが今年か来年か判断できない" % (s, s))
            return _res(m.group(0), ys, ye, "season")
        if pre in ("今", "本"):
            if cur_e >= base or prev_e >= base:
                a, b = (prev_s, prev_e) if prev_e >= base else (cur_s, cur_e)
                return _res(m.group(0), a, b, "season")
            return _res(m.group(0), cur_s, cur_e, "season", True, "発表日より前の季節を指している可能性")
        # 修飾なしの季節名: 直近で終わっていない同季節を仮置きして必ず確認対象
        if cur_e >= base:
            a, b = cur_s, cur_e
        else:
            a, b = _season_range(base.year + 1, s)
        return _res(m.group(0), a, b, "season", True, "年の指定がない（直近の該当季節を仮置き）")

    # 7) 年度内・来年度など（事業年度の末日が分からないと確定できない）
    m = re.search(r"(年度内|今年度|当年度|来年度|次年度|今期|当期|来期|次期|翌期|下期|上期)", t)
    if m:
        w = m.group(1)
        if fy_end_month and w in ("年度内", "今年度", "当年度", "今期", "当期"):
            y = base.year
            end = _eom(y, fy_end_month)
            if end < base:
                end = _eom(y + 1, fy_end_month)
            start = _eom(end.year - 1, end.month) + dt.timedelta(days=1)
            return _res(w, base, end, "fy")
        if fy_end_month and w in ("来年度", "次年度", "来期", "次期", "翌期"):
            y = base.year
            end = _eom(y, fy_end_month)
            if end < base:
                end = _eom(y + 1, fy_end_month)
            e2 = _eom(end.year + 1, fy_end_month)
            return _res(w, end + dt.timedelta(days=1), e2, "fy")
        return _res(w, None, None, "fy", True, "会社の決算期が文中にないため期間を確定できない")

    # 8) 年のみ
    m = re.search(r"(\d{4})年(?!度)", t)
    if m:
        y = int(m.group(1))
        return _res(m.group(0), dt.date(y, 1, 1), dt.date(y, 12, 31), "year", True, "年のみの記載")

    return None
