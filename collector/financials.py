"""決算短信のXBRL(inline XBRL)から、構造化された財務数値を取り出す。

取得元: TDnet由来(非公式API経由)。利用条件は未確認なので、画面にもそう明示すること。
方針: タグに無い項目・読めない項目は None のまま(推測値で埋めない)。

使い方(collect.py から):
    rec = parse_summary_zip(zip_bytes, meta)          # 決算短信でなければ None
    if rec: doc = merge_period(load(path, None), rec, code, name); save(path, doc)

単位の扱い(ix:nonFraction の scale / sign / format を解釈する):
    金額  ... 百万円に直す(scale=6 の "33,178" -> 33178。scale=3(千円)なら 1234 -> 1.234)
    %     ... 画面表記のまま(scale=-2 の "0.9" -> 0.9)
    円/株 ... scale を掛けた実数(EPS 287.24 円、発行済株式 2,296,176 株)
    sign="-" は負、format の zerodash(「－」)は 0、xsi:nil は None。
"""
import copy
import datetime as dt
import html
import io
import re
import unicodedata
import zipfile
from decimal import Decimal, InvalidOperation

SOURCE = "TDnet決算短信(XBRL)"
DOC_SOURCE = "TDnet由来(非公式API経由・利用条件は未確認)"
JST = dt.timezone(dt.timedelta(hours=9))

# ---- 項目名 -> 出力キー。IFRS/米国基準は末尾に IFRS / US が付くので除いてから照合する ----
_SALES = ("NetSales", "Sales", "OperatingRevenue", "OperatingRevenues", "OperatingRevenue1",
          "OperatingRevenue2", "Revenue", "Revenues", "NetSalesAndOperatingRevenue")
_OPINC = ("OperatingIncome", "OperatingProfit", "OperatingProfitLoss", "OperatingIncomeLoss")
_ORDINC = ("OrdinaryIncome", "OrdinaryProfit", "OrdinaryIncomeLoss")
_NETINC = ("ProfitAttributableToOwnersOfParent", "ProfitLossAttributableToOwnersOfParent",
           "NetIncomeAttributableToOwnersOfParent")  # 少数株主分を含む「当期利益」は推測で代用しない
# 非連結の短信では「四半期(当期)純利益」が NetIncome で出る。連結書類では使わない(少数株主分を含みうるため)
_NETINC_SOLO = ("NetIncome", "NetIncomeLoss", "ProfitLoss")
_EPS = ("NetIncomePerShare", "BasicEarningsPerShare", "BasicNetIncomePerShare")


def _alias(names, prefix=""):
    return tuple(prefix + n for n in names)


_RESULT_TAGS = {"sales": _SALES, "operating_income": _OPINC, "ordinary_income": _ORDINC,
                "net_income": _NETINC}
_CHANGE_TAGS = {k: _alias(v, "ChangeIn") + _alias(v, "ChangesIn") for k, v in _RESULT_TAGS.items()}
_BALANCE_TAGS = {
    "net_assets": ("NetAssets", "TotalEquity", "Equity"),
    "equity_ratio_pct": ("CapitalAdequacyRatio", "EquityAttributableToOwnersOfParentToTotalAssetsRatio",
                         "EquityRatio"),
    "bps": ("NetAssetsPerShare", "EquityAttributableToOwnersOfParentPerShare", "EquityPerShare"),
    "shares_issued": ("NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock",),
    "treasury_shares": ("NumberOfTreasuryStockAtTheEndOfFiscalYear",),
}
_SUFFIXES = ("IFRS", "USGAAP", "US", "JMIS")

PERIOD_TYPES = {None: "通期", 1: "第1四半期", 2: "第2四半期", 3: "第3四半期"}


