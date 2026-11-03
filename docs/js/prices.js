/* 株価・出来高の計算とCSV取込。
   - 比較は「引け後の日足」どうしだけ。取引時間中の途中出来高は比較に入れない。
   - 直前20営業日（データにある日）の平均と比べ、足りない・欠けている・分割の影響は表示する。
   - 出来高の多さだけで買い推奨や仕手株の判定はしない。 */
(function (K) {
  var N = 20;

  /* ---- CSV ---- */
  function splitCsv(line) {
    var out = [], cur = "", q = false;
    for (var i = 0; i < line.length; i++) {
      var c = line[i];
      if (q) { if (c === '"') { if (line[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += c; }
      else if (c === '"') q = true;
      else if (c === "," || c === "\t") { out.push(cur); cur = ""; }
      else cur += c;
    }
    out.push(cur);
    return out.map(function (s) { return s.trim(); });
  }
  function num(s) {
    if (s == null) return null;
    var t = String(s).replace(/[,\s円株]/g, "");
    if (t === "" || t === "-" || t === "--") return null;
    var v = Number(t);
    return isFinite(v) ? v : null;
  }
  function normDate(s) {
    var m = /(\d{4})[\/\-.年](\d{1,2})[\/\-.月](\d{1,2})/.exec(s || "");
    return m ? m[1] + "-" + K.pad(+m[2]) + "-" + K.pad(+m[3]) : null;
  }
  var HDR = {
    d: /^(日付|年月日|date)$/i, o: /^(始値|open)$/i, h: /^(高値|high)$/i, l: /^(安値|low)$/i,
    c: /^(終値|close|調整後終値|adj.?close)$/i, v: /^(出来高|volume|売買高)$/i, val: /^(売買代金|turnover|value)$/i
  };
  K.parseCsv = function (text) {
    text = text.replace(/^﻿/, "");
    var lines = text.split(/\r?\n/).filter(function (l) { return l.trim(); });
    if (lines.length < 2) return { ok: false, msg: "行が足りません" };
    var head = splitCsv(lines[0]), idx = {};
    head.forEach(function (h, i) { Object.keys(HDR).forEach(function (k) { if (idx[k] == null && HDR[k].test(h)) idx[k] = i; }); });
    if (idx.d == null || idx.c == null || idx.v == null) {
      return { ok: false, msg: "日付・終値・出来高の列が見つかりません（1行目は見出し行にしてください。例: 日付,始値,高値,安値,終値,出来高）" };
    }
    var rows = [], bad = 0, seen = {};
    for (var i = 1; i < lines.length; i++) {
      var c = splitCsv(lines[i]), d = normDate(c[idx.d]);
      var close = num(c[idx.c]), vol = num(c[idx.v]);
      if (!d || close == null) { bad++; continue; }
      if (seen[d]) { bad++; continue; }   // 同じ日の重複は最初の1件だけ
      seen[d] = 1;
      rows.push({ d: d, o: idx.o != null ? num(c[idx.o]) : null, h: idx.h != null ? num(c[idx.h]) : null, l: idx.l != null ? num(c[idx.l]) : null, c: close, v: vol, val: idx.val != null ? num(c[idx.val]) : null });
    }
    rows.sort(function (a, b) { return a.d < b.d ? -1 : 1; });
    if (!rows.length) return { ok: false, msg: "読める行がありませんでした" };
    return { ok: true, rows: rows, bad: bad };
  };
  /* ファイルを読む。UTF-8で文字化け(�)が出たら Shift_JIS で読み直す */
  K.readCsvFile = function (file) {
    return file.arrayBuffer().then(function (buf) {
      var t = new TextDecoder("utf-8").decode(buf);
      if (t.indexOf("�") >= 0) { try { t = new TextDecoder("shift_jis").decode(buf); } catch (e) { /* そのまま */ } }
      return t;
    });
  };

  /* ---- 出来高の比較 ---- */
  function isIntraday(row) {
    // 当日の行は、引け(15:30)後に十分な余裕(15:40)をみるまで「途中」として扱う
    var now = new Date();
    return row.d === K.ymd(now) && (now.getHours() * 60 + now.getMinutes()) < 15 * 60 + 40;
  }
  K.volStats = function (code) {
    var all = (K.state.prices[code] || []).slice();
    var meta = K.state.priceMeta[code] || {};
    var splits = (K.state.splits[code] || []).slice().sort();
    var res = { rows: [], meta: meta, excludedIntraday: false, gaps: [], missingVol: 0, series: [] };
    if (!all.length) return res;
    var rows = all.filter(function (r) { return !isIntraday(r); });
    res.excludedIntraday = rows.length !== all.length;
    rows.forEach(function (r, i) {
      if (r.v == null) res.missingVol++;
      if (i > 0) {
        var gap = (K.parseYmd(r.d) - K.parseYmd(rows[i - 1].d)) / 86400000;
        if (gap > 5) res.gaps.push(rows[i - 1].d + " → " + r.d + "（" + gap + "日空き）");
      }
    });
    rows.forEach(function (r, i) {
      var prev = rows.slice(Math.max(0, i - N), i).filter(function (x) { return x.v != null; });
      var o = { row: r, prevChange: i > 0 ? (r.c / rows[i - 1].c - 1) * 100 : null, avg: null, ratio: null, n: prev.length, note: "" };
      o.value = r.val != null ? r.val : (r.v != null ? r.c * r.v : null);
      o.valueIsEstimate = r.val == null;
      if (prev.length) {
        o.from = prev[0].d; o.to = prev[prev.length - 1].d;
        o.avg = prev.reduce(function (s, x) { return s + x.v; }, 0) / prev.length;
        if (r.v != null && o.avg > 0) o.ratio = r.v / o.avg;
        var hasSplit = splits.some(function (s) { return s > o.from && s <= r.d; });
        if (prev.length < N) o.note = "比較期間が" + prev.length + "日分しかありません（20日未満）";
        if (hasSplit && !meta.adjusted) { o.note = "比較期間に株式分割があり、調整前なら比較できません"; o.ratio = null; o.splitBlocked = true; }
      }
      res.series.push(o);
    });
    res.rows = rows;
    return res;
  };
  K.surgeThreshold = 2.0;

  /* ---- チャート(SVG): 終値の線 + 出来高の棒 + IR発表日の縦線 ---- */
  K.chartSvg = function (series, irDates) {
    var E = K.esc, S = series.slice(-90);
    if (S.length < 2) return '<p class="empty">チャートを描くには2日分以上のデータが必要です。</p>';
    var W = 640, H = 270, L = 8, R = 8, top = 10, ph = 150, vy = 175, vh = 80;
    var cs = S.map(function (o) { return o.row.c; }), mn = Math.min.apply(null, cs), mx = Math.max.apply(null, cs);
    if (mx === mn) { mx += 1; mn -= 1; }
    var vs = S.map(function (o) { return o.row.v || 0; }), vmax = Math.max.apply(null, vs) || 1;
    var step = (W - L - R) / (S.length - 1), xs = function (i) { return L + i * step; };
    var pts = S.map(function (o, i) { return xs(i).toFixed(1) + "," + (top + ph - (o.row.c - mn) / (mx - mn) * ph).toFixed(1); }).join(" ");
    var bw = Math.max(1, step * 0.7);
    var h = '<svg viewBox="0 0 ' + W + " " + H + '" class="chart" role="img" aria-label="終値と出来高のチャート">';
    S.forEach(function (o, i) {
      var bh = (o.row.v || 0) / vmax * vh, surge = o.ratio != null && o.ratio >= K.surgeThreshold;
      h += '<rect x="' + (xs(i) - bw / 2).toFixed(1) + '" y="' + (vy + vh - bh).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + bh.toFixed(1) + '" fill="' + (surge ? "#c2410c" : "#9aa7b4") + '"><title>' + E(o.row.d) + " 出来高 " + E(o.row.v == null ? "欠損" : o.row.v.toLocaleString()) + (o.ratio ? " (20日平均の" + o.ratio.toFixed(1) + "倍)" : "") + "</title></rect>";
    });
    h += '<polyline points="' + pts + '" fill="none" stroke="#1a56db" stroke-width="2"/>';
    (irDates || []).forEach(function (ir) {
      var i = -1;
      S.forEach(function (o, k) { if (o.row.d >= ir.date && i < 0) i = k; });   // 発表日が休日なら次の営業日に置く
      if (i < 0 || S[i].row.d > K.addDays(ir.date, 5)) return;
      h += '<line x1="' + xs(i).toFixed(1) + '" x2="' + xs(i).toFixed(1) + '" y1="' + top + '" y2="' + (vy + vh) + '" stroke="#7a3fc4" stroke-dasharray="3 3"/>';
      h += '<text x="' + (xs(i) + 2).toFixed(1) + '" y="' + (top + 10) + '" font-size="10" fill="#7a3fc4">IR</text>';
    });
    h += '<text x="' + L + '" y="' + (H - 2) + '" font-size="10" fill="#666">' + E(S[0].row.d) + "</text>";
    h += '<text x="' + (W - R) + '" y="' + (H - 2) + '" font-size="10" fill="#666" text-anchor="end">' + E(S[S.length - 1].row.d) + "</text></svg>";
    return h;
  };
})(window.KMC);
