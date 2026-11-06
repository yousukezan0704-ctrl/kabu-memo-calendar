/* 収集済みデータ(docs/data/*.json)の読み込みと、カレンダー用の「予定」への変換。
   サンプルは必ず sample:true を付け、画面でも「サンプル」と表示する。 */
(function (K) {
  K.data = { status: null, events: [], index: [], themes: [], sample: null, loadErrors: [] };

  /* ---------------------------------------------------------------------
     データ取得の窓口（ここ1箇所）。取得元を切り替える:
       ・「非公開リポジトリ接続」が設定済み → GitHub API で private リポジトリの data/<パス> を取得
       ・未設定 → 従来どおり相対パス data/<パス>
     sample.json と themes.json は常に相対パス。
     トークンは store.js の別キー(kmc.src)にだけ置く。ここでもエラー文・URLに出さない。
     --------------------------------------------------------------------- */
  var LOCAL_ONLY = { "sample.json": 1, "themes.json": 1 };
  var AUTH_MSG = "トークンが無効か期限切れ。メモ画面で再設定してください";
  K.AUTH_MSG = AUTH_MSG;
  K.srcState = { auth: false };   // 直近の取得で 401/403 だったか
  K.fetchData = function (path) {
    var cfg = K.srcGet && K.srcGet(), remote = !LOCAL_ONLY[path] && cfg && cfg.token && cfg.repo;
    var url, opt = { cache: "no-store" };
    if (remote) {
      url = "https://api.github.com/repos/" + cfg.repo + "/contents/data/" + path;
      opt.headers = { "Authorization": "Bearer " + cfg.token, "Accept": "application/vnd.github.raw+json", "X-GitHub-Api-Version": "2022-11-28" };
    } else url = "data/" + path + "?t=" + Date.now();
    function fail(kind, msg) { var e = new Error(msg); e.kind = kind; return e; }
    return fetch(url, opt).then(function (r) {
      if (r.status === 404) throw fail("none", "未取得（404）");
      if (remote && (r.status === 401 || r.status === 403)) { K.srcState.auth = true; throw fail("auth", AUTH_MSG); }
      if (!r.ok) throw fail("http", "取得できません（HTTP " + r.status + "）");
      if (remote) K.srcState.auth = false;
      return r.json().catch(function () { throw fail("http", "データの形が正しくありません"); });
    }, function () { throw fail("net", "通信できません（オフラインか、電波が弱い状態です）"); });
  };
  function getJson(path) { return K.fetchData(path); }

  K.loadData = function () {
    var D = K.data;
    D.loadErrors = [];
    var tasks = [
      getJson("status.json").then(function (j) { D.status = j; }).catch(function (e) { D.loadErrors.push("取得状況: " + e.message); }),
      getJson("events.json").then(function (j) { D.events = j.events || []; D.eventsAt = j.generated_at; }).catch(function (e) { D.loadErrors.push("IR予定: " + e.message); }),
      getJson("ir_index.json").then(function (j) { D.index = j.items || []; }).catch(function (e) { D.loadErrors.push("IR一覧: " + e.message); }),
      getJson("themes.json").then(function (j) { D.themes = j.themes || []; }).catch(function (e) { D.loadErrors.push("テーマ: " + e.message); }),
      getJson("sample.json").then(function (j) { D.sample = j; }).catch(function () { /* サンプルが無くても動く */ })
    ];
    return Promise.all(tasks);
  };
  /* 接続設定を変えたあと: 読み込み済みのデータを捨てて取り直す */
  K.reloadAll = function () {
    var D = K.data;
    D.status = null; D.events = []; D.index = []; K.fin = {}; K.hist = {}; K.srcState.auth = false;
    return K.loadData().then(function () { K.render(); });
  };

  /* 収集側がつけた資料の分類(cat: 決算短信/業績修正/配当修正/自社株/決算説明資料/その他)。URLで ir_index.json と突き合わせる */
  K.catOf = function (it) {
    if (!it || !it.url) return "";
    if (K._catSrc !== K.data.index) {
      K._catSrc = K.data.index; K._catMap = {};
      K.data.index.forEach(function (x) { if (x.url && x.cat) K._catMap[x.url] = x.cat; });
    }
    return K._catMap[it.url] || "";
  };
  K.hasRealData = function () { return !!(K.data.status && K.data.events.length); };

  var BUCKET_LABEL = { month: "月", season: "季節", fy: "年度・期", year: "年" };

  function irItem(e, sample) {
    var t = e.target;
    var it = {
      id: (sample ? "s:" : "e:") + e.id, refId: e.id, src: "ir", sample: !!sample,
      kind: e.actual && e.kind === "earnings" ? "earnings_actual" : e.kind, actual: !!e.actual, origin: e.origin || "official", code: e.code, name: e.name,
      title: e.summary || e.kind_label, time: e.time_text || null,
      raw: e.target_text, url: e.url, page: e.page, quote: e.quote,
      checked_at: e.checked_at, announced_at: e.announced_at, impact: e.impact_period,
      kindLabel: e.kind_label, review: !!e.needs_review, reason: t && t.reason,
      confirmed: false, date: null, bucket: null, ev: e
    };
    if (t && t.precision === "day" && t.start) {
      it.date = t.start;
      it.confirmed = !!e.confirmed && !t.year_inferred;
      if (t.year_inferred) it.reason = "年は発表日から推定（原文に年なし）";
    } else if (t && t.start) {
      it.bucket = { start: t.start, end: t.end, label: bucketLabel(t) };
    } else if (t && !t.start) {
      it.bucket = { start: null, end: null, label: "時期未確定（" + t.raw + "）" };
    } else if (e.kind === "revision_up" || e.kind === "revision_down") {
      it.date = (e.announced_at || "").slice(0, 10);   // 修正を発表した日
      it.confirmed = true;
      it.isAnnounce = true;
    }
    return it;
  }

  function bucketLabel(t) {
    var s = K.parseYmd(t.start), en = K.parseYmd(t.end);
    var base = t.raw ? "「" + t.raw + "」" : "";
    if (t.precision === "month") return s.getFullYear() + "年" + (s.getMonth() + 1) + "月 " + base;
    if (t.precision === "season") return s.getFullYear() + "年 " + (s.getMonth() + 1) + "〜" + (en.getMonth() + 1) + "月頃 " + base;
    if (t.precision === "range" && en) return t.start + "〜" + t.end + " " + base;
    if (t.precision === "fy") return t.start.slice(0, 7) + "〜" + t.end.slice(0, 7) + " " + base;
    return t.start.slice(0, 4) + "年 " + base;
  }

  K.buildItems = function () {
    var items = [];
    var D = K.data;
    D.events.forEach(function (e) { items.push(irItem(e, false)); });
    if (K.state.settings.showSample && D.sample && D.sample.events) {
      D.sample.events.forEach(function (e) { items.push(irItem(e, true)); });
    }
    var done = K.state.checked;
    items.forEach(function (it) { it.checkedByMe = !!done[it.refId]; });

    K.state.userEvents.forEach(function (u) {
      var it = {
        id: "u:" + u.id, refId: u.id, src: "user", sample: false, kind: u.kind || "other", origin: u.origin || "memo",
        code: u.code || "", name: u.name || "", title: u.title, time: u.time || null, raw: u.rawText || "",
        url: u.url || "", note: u.note, confirmed: !!u.confirmed, review: false, date: null, bucket: null
      };
      if (u.precision === "day" && u.date) it.date = u.date;
      else it.bucket = { start: u.date || null, end: null, label: u.rawText || u.bucketLabel || "時期未定" };
      items.push(it);
    });
    K.state.memos.forEach(function (m) {
      if (!m.reviewDate) return;
      items.push({
        id: "m:" + m.id, refId: m.id, src: "memo", sample: false, kind: "mine", origin: "memo",
        code: m.code, name: m.name,
        title: "調べる: " + (m.name || m.code || "（銘柄なし）") + (m.checks ? " — " + m.checks.split("\n")[0].slice(0, 40) : ""),
        date: m.reviewDate, confirmed: true, review: false, done: m.status !== "open", bucket: null, time: null
      });
    });
    K.items = items;
    return items;
  };

  /* ---- 絞り込み ---- */
  K.filter = { text: "", theme: "", fav: false, kinds: null, origin: "" };
  K.themeCodes = function (themeId) {
    var codes = {};
    K.allThemes().forEach(function (t) {
      if (t.id === themeId) t.stocks.forEach(function (s) { codes[s.code] = 1; });
    });
    return codes;
  };
  K.allThemes = function () {
    var list = [];
    var byId = {};
    (K.data.themes || []).forEach(function (t) {
      var c = { id: t.id, name: t.name, note: t.note || "", stocks: (t.stocks || []).map(function (s) { return Object.assign({}, s); }) };
      byId[c.id] = c; list.push(c);
    });
    if (K.state.settings.showSample && K.data.sample && K.data.sample.themes) {
      K.data.sample.themes.forEach(function (t) {
        var c = byId[t.id];
        if (!c) { c = { id: t.id, name: t.name, note: "", stocks: [] }; byId[t.id] = c; list.push(c); }
        t.stocks.forEach(function (s) { c.stocks.push(Object.assign({ sample: true }, s)); });
      });
    }
    K.state.themeStocks.forEach(function (s) {
      var c = byId[s.theme];
      if (!c) { c = { id: s.theme, name: s.theme, note: "", stocks: [] }; byId[s.theme] = c; list.push(c); }
      c.stocks.push(Object.assign({ mine: true }, s));
    });
    return list;
  };
  K.applyFilter = function (items) {
    var f = K.filter, tcodes = f.theme ? K.themeCodes(f.theme) : null;
    var q = (f.text || "").trim().toLowerCase();
    return items.filter(function (it) {
      if (f.kinds && !f.kinds[it.kind]) return false;
      if (f.origin && it.origin !== f.origin) return false;
      if (q && (it.code + " " + it.name + " " + it.title).toLowerCase().indexOf(q) < 0) return false;
      if (f.fav && !K.isFav(it.code)) return false;
      if (tcodes && !tcodes[it.code]) return false;
      return true;
    });
  };

  /* =====================================================================
     財務データ docs/data/financials/<コード>.json の読み込みと、指標の計算。
     - 無い(404)ときは「財務データ未取得」。推測値では埋めない。
     - 指標はすべて「計算値」。式と使った数字を画面に出す。
     ===================================================================== */
  K.fin = {};   // コード -> { st: "loading"|"ok"|"none"|"err", data, msg, at }
  function toNum(v) {
    if (typeof v === "number") return isFinite(v) ? v : null;
    if (typeof v === "string" && /^\s*-?[\d,]+(\.\d+)?\s*$/.test(v)) return Number(v.replace(/,/g, ""));
    return null;
  }
  K.toNum = toNum;
  K.fmtNum = function (v, d) {
    if (v == null) return "";
    d = d || 0;
    return Number(v).toLocaleString("ja-JP", { minimumFractionDigits: d, maximumFractionDigits: d });
  };
  K.fmtYenBig = function (yen) {
    var a = Math.abs(yen);
    if (a >= 1e12) return K.fmtNum(yen / 1e12, 2) + "兆円";
    if (a >= 1e8) return K.fmtNum(Math.round(yen / 1e8)) + "億円";
    return K.fmtNum(Math.round(yen / 1e4)) + "万円";
  };

  /* 読み込んだJSONを検査して整える。periods は period_end の新しい順。訂正で置き換えられた古い版は除く */
  K.finValidate = function (j, code) {
    if (!j || typeof j !== "object" || !Array.isArray(j.periods)) return { ok: false, msg: "財務データの形が正しくありません" };
    if (j.code && String(j.code).toUpperCase() !== code) return { ok: false, msg: "財務データのコードが一致しません" };
    var ps = j.periods.filter(function (p) { return p && typeof p === "object"; });
    var replaced = {};
    ps.forEach(function (p) { if (p.supersedes) replaced[p.supersedes] = true; });
    ps = ps.filter(function (p) { return !(p.id && replaced[p.id]); });
    ps.sort(function (a, b) {
      var x = a.period_end || "", y = b.period_end || "";
      if (x !== y) return x < y ? 1 : -1;
      return (a.announced_at || "") < (b.announced_at || "") ? 1 : -1;
    });
    return { ok: true, data: Object.assign({}, j, { periods: ps }) };
  };
  /* 取得を開始して、いまの状態を返す。終わったら K.onFinLoaded(code) を呼ぶ。失敗は30秒あけて再試行 */
  K.finGet = function (code) {
    if (!/^[0-9A-Z]{4}$/.test(code || "")) return { st: "none" };
    var c = K.fin[code];
    if (c && (c.st !== "err" || Date.now() - c.at < 30000)) return c;
    c = K.fin[code] = { st: "loading", at: Date.now() };
    K.fetchData("financials/" + code + ".json").then(function (j) {
      var v = K.finValidate(j, code);
      if (v.ok) { c.st = "ok"; c.data = v.data; } else { c.st = "err"; c.msg = v.msg; }
    }).catch(function (e) { if (e.kind === "none") c.st = "none"; else { c.st = "err"; c.msg = e.message; } })
      .then(function () { c.at = Date.now(); if (K.onFinLoaded) K.onFinLoaded(code); });
    return c;
  };

  /* 通期の決算か（四半期の累計ではないか） */
  K.isFullYear = function (p) {
    var t = p.period_type || "";
    if (/四半期|第\s*[1-4１-４]|Q[1-4]|中間/i.test(t)) return false;
    if (/通期|本決算|年度|FY|annual/i.test(t)) return true;
    return !!(p.period_end && p.fiscal_year_end && String(p.period_end).slice(0, 7) === String(p.fiscal_year_end).slice(0, 7));
  };
  function firstWith(P, get) {
    for (var i = 0; i < P.length; i++) { var v = toNum(get(P[i])); if (v != null) return { p: P[i], v: v }; }
    return null;
  }
  function bal(p, k) { return p.balance ? p.balance[k] : null; }

  /* 株価に関係する指標。戻り値: { px, items:[{label,value,tag,formula,note,why}] }
     value が null のものは「未取得」(why に理由)。式には実際に使った数字を入れる。 */
  K.finMetrics = function (code, fin) {
    var P = fin.periods || [], p0 = P[0] || {};
    var vs = K.volStats(code), px = vs.rows.length ? vs.rows[vs.rows.length - 1] : null;
    var noPx = px ? "" : ((K.state.prices[code] || []).length ? "株価は取引時間中の途中データのみ" : "株価未取得");
    var out = [];
    function add(label, o) { o.label = label; out.push(o); }
    function miss(label, why) { add(label, { value: null, why: why }); }
    var c = px ? px.c : null;
    var ye = function (v) { return K.fmtNum(v, v % 1 ? 2 : 0); };

    /* 時価総額 = 終値 × 発行済株式数（自己株式を除く） */
    var sh = firstWith(P, function (p) { return bal(p, "shares_issued"); });
    if (!px) miss("時価総額", noPx);
    else if (!sh) miss("時価総額", "発行済株式数が未取得");
    else {
      var tr = toNum(bal(sh.p, "treasury_shares")), shares = sh.v - (tr != null ? tr : 0);
      add("時価総額", {
        value: K.fmtYenBig(c * shares), tag: "計算値",
        formula: "終値 " + ye(c) + "円 × " + (tr != null ? "発行済株式数（自己株式を除く）" : "発行済株式数（自己株式を含む。自己株式数が未取得）") + " " + K.fmtNum(shares) + "株",
        note: "株式数は " + (sh.p.period_end || "不明") + " 時点"
      });
    }

    /* PER = 終値 ÷ 会社予想EPS（無ければ実績EPS） */
    var eps = null, basis = "", epsLab = "";
    var fe = p0.forecast ? toNum(p0.forecast.eps) : null;
    if (fe != null) { eps = fe; basis = "予想ベース"; epsLab = "会社予想EPS" + (p0.forecast.period ? "（" + p0.forecast.period + "）" : ""); }
    else {
      var ae = firstWith(P.filter(K.isFullYear), function (p) { return p.results ? p.results.eps : null; });
      if (ae) { eps = ae.v; basis = "実績ベース"; epsLab = "通期の実績EPS（" + (ae.p.period_end || "不明") + "）"; }
    }
    if (!px) miss("PER", noPx);
    else if (eps == null) miss("PER", "EPS（1株利益）が未取得");
    else if (eps <= 0) add("PER", { value: null, why: "EPSが0以下のため算出できません（" + epsLab + " " + ye(eps) + "円）" });
    else add("PER", { value: K.fmtNum(c / eps, 1) + "倍", tag: "計算値・" + basis, formula: "終値 " + ye(c) + "円 ÷ " + epsLab + " " + ye(eps) + "円" });

    /* PBR = 終値 ÷ BPS。BPSが無ければ 純資産×1,000,000 ÷ 発行済株式数 の概算 */
    var bps = firstWith(P, function (p) { return bal(p, "bps"); });
    var na = firstWith(P, function (p) { return bal(p, "net_assets"); });
    if (!px) miss("PBR", noPx);
    else if (bps && bps.v > 0) add("PBR", { value: K.fmtNum(c / bps.v, 2) + "倍", tag: "計算値", formula: "終値 " + ye(c) + "円 ÷ 1株純資産(BPS) " + ye(bps.v) + "円", note: "BPSは " + (bps.p.period_end || "不明") + " 時点" });
    else if (na && sh && sh.v > 0 && (na.p.unit || "百万円") === "百万円") {
      var b2 = na.v * 1e6 / sh.v;
      if (b2 > 0) add("PBR", { value: K.fmtNum(c / b2, 2) + "倍", tag: "概算", formula: "終値 " + ye(c) + "円 ÷（純資産 " + K.fmtNum(na.v) + "百万円 × 1,000,000 ÷ 発行済株式数 " + K.fmtNum(sh.v) + "株 = " + K.fmtNum(b2, 1) + "円）", note: "BPS未取得のため概算。純資産に非支配株主持分が含まれる場合や、自己株式を含む株数で割るため、実際の値とずれます" });
      else miss("PBR", "純資産が0以下のため算出できません");
    } else miss("PBR", "BPSも、純資産と発行済株式数の組み合わせも未取得");

    /* ROE = 直近通期の純利益 ÷ 純資産 */
    var roeP = null;
    P.filter(K.isFullYear).some(function (p) {
      var ni = toNum(p.results ? p.results.net_income : null), n2 = toNum(bal(p, "net_assets"));
      if (ni != null && n2 != null) { roeP = { p: p, ni: ni, na: n2 }; return true; }
      return false;
    });
    if (roeP && roeP.na > 0) add("ROE", { value: K.fmtNum(roeP.ni / roeP.na * 100, 1) + "%", tag: "概算", formula: "通期の純利益 " + K.fmtNum(roeP.ni) + (roeP.p.unit || "") + " ÷ 期末の純資産 " + K.fmtNum(roeP.na) + (roeP.p.unit || ""), note: (roeP.p.period_end || "") + " 期。期中の平均ではなく期末の純資産で割った概算です" });
    else miss("ROE", "通期の純利益と純資産がそろっていません");

    /* 配当利回り = 会社予想の年間配当 ÷ 終値 */
    var dps = p0.forecast ? toNum(p0.forecast.dps) : null;
    if (dps == null && p0.dividend) dps = toNum(p0.dividend.annual_forecast);
    if (!px) miss("配当利回り", noPx);
    else if (dps == null) miss("配当利回り", "会社予想の年間配当が未取得");
    else add("配当利回り", { value: K.fmtNum(dps / c * 100, 2) + "%", tag: "計算値", formula: "会社予想の年間配当 " + ye(dps) + "円 ÷ 終値 " + ye(c) + "円" });

    return { px: px, noPx: noPx, items: out, stale: px ? (K.parseYmd(K.today()) - K.parseYmd(px.d)) / 86400000 : null };
  };

  /* 「会社予想との差」: 行ごとに { label, f(会社予想), mid(進捗率 or 前期予想との差), chg(予想の変更) } */
  K.finForecastRows = function (P) {
    var p0 = P[0], res = { rows: [], kind: "", q: null, prev: null };
    if (!p0 || !p0.forecast) return res;
    var full = K.isFullYear(p0);
    var prev = P.slice(1).filter(function (p) { return p.fiscal_year_end && p0.fiscal_year_end && p.fiscal_year_end === p0.fiscal_year_end; })[0] || null;
    var m = /([1-3１-３])/.exec(p0.period_type || ""), q = null;
    if (!full && m && /四半期|Q/i.test(p0.period_type || "")) q = Number(String(m[1]).replace(/[１-３]/, function (z) { return String.fromCharCode(z.charCodeAt(0) - 65248); }));
    if (!full && /中間/.test(p0.period_type || "")) q = 2;
    res.kind = full ? "full" : "cum";
    res.q = q;
    [["sales", "売上高"], ["operating_income", "営業利益"], ["ordinary_income", "経常利益"], ["net_income", "純利益"]].forEach(function (k) {
      var f = toNum(p0.forecast[k[0]]), r = p0.results ? toNum(p0.results[k[0]]) : null, row = { label: k[1], f: f, mid: null, midText: "", chg: null };
      if (!full) {
        if (f != null && r != null) {
          if (f > 0 && r >= 0) row.mid = r / f * 100;
          else row.midText = "算出不可（予想か実績が0以下）";
        }
        var pf = prev && prev.forecast ? toNum(prev.forecast[k[0]]) : null;
        if (f != null && pf != null) row.chg = { prev: pf, now: f, dir: f > pf ? "up" : f < pf ? "down" : "same" };
      } else if (prev && prev.forecast) {
        var pf2 = toNum(prev.forecast[k[0]]);
        if (pf2 != null && r != null && pf2 !== 0) row.mid = { diff: r - pf2, pct: (r - pf2) / Math.abs(pf2) * 100, base: pf2 };
      }
      res.rows.push(row);
    });
    res.prev = prev;
    return res;
  };
  K.hist = {};   // コード -> { st: "loading"|"ok"|"none"|"err", items, at }
  K.histGet = function (code) {
    if (!/^[0-9A-Z]{4}$/.test(code || "")) return { st: "none" };
    var c = K.hist[code];
    if (c && (c.st !== "err" || Date.now() - c.at < 30000)) return c;
    c = K.hist[code] = { st: "loading", at: Date.now(), items: [] };
    K.fetchData("history/" + code + ".json").then(function (j) {
      if (!j || !Array.isArray(j.items)) { c.st = "err"; c.msg = "形が正しくありません"; return; }
      c.items = j.items.filter(function (x) { return x && /^\d{4}-\d{2}-\d{2}/.test(x.pubdate || ""); })
        .sort(function (a, b) { return a.pubdate < b.pubdate ? 1 : -1; });
      c.st = "ok";
    }).catch(function (e) { if (e.kind === "none") c.st = "none"; else { c.st = "err"; c.msg = e.message; } })
      .then(function () { c.at = Date.now(); if (K.onHistLoaded) K.onHistLoaded(code); });
    return c;
  };
  /* 昨年同期の発表日(参考・未確定)。collector/history.py の reference_next と同じ計算:
     訂正を除き、発表日が今日より前で、1年後が今日以降のうち最も近いもの */
  K.refNext = function (items) {
    var today = K.today(), best = null;
    (items || []).forEach(function (h) {
      if (h.correction || !h.pubdate) return;
      var o = K.parseYmd(h.pubdate), s = new Date(o.getFullYear() + 1, o.getMonth(), o.getDate());
      if (s.getMonth() !== o.getMonth()) s = new Date(o.getFullYear() + 1, o.getMonth(), 28);   // 2/29 -> 2/28
      var sy = K.ymd(s), oy = K.ymd(o);
      if (sy < today || oy > today) return;
      if (!best || sy < best.approx) best = { approx: sy, h: h };
    });
    return best;
  };
  K.refNextText = function (r) {
    var a = K.parseYmd(r.approx), o = K.parseYmd(r.h.pubdate), hh = String(r.h.pubdate).slice(11, 13);
    return "約" + (a.getMonth() + 1) + "月" + a.getDate() + "日ごろ" + (hh ? "・" + (+hh) + "時台" : "") +
      "（昨年" + (o.getMonth() + 1) + "月" + o.getDate() + "日" + (hh ? (+hh) + "時" : "") + "の実績から）";
  };
})(window.KMC);