# ===================== 低レベル: タグと数値の読み取り =====================
_NF = re.compile(r"<ix:nonFraction\b([^>]*?)(?:/>|>(.*?)</ix:nonFraction>)", re.S)
_NN = re.compile(r"<ix:nonNumeric\b([^>]*?)(?:/>|>(.*?)</ix:nonNumeric>)", re.S)
_CTX = re.compile(r"<xbrli:context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</xbrli:context>", re.S)
_TAGS = re.compile(r"<[^>]+>")


def _attr(attrs, key):
    m = re.search(r"(?<![\w:-])" + re.escape(key) + r"\s*=\s*\"([^\"]*)\"", attrs)
    return m.group(1) if m else None


def _strip_name(name):
    """'tse-ed-t:NetSalesIFRS' -> 'NetSales'"""
    n = name.split(":")[-1]
    for s in _SUFFIXES:
        if n.endswith(s) and len(n) > len(s):
            return n[: -len(s)]
    return n


def _kind_value(text, fmt, scale, sign, nil):
    """nonFraction の中身を Decimal(実数)にする。読めなければ None。"""
    if nil:
        return None
    f = (fmt or "").split(":")[-1].lower().replace("-", "")
    t = unicodedata.normalize("NFKC", html.unescape(_TAGS.sub("", text or ""))).strip()
    if f in ("zerodash", "fixedzero", "numdotdecimalzero"):
        d = Decimal(0)
    else:
        if f == "numcommadecimal":
            t = t.replace(".", "").replace(" ", "").replace(",", ".")
        else:
            t = t.replace(",", "").replace(" ", "")
        if not t:
            return None
        try:
            d = Decimal(t)
        except InvalidOperation:
            return None
    if sign == "-":
        d = -d
    if scale:
        try:
            d = d.scaleb(int(scale))
        except ValueError:
            return None
    return d


def _num(d, mode):
    """Decimal(実数)を出力の単位に直す。mode: money(百万円) / pct / raw(円・株)"""
    if d is None:
        return None
    if mode == "money":
        d = d.scaleb(-6)
    elif mode == "pct":
        d = d.scaleb(2)  # scale=-2 で書かれた 0.009 -> 0.9(画面の表記)
    d = d.normalize() if d != 0 else Decimal(0)
    if d == d.to_integral_value():
        return int(d)
    return float(round(d, 6))


def _parse_facts(htm):
    """-> (facts, texts, contexts)
    facts: {(項目名, contextRef): Decimal|None}  texts: {項目名: 文字列}  contexts: {id: (start,end,instant)}"""
    facts, texts = {}, {}
    for m in _NF.finditer(htm):
        a = m.group(1)
        name, ctx = _attr(a, "name"), _attr(a, "contextRef")
        if not name or not ctx:
            continue
        nil = (_attr(a, "xsi:nil") or "").lower() == "true"
        val = _kind_value(m.group(2), _attr(a, "format"), _attr(a, "scale"), _attr(a, "sign"), nil)
        key = (_strip_name(name), ctx)
        if facts.get(key) is None:  # 同じ項目が2回出たら、値があるほうを残す
            facts[key] = val
    for m in _NN.finditer(htm):
        a = m.group(1)
        name = _attr(a, "name")
        if name:
            t = html.unescape(_TAGS.sub("", m.group(2) or "")).strip()
            texts.setdefault(_strip_name(name), t)
    contexts = {}
    for cid, body in _CTX.findall(htm):
        g = lambda tag: (re.search(r"<xbrli:%s>\s*([^<\s]+)\s*<" % tag, body) or [None, None])[1]
        contexts[cid] = (g("startDate"), g("endDate"), g("instant"))
    return facts, texts, contexts


def _parse_date(s):
    """'2026-09-20' や '2026年11月２日' を 'YYYY-MM-DD' に。読めなければ None。"""
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s) or re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


# ===================== コンテキストの選択 =====================
def _ctx_parts(cid):
    parts = cid.split("_")
    return parts[0], set(parts[1:])


