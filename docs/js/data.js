/* 収集済みデータ(docs/data/*.json)の読み込みと、カレンダー用の「予定」への変換。
   サンプルは必ず sample:true を付け、画面でも「サンプル」と表示する。 */
(function (K) {
  K.data = { status: null, events: [], index: [], themes: [], sample: null, loadErrors: [] };

  function getJson(path) {
    return fetch(path + "?t=" + Date.now(), { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error(path + " " + r.status);
      return r.json();
    });
  }

  K.loadData = function () {
    var D = K.data;
    D.loadErrors = [];
    var tasks = [
      getJson("data/status.json").then(function (j) { D.status = j; }).catch(function (e) { D.loadErrors.push("取得状況: " + e.message); }),
      getJson("data/events.json").then(function (j) { D.events = j.events || []; D.eventsAt = j.generated_at; }).catch(function (e) { D.loadErrors.push("IR予定: " + e.message); }),
      getJson("data/ir_index.json").then(function (j) { D.index = j.items || []; }).catch(function (e) { D.loadErrors.push("IR一覧: " + e.message); }),
      getJson("data/themes.json").then(function (j) { D.themes = j.themes || []; }).catch(function (e) { D.loadErrors.push("テーマ: " + e.message); }),
      getJson("data/sample.json").then(function (j) { D.sample = j; }).catch(function () { /* サンプルが無くても動く */ })
    ];
    return Promise.all(tasks);
  };

  K.hasRealData = function () { return !!(K.data.status && K.data.events.length); };

  var BUCKET_LABEL = { month: "月", season: "季節", fy: "年度・期", year: "年" };

  function irItem(e, sample) {
    var t = e.target;
    var it = {
      id: (sample ? "s:" : "e:") + e.id, refId: e.id, src: "ir", sample: !!sample,
      kind: e.kind, origin: e.origin || "official", code: e.code, name: e.name,
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
})(window.KMC);