class _Ctx:
    """contextRef 名(例 CurrentYearDuration_ConsolidatedMember_ResultMember)から値を引く道具。"""

    def __init__(self, facts):
        self.facts = facts

    def has_member(self, member):
        """書類内のどこかの contextRef に、そのメンバー(完全一致)が付いているか。"""
        return any(member in _ctx_parts(cid)[1] for (_n, cid) in self.facts)

    def get(self, names, base, scope, members=(), mode="money", prefs=("ConsolidatedMember", "NonConsolidatedMember", None)):
        """names: 項目名の候補 / base: 'CurrentYearDuration' など / scope: 'Result'|'Forecast'
        members: 追加で必要なメンバー(例 'AnnualMember')。連結を優先、なければ個別、なければ区分なし。"""
        want = {scope + "Member", *members}
        for pref in prefs:
            for name in names:
                for (n, cid), v in self.facts.items():
                    if n != name or v is None:
                        continue
                    b, mem = _ctx_parts(cid)
                    if b != base or not want <= mem:
                        continue
                    if "LowerMember" in mem or "UpperMember" in mem:
                        continue
                    if pref is None:
                        if "ConsolidatedMember" in mem or "NonConsolidatedMember" in mem:
                            continue
                    elif pref not in mem:
                        continue
                    # 余計なメンバー(四半期末など)が付いたものは、指定が無い限り除く
                    extra = mem - want - {"ConsolidatedMember", "NonConsolidatedMember"}
                    if extra:
                        continue
                    return _num(v, mode)
        return None


# ===================== 決算短信1通の解釈 =====================
def _is_earnings_title(title):
    t = title or ""
    return ("決算短信" in t) and not re.search(r"補足|説明|参考|スライド|プレゼン", t)


def _summary_htm(z):
    cands = [n for n in z.namelist() if "/Summary/" in n.replace("\\", "/") and n.endswith("-ixbrl.htm")]
    return sorted(cands)[0] if cands else None


def _period_from_title(title):
    t = unicodedata.normalize("NFKC", title or "")
    m = re.search(r"第\s*([123])\s*四半期", t)
    if m:
        return int(m.group(1))
    if "中間期" in t:
        return 2
    return None


def parse_summary_zip(zip_bytes, meta):
    """TDnetのXBRL zip(bytes)から財務数値の dict を作る。決算短信でない/読めない場合は None。"""
    meta = meta or {}
    title = meta.get("title") or ""
    if title and not _is_earnings_title(title):
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
        name = _summary_htm(z)
        if not name:
            return None
        htm = z.read(name).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, OSError):
        return None

    facts, texts, contexts = _parse_facts(htm)
    if not facts:
        return None
    doc_name = texts.get("DocumentName") or ""
    if doc_name and "決算短信" not in doc_name:
        return None  # 書類名が決算短信でない(補足資料など)

    # --- 期間の種類 ---
    q = None
    for (n, cid), v in facts.items():
        if n == "QuarterlyPeriod" and v is not None and int(v) in (1, 2, 3):
            q = int(v)
            break
    if q is None:
        q = _period_from_title(title or doc_name)
    ptype = PERIOD_TYPES[q]
    dur = "CurrentYearDuration" if q is None else "CurrentAccumulatedQ%dDuration" % q
    inst = "CurrentYearInstant" if q is None else "CurrentAccumulatedQ%dInstant" % q
    # 会社予想(通期)は、通期の短信では「来期」、四半期の短信では「当期」の通期
    fdur = "NextYearDuration" if q is None else "CurrentYearDuration"

    c = _Ctx(facts)
    # 基準・連結/非連結の判定。連結の印(ConsolidatedMember)が書類のどこにも無く、非連結の印だけがある書類を「非連結書類」とする
    is_solo = c.has_member("NonConsolidatedMember") and not c.has_member("ConsolidatedMember")
    is_ifrs = bool(re.search(r'name="[^"]*:\w+IFRS"', htm))
    basis = "非連結" if is_solo else ("連結" if c.has_member("ConsolidatedMember") else None)
    solo_prefs = ("NonConsolidatedMember", None)
    used_solo_net = []

    def solo_net(base, scope, names, mode="money"):
        """非連結書類のときだけ NetIncome 系を拾う(連結書類では None のまま)。"""
        if not is_solo:
            return None
        v = c.get(names, base, scope, mode=mode, prefs=solo_prefs)
        if v is not None:
            used_solo_net.append(scope)
        return v

    results = {k: c.get(v, dur, "Result") for k, v in _RESULT_TAGS.items()}
    if results["net_income"] is None:
        results["net_income"] = solo_net(dur, "Result", _NETINC_SOLO)
    results["eps"] = c.get(_EPS, dur, "Result", mode="raw")
    yoy = {k: c.get(v, dur, "Result", mode="pct") for k, v in _CHANGE_TAGS.items()}
    if yoy["net_income"] is None:
        yoy["net_income"] = solo_net(dur, "Result", _alias(_NETINC_SOLO, "ChangeIn"), mode="pct")

    fc = {"period": "通期"}
    for k, v in _RESULT_TAGS.items():
        fc[k] = c.get(v, fdur, "Forecast")
    if fc["net_income"] is None:
        fc["net_income"] = solo_net(fdur, "Forecast", _NETINC_SOLO)
    fc["eps"] = c.get(_EPS, fdur, "Forecast", mode="raw")
    fc["dps"] = c.get(("DividendPerShare",), fdur, "Forecast", members=("AnnualMember",), mode="raw")
    fc["yoy_pct"] = {k: c.get(v, fdur, "Forecast", mode="pct") for k, v in _CHANGE_TAGS.items()}
    if fc["yoy_pct"]["net_income"] is None:
        fc["yoy_pct"]["net_income"] = solo_net(fdur, "Forecast", _alias(_NETINC_SOLO, "ChangeIn"), mode="pct")

    dividend = {
        "annual_actual": c.get(("DividendPerShare",), dur, "Result", members=("AnnualMember",), mode="raw"),
        "annual_forecast": fc["dps"],
    }
    balance = {}
    for k, v in _BALANCE_TAGS.items():
        mode = {"net_assets": "money", "equity_ratio_pct": "pct"}.get(k, "raw")
        balance[k] = c.get(v, inst, "Result", mode=mode)

    has_any = any(x is not None for x in results.values()) or any(
        fc[k] is not None for k in ("sales", "operating_income", "ordinary_income", "net_income", "eps"))
    if not has_any:
        return None

    # --- 日付 ---
    fye = _parse_date(texts.get("FiscalYearEnd"))
    end = None
    for cid, (s, e, i) in contexts.items():
        if cid == dur or cid.startswith(dur + "_"):
            end = e
            break
    period_end = _parse_date(end)
    if period_end is None and q is None:
        period_end = fye
    if fye is None and q is None:
        fye = period_end

    rec = {
        "id": meta.get("id"),
        "announced_at": meta.get("pubdate"),
        "period_type": ptype,
        "fiscal_year_end": fye,
        "period_end": period_end,
        "doc_title": title or doc_name,
        "url": meta.get("url"),
        "unit": "百万円",
        "results": results,
        "yoy_pct": yoy,
        "forecast": fc,
        "dividend": dividend,
        "balance": balance,
        "source": SOURCE,
        "basis": basis,
    }
    if used_solo_net:
        rec["results_note"] = "非連結の書類のため、純利益は「四半期(当期)純利益」(NetIncome)の値。親会社株主帰属ではない"
    # 無い項目をNoneのまま保つ理由(推測で埋めない)
    reasons = {}
    if is_ifrs:
        if results["ordinary_income"] is None:
            reasons["ordinary_income"] = "IFRSには経常利益の項目が無いため(税引前利益などで代用しない)"
        if results["operating_income"] is None:
            reasons["operating_income"] = "IFRSの短信に営業利益のタグが無いため(税引前利益などで代用しない)"
    if results["net_income"] is None and not is_solo:
        reasons["net_income"] = "親会社株主に帰属する利益のタグが無い(少数株主分を含む利益では代用しない)"
    if reasons:
        rec["missing_reason"] = reasons
    return rec


# ===================== 会社ごとの履歴ファイルへのマージ =====================
def _sort_key(p):
    return (p.get("period_end") or "", p.get("announced_at") or "")


def merge_period(doc, rec, code, name, now=None):
    """docs/data/financials/<code>.json の中身(doc)に rec を足した新しい dict を返す(doc は書き換えない)。
    - 同じ id は重複させない(既存を残す)
    - 同じ(fiscal_year_end, period_type)で別id は『訂正』: 新しいほうに supersedes=旧id、旧は残す
    - 既存の期は絶対に消さない。periods は period_end の新しい順。"""
    out = copy.deepcopy(doc) if doc else {}
    out.setdefault("periods", [])
    out["code"] = code
    out["name"] = name or out.get("name")
    out["source"] = DOC_SOURCE
    if rec is None:
        return out
    periods = out["periods"]
    for i, p in enumerate(periods):
        if p.get("id") == rec.get("id"):
            # 同じ書類は2回入れない。ただしパーサー改良後の再解析は、解析結果だけ新しくする(訂正の履歴は引き継ぐ)
            new = copy.deepcopy(rec)
            for k in ("supersedes", "superseded_by"):
                if p.get(k) is not None:
                    new[k] = p[k]
            periods[i] = new
            return out
    new = copy.deepcopy(rec)
    same = [p for p in periods
            if p.get("fiscal_year_end") == new.get("fiscal_year_end")
            and p.get("period_type") == new.get("period_type")]
    if same:
        latest = max(same, key=lambda p: p.get("announced_at") or "")
        if (new.get("announced_at") or "") >= (latest.get("announced_at") or ""):
            new["supersedes"] = latest.get("id")
        else:  # 古い書類を後から取り込んだ場合: 新しい側が有効
            new["superseded_by"] = latest.get("id")
    periods.append(new)
    periods.sort(key=_sort_key, reverse=True)
    now = now or dt.datetime.now(JST)
    out["updated_at"] = now.isoformat(timespec="seconds") if hasattr(now, "isoformat") else str(now)
    return out


# ===================== 業績予想の修正(tse-rvfc)の解釈 =====================
# 『業績予想の修正に関するお知らせ』のTDnet公式XBRL。単位は金額=百万円、EPS/配当=円、率=%。
# 方針: 前回発表予想(PreviousMember)と今回修正予想(CurrentMember)の ForecastMember だけを読む。
#       LowerMember/UpperMember(予想レンジ)や四半期メンバーが付いた別枠のコンテキストは、
#       値があっても採用しない(別の意味の数値と混ざるため)。読めない項目は None のまま。
REVISION_SOURCE = "公式XBRL(tse-rvfc)"
_REV_ITEMS = (
    ("sales", _SALES),
    ("operating_income", _OPINC),
    ("ordinary_income", _ORDINC),
    # 連結の「親会社株主に帰属する当期純利益」は書式によって ProfitAttributable... か NetIncome のタグで出る
    ("net_income", _NETINC + _NETINC_SOLO),
    ("eps", _EPS),
)
_REV_PERIODS = (("CurrentYearDuration", "通期"), ("CurrentAccumulatedQ1Duration", "第1四半期累計"),
                ("CurrentAccumulatedQ2Duration", "第2四半期累計"), ("CurrentAccumulatedQ3Duration", "第3四半期累計"))
_REV_DIV_MEMBERS = {"FirstQuarterMember": "q1", "SecondQuarterMember": "q2", "ThirdQuarterMember": "q3",
                    "YearEndMember": "year_end", "AnnualMember": "annual"}
_NIL_NF = re.compile(r"<ix:nonFraction\b[^>]*?xsi:nil\s*=\s*\"true\"[^>]*?/>", re.S)
_REV_HTM = re.compile(r"(?:^|/)tse-rv[a-z]{2}-[^/]*-ixbrl\.htm$", re.I)


def _rev_text(s):
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[^\x00-\x7f]) (?=[^\x00-\x7f])", "", s)  # 全角どうしの間の改行由来の空白を除く
    return s or None


def _rev_date(s):
    """'令和8年11月2日' / '2026年11月2日' / '2026-11-02' -> 'YYYY-MM-DD'。読めなければ None。"""
    if not s:
        return None
    t = unicodedata.normalize("NFKC", s)
    m = re.search(r"令和\s*(\d{1,2}|元)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", t)
    if m:
        try:
            y = 2018 + (1 if m.group(1) == "元" else int(m.group(1)))
            return dt.date(y, int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    return _parse_date(t)


def _rev_pick(facts, base, scope, which, names, mode):
    """facts から (base, scope, which, Forecast) ちょうどのコンテキストの値を引く。余計なメンバー付きは除く。"""
    want = {scope, which + "Member", "ForecastMember"}
    for name in names:
        for (n, cid), v in facts.items():
            if n != name or v is None:
                continue
            b, mem = _ctx_parts(cid)
            if b == base and mem == want:
                return _num(v, mode)
    return None


def _rev_direction(items):
    ds = [it["diff"] for it in items if it["item"] in ("operating_income", "ordinary_income", "net_income")
          and it["diff"] is not None]
    if not ds:
        return None
    if all(d == 0 for d in ds):
        return "flat"
    if all(d >= 0 for d in ds):
        return "up"
    if all(d <= 0 for d in ds):
        return "down"
    return "mixed"


def _rev_section(facts, base, scope_member):
    items = []
    for key, names in _REV_ITEMS:
        mode = "raw" if key == "eps" else "money"
        prev = _rev_pick(facts, base, scope_member, "Previous", names, mode)
        new = _rev_pick(facts, base, scope_member, "Current", names, mode)
        if prev is None and new is None:
            continue
        diff = pct = None
        if key != "eps":
            diff = _rev_pick(facts, base, scope_member, "Current", _alias(names, "AmountChange"), "money")
            pct = _rev_pick(facts, base, scope_member, "Current",
                            _alias(names, "ChangeIn") + _alias(names, "ChangesIn"), "pct")
        diff_src = pct_src = None
        if diff is not None:
            diff_src = "XBRL"
        elif prev is not None and new is not None:
            diff, diff_src = round(new - prev, 6), "計算"
            diff = int(diff) if diff == int(diff) else diff
        if pct is not None:
            pct_src = "XBRL"
        elif key != "eps" and prev not in (None, 0) and new is not None:
            pct, pct_src = round((new - prev) / abs(prev) * 100, 1), "計算"
        it = {"item": key, "prev": prev, "new": new, "diff": diff, "diff_pct": pct,
              "diff_source": diff_src, "pct_source": pct_src}
        if diff_src == "XBRL" and prev is not None and new is not None and abs((new - prev) - diff) > 1e-6:
            it["diff_consistent"] = False  # 開示された増減額が 今回-前回 と合わない(そのまま載せ、確認が必要)
        items.append(it)
    return items


def parse_revision_zip(zip_bytes, meta):
    """『業績予想の修正に関するお知らせ』のXBRL zip(bytes) -> dict。読めない/対象外なら None。
    主(items)は 通期の連結(無ければ通期の非連結、さらに無ければ四半期累計)。同じ期間の非連結は non_consolidated、
    別の期間(例: 第2四半期累計)は other_periods に入れる。配当の修正は dividend(円/株)。"""
    meta = meta or {}
    title = meta.get("title") or ""
    if title and "修正" not in title:
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = sorted(n for n in z.namelist() if _REV_HTM.search(n.replace("\\", "/")))
        if not names:
            return None
        htm = z.read(names[0]).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError, OSError):
        return None
    htm = _NIL_NF.sub("", htm)  # xsi:nil の自己閉じタグを先に除く(入れ子対応が崩れるため)
    facts, texts, contexts = _parse_facts(htm)
    if not facts:
        return None
    doc_name = texts.get("DocumentName") or ""
    if doc_name and "修正" not in doc_name:
        return None

    sections = {}  # (期間名, 範囲) -> (base, items)
    for base, plabel in _REV_PERIODS:
        for member, label in (("ConsolidatedMember", "連結"), ("NonConsolidatedMember", "非連結")):
            items = _rev_section(facts, base, member)
            if items:
                sections[(plabel, label)] = (base, items)

    # 配当予想の修正(DividendPerShare。連結/非連結どちらのメンバーが付いていても同じ1株配当として扱う)
    allowed = {"ForecastMember", "PreviousMember", "CurrentMember", "ConsolidatedMember",
               "NonConsolidatedMember"} | set(_REV_DIV_MEMBERS)
    div = {}
    for (n, cid), v in facts.items():
        if n != "DividendPerShare" or v is None:
            continue
        b, mem = _ctx_parts(cid)
        if b != "CurrentYearDuration" or "ForecastMember" not in mem or not mem <= allowed:
            continue
        which = "prev" if "PreviousMember" in mem else ("new" if "CurrentMember" in mem else None)
        fam = [_REV_DIV_MEMBERS[m] for m in mem if m in _REV_DIV_MEMBERS]
        if which and len(fam) == 1:
            div.setdefault(fam[0], {})[which] = _num(v, "raw")
    dividend = None
    if div:
        dividend = {k: {"prev": d.get("prev"), "new": d.get("new")} for k, d in sorted(div.items())}
        dividend["reason_text"] = _rev_text(texts.get("ReasonForDividendForecastCorrection"))

    if not sections and not dividend:
        return None

    def ctx_range(base, member):
        for cid, (s, e, _i) in contexts.items():
            b, mem = _ctx_parts(cid)
            if b == base and member in mem and s and e:
                return s, e
        return None, None

    def pack(plabel, scope):
        base, items = sections[(plabel, scope)]
        s, e = ctx_range(base, "ConsolidatedMember" if scope == "連結" else "NonConsolidatedMember")
        return {"scope": scope, "period": plabel, "period_start": s, "period_end": e,
                "items": items, "direction": _rev_direction(items)}

    code5 = (texts.get("SecuritiesCode") or "").strip()
    out = {"kind": "業績予想修正" if sections else "配当予想修正",
           "code": code5[:-1] if len(code5) == 5 else (code5 or None),
           "announced_date": _rev_date(texts.get("ReportingDateOfFinancialForecastCorrection"))
           or (meta.get("pubdate") or "")[:10] or None,
           "scope": None, "period": None, "items": [], "direction": None,
           "reason_text": _rev_text(texts.get("ReasonForForecastCorrection")),
           "non_consolidated": None, "other_periods": [], "dividend": dividend,
           "basis": REVISION_SOURCE}
    if sections:
        order = [p for _b, p in _REV_PERIODS]
        have = sorted({p for (p, _s) in sections}, key=order.index)
        mp = "通期" if "通期" in have else have[0]
        ms = "連結" if (mp, "連結") in sections else "非連結"
        main = pack(mp, ms)
        out.update({k: main[k] for k in ("scope", "period", "period_start", "period_end", "items", "direction")})
        if ms == "連結" and (mp, "非連結") in sections:
            out["non_consolidated"] = pack(mp, "非連結")
        for p in have:
            for s in ("連結", "非連結"):
                if (p, s) in sections and (p, s) != (mp, ms) and not (p == mp and s == "非連結" and ms == "連結"):
                    out["other_periods"].append(pack(p, s))
    return out
