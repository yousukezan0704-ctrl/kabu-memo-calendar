/* 銘柄・テーマ画面: 銘柄一覧／銘柄詳細／テーマ／突発材料 */
(function (K) {
  var E = K.esc;
  K.sUi = K.sUi || { sub: "watch", code: "", wq: "", wsort: "date", wnear: false, wrev: false };

  function knownStocks() {
    var m = {};
    function add(code, name) { if (code) { m[code] = m[code] || { code: code, name: "" }; if (name && !m[code].name) m[code].name = name; } }
    K.data.events.forEach(function (e) { add(e.code, e.name); });
    K.state.memos.forEach(function (x) { add(x.code, x.name); });
    K.state.favorites.forEach(function (c) { add(c); });
    K.state.userEvents.forEach(function (x) { add(x.code, x.name); });
    Object.keys(K.state.prices).forEach(function (c) { add(c); });
    K.allThemes().forEach(function (t) { t.stocks.forEach(function (s) { add(s.code, s.name); }); });
    return Object.keys(m).sort().map(function (k) { return m[k]; });
  }
  K.stockName = function (code) {
    var s = knownStocks().filter(function (x) { return x.code === code; })[0];
    return s ? s.name : "";
  };

  K.renderStocks = function () {
    var u = K.sUi;
    if (u.code) return detail(u.code);
    var h = '<div class="subtabs">' + [["watch", "注目"], ["stocks", "銘柄"], ["themes", "テーマ"], ["breaking", "突発材料"]].map(function (v) {
      return '<button class="' + (u.sub === v[0] ? "on" : "") + '" data-act="ssub" data-v="' + v[0] + '">' + v[1] + "</button>";
    }).join("") + "</div>";
    if (u.sub === "themes") return h + themes();
    if (u.sub === "breaking") return h + breaking();
    if (u.sub === "stocks") return h + list();
    return h + K.renderWatch();
  };

  function list() {
    var q = (K.sUi.q || "").toLowerCase();
    var h = '<div class="filters"><input id="s-q" type="search" placeholder="会社名・コードで検索" value="' + E(K.sUi.q || "") + '">' +
      '<input id="s-code" placeholder="コード(例 7203)" size="8"><button data-act="open-code">この銘柄を開く</button></div>';
    var L = knownStocks().filter(function (s) { return !q || (s.code + s.name).toLowerCase().indexOf(q) >= 0; });
    if (!L.length) h += '<p class="empty">まだ銘柄がありません。コードを入力して開くか、IRが取得されると自動で並びます。</p>';
    L.forEach(function (s) {
      var n = K.data.events.filter(function (e) { return e.code === s.code; }).length;
      h += '<div class="srow"><a href="#" data-act="stock" data-code="' + E(s.code) + '">' + E(s.name || "(名称未登録)") + " (" + E(s.code) + ")</a> " +
        '<span class="muted">IR ' + n + "件 / メモ " + K.memoByCode(s.code).length + "件</span> " +
        '<button class="mini" data-act="fav" data-code="' + E(s.code) + '">' + (K.isFav(s.code) ? "★" : "☆") + "</button></div>";
    });
    return h;
  }

  /* ---------- 銘柄詳細 ---------- */
  function detail(code) {
    var name = K.stockName(code), st = K.volStats(code);
    var fc = K.fin[code];
    if (!name && fc && fc.st === "ok" && fc.data.name) name = fc.data.name;
    var items = K.buildItems().filter(function (it) { return it.code === code; });
    var irs = items.filter(function (it) { return it.src === "ir"; });
    var h = '<button data-act="sback">← 一覧へ</button> <h2 class="inl">' + E(name || "") + " (" + E(code) + ")</h2> " +
      '<button data-act="fav" data-code="' + E(code) + '">' + (K.isFav(code) ? "★ お気に入り" : "☆ お気に入りに追加") + "</button>";
    var th = K.allThemes().filter(function (t) { return t.stocks.some(function (s) { return s.code === code; }); });
    h += '<div class="muted">テーマ: ' + (th.length ? th.map(function (t) { return E(t.name); }).join("、") : "未登録") + "</div>";

    /* 財務・指標・修正（財務データが無い銘柄は「財務データ未取得」） */
    h += finSection(code, items);

    /* 株価・出来高 */
    var ph = "";
    if (!st.rows.length) {
      ph += '<p class="warn">未取得です。無料で自動取得できる出典はまだ接続していません。証券会社などからダウンロードしたCSVを取り込めます。</p>';
    } else {
      var last = st.series[st.series.length - 1], r = last.row;
      ph += '<dl class="kv big"><dt>最新データ日</dt><dd>' + E(r.d) + "</dd>" +
        "<dt>終値</dt><dd>" + E(r.c.toLocaleString()) + "円" + (last.prevChange != null ? "（前日比 " + (last.prevChange >= 0 ? "+" : "") + last.prevChange.toFixed(2) + "%）" : "") + "</dd>" +
        "<dt>出来高</dt><dd>" + (r.v == null ? "欠損" : r.v.toLocaleString() + "株") + "</dd>" +
        "<dt>売買代金</dt><dd>" + (last.value == null ? "欠損" : Math.round(last.value / 1e6).toLocaleString() + "百万円" + (last.valueIsEstimate ? "（終値×出来高の概算）" : "")) + "</dd>" +
        "<dt>直前20営業日の平均出来高</dt><dd>" + (last.avg == null ? "算出不可" : Math.round(last.avg).toLocaleString() + "株") + "</dd>" +
        "<dt>平均との比</dt><dd>" + (last.ratio == null ? "比較できません" : last.ratio.toFixed(2) + "倍") + "</dd>" +
        "<dt>比較した期間</dt><dd>" + (last.from ? E(last.from) + " 〜 " + E(last.to) + "（" + last.n + "日分）" : "なし") + "</dd>" +
        "<dt>データの取り込み</dt><dd>" + E(st.meta.importedAt || "不明") + " ／ 出典: " + E(st.meta.source || "不明") + "</dd></dl>";
      if (last.note) ph += '<p class="warn">' + E(last.note) + "</p>";
      if (st.excludedIntraday) ph += '<p class="warn">本日分は取引時間中（または引け直後）の途中データのため、比較から除いています。</p>';
      if (st.gaps.length) ph += '<p class="warn">欠損の可能性: ' + E(st.gaps.slice(0, 5).join(" / ")) + "</p>";
      if (st.missingVol) ph += '<p class="warn">出来高が空欄の日が' + st.missingVol + "日あります。</p>";
      var sp = K.state.splits[code] || [];
      if (sp.length && !st.meta.adjusted) ph += '<p class="warn">株式分割日 ' + E(sp.join(", ")) + " が登録されています。調整前のデータは分割をまたぐ比較ができません。</p>";
      var irDates = irs.filter(function (i) { return i.announced_at; }).map(function (i) { return { date: i.announced_at.slice(0, 10) }; });
      ph += K.chartSvg(st.series, irDates);
      ph += '<p class="muted">青線=終値、棒=出来高（橙=20日平均の' + K.surgeThreshold + "倍以上）、紫の点線=IR発表日。発表日が休日の場合は次の営業日に置いています。</p>";
      var surges = st.series.filter(function (o) { return o.ratio != null && o.ratio >= K.surgeThreshold; }).slice(-5).reverse();
      if (surges.length) {
        ph += "<h4>出来高が増えた日と、関連しそうなIR</h4>";
        surges.forEach(function (o) {
          var near = irs.filter(function (i) { var a = (i.announced_at || "").slice(0, 10); return a >= K.addDays(o.row.d, -2) && a <= o.row.d; });
          ph += '<div class="mline">▲ ' + E(o.row.d) + "：平均の" + o.ratio.toFixed(1) + "倍 → " +
            (near.length ? "直前のIR: " + near.map(function (i) { return E(i.kindLabel + "(" + i.announced_at.slice(0, 10) + ")"); }).join("、")
              : "取得済みの範囲に関連IRは見つかりません（未取得・未処理の可能性もあります）") + "</div>";
        });
        ph += '<p class="muted">出来高が多いこと自体は、買い・売りの根拠や特定の株の性質の判定にはなりません。</p>';
      }
    }
    var cb = "";
    cb += '<div class="row wrap"><label class="btnlike">CSVを取り込む<input id="csv-file" type="file" accept=".csv,.txt" hidden></label>' +
      '<label class="chk"><input id="csv-adj" type="checkbox"' + (st.meta.adjusted ? " checked" : "") + "> 取り込むCSVは分割調整済み</label></div>" +
      '<div class="row wrap"><input id="split-date" type="date"><button data-act="addsplit" data-code="' + E(code) + '">株式分割日を登録</button>' +
      ((K.state.splits[code] || []).length ? '<button data-act="clearsplit" data-code="' + E(code) + '">分割日を消す</button>' : "") + "</div>";
    if (st.rows.length) cb += '<button data-act="delprices" data-code="' + E(code) + '">この銘柄の株価データを削除</button>';
    ph += K.det("csv:" + code, "株価データの取り込み・株式分割日", cb, false, "sub");
    h += K.det("px:" + code, "株価・出来高（引け後の日足）", ph, true, "pf");

    /* 決算発表の予定（日付があるものだけ。時刻が無ければ未公表） */
    var er = items.filter(function (i) { return i.kind === "earnings" && i.date && i.date >= K.today(); }).sort(function (a, b) { return a.date < b.date ? -1 : 1; });
    var eh = "";
    if (!er.length) eh += '<p class="empty">この銘柄の決算発表予定日は、取得済みの資料・入力済みの予定にありません（未確認）。自分で入力する場合は「カレンダー」→「＋予定を追加」。</p>';
    er.forEach(function (i) { eh += '<div class="plan">' + K.chip("earnings") + " " + E(K.fmtDay(i.date)) + " ／ 時刻: " + E(K.timeText(i)) + " " + K.originBadge(i.origin) + "</div>"; });
    h += K.det("er:" + code, "決算発表の予定 " + er.length + "件", eh, true, "pf");

    /* 計画の進捗 */
    var plans = irs.filter(function (i) { return /^(launch|development|production|alliance|delay)$/.test(i.kind); })
      .sort(function (a, b) { return a.announced_at < b.announced_at ? -1 : 1; });
    var plh = "";
    if (!plans.length) plh += '<p class="empty">取得済みのIRに、発売・開発・量産・提携などの記載は見つかっていません（未取得分は含みません）。</p>';
    plans.forEach(function (p) {
      var over = p.bucket && p.bucket.end && p.bucket.end < K.today() || (p.date && p.date < K.today());
      plh += '<div class="plan">' + K.chip(p.kind) + " " + E((p.announced_at || "").slice(0, 10)) + " 発表 ／ 時期: " + E(p.raw || "記載なし") + " — " + E(p.title) +
        (over ? '<div class="warn">予定時期を過ぎています。完了または変更のIRは、取得済みの範囲では確認できていません（延期・中止とは判定していません）。</div>' : "") + "</div>";
    });
    h += K.det("pl:" + code, "計画の進捗（IRから抽出） " + plans.length + "件", plh, false, "pf");

    /* 時系列 */
    var tl = [];
    irs.forEach(function (i) { tl.push({ at: i.announced_at || "", t: "IR", html: K.chip(i.kind) + " " + E(i.title) + (i.raw && i.raw !== "記載なし" ? "（時期: " + E(i.raw) + "）" : "") + (i.sample ? ' <span class="badge b-sample">サンプル</span>' : "") }); });
    K.memoByCode(code).forEach(function (m) {
      tl.push({ at: m.createdAt || "", t: "メモ", html: '<span class="badge o-memo">自分のメモ</span> ' + E((m.reason || "").slice(0, 60)) + (m.reviewDate ? "（再確認日 " + E(m.reviewDate) + "）" : "") + ' <a href="#" data-act="gomemo" data-id="' + E(m.id) + '">開く</a>' });
    });
    items.filter(function (i) { return i.src === "user"; }).forEach(function (i) { tl.push({ at: i.date || "", t: "予定", html: K.chip(i.kind) + " " + K.originBadge(i.origin) + " " + E(i.title) }); });
    tl.sort(function (a, b) { return a.at < b.at ? 1 : -1; });
    h += K.det("tl:" + code, "時系列（新しい順） " + tl.length + "件", (tl.length ? tl.slice(0, 60).map(function (x) { return '<div class="tl"><span class="tld">' + E(x.at.slice(0, 16)) + "</span> " + x.html + "</div>"; }).join("") : '<p class="empty">まだ記録がありません。</p>'), false, "pf");

    h += K.det("mm:" + code, "自分の投資メモ " + K.memoByCode(code).length + "件", '<button data-act="newmemo" data-code="' + E(code) + '">＋ この銘柄のメモを作る</button>' +
      K.memoByCode(code).map(function (m) {
        var stt = m.status === "open" ? "追跡中" : m.status === "done" ? "確認済み" : "見送り";
        return '<div class="mline"><span class="badge">' + stt + "</span> " + E((m.reason || "（理由なし）").slice(0, 60)) +
          (m.checks ? '<div class="muted">調べること: ' + E(m.checks.split("\n")[0].slice(0, 60)) + "</div>" : "") +
          '<div class="muted">再確認日: ' + E(m.reviewDate || "未設定") + ' <a href="#" data-act="gomemo" data-id="' + E(m.id) + '">開く</a></div></div>';
      }).join(""), true, "pf");
    return h;
  }

  /* ---------- 財務・指標（銘柄詳細） ---------- */
  K.onFinLoaded = function (code) { if (K.ui.tab === "stocks" && K.sUi.code === code) K.render(); };

  var NA = '<span class="muted">未取得</span>';
  function numHtml(v, d) { return v == null ? NA : E(K.fmtNum(v, d != null ? d : (v % 1 ? 2 : 0))); }
  function pctHtml(v, d) {
    if (v == null) return NA;
    var t = K.fmtNum(Math.abs(v), d == null ? 1 : d) + "%";
    return '<span class="' + (v > 0 ? "up" : v < 0 ? "down" : "") + '">' + (v > 0 ? "▲ ＋" : v < 0 ? "▼ －" : "") + E(t) + "</span>";
  }
  function table(cls, heads, rows) {
    return '<div class="tbl-wrap"><table class="tbl ' + cls + '"><thead><tr>' + heads.map(function (x) { return "<th>" + E(x) + "</th>"; }).join("") +
      "</tr></thead><tbody>" + rows.map(function (r) {
        return "<tr>" + r.map(function (c, i) { return '<td data-l="' + E(heads[i]) + '"' + (i ? ' class="num"' : "") + ">" + c + "</td>"; }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }
  var FKEYS = [["sales", "売上高"], ["operating_income", "営業利益"], ["ordinary_income", "経常利益"], ["net_income", "純利益"]];

  function finMetricsHtml(code, fin) {
    var m = K.finMetrics(code, fin), h = "";
    if (m.px) {
      h += '<p class="pxline"><b>株価</b> 終値 ' + E(K.fmtNum(m.px.c, m.px.c % 1 ? 2 : 0)) + '円 <span class="badge">データ日 ' + E(m.px.d) + "</span></p>";
      if (m.stale != null && m.stale > 7) h += '<p class="warn">株価データが' + Math.floor(m.stale) + "日前のものです。古い株価で計算しているため、実際とずれています。</p>";
    } else {
      h += '<p class="warn">' + E(m.noPx) + "です。時価総額・PER・PBR・配当利回りは、株価のCSVを取り込むと計算されます（下の「株価データの取り込み」）。</p>";
    }
    h += '<div class="mets">';
    m.items.forEach(function (it) {
      h += '<div class="met"><div class="mh"><span class="ml">' + E(it.label) + "</span> ";
      if (it.value != null) h += '<span class="mv">' + E(it.value) + '</span> <span class="badge b-calc">' + E(it.tag || "計算値") + "</span>";
      else h += '<span class="mv na">未取得</span>';
      h += "</div>";
      if (it.value != null) h += '<div class="fm">式: ' + E(it.formula || "") + (it.note ? " ／ " + E(it.note) : "") + "</div>";
      else h += '<div class="fm">' + E(it.why || "材料がそろっていません") + "（推測値では埋めません）</div>";
      h += "</div>";
    });
    h += "</div>";
    h += '<p class="muted">上の数字は、財務データと取り込んだ株価からこのアプリが計算した値です（会社・取引所の公表値ではありません）。「概算」は材料が足りず近似した値です。</p>';
    return h;
  }

  function finResultsHtml(fin) {
    var p = fin.periods[0], r = p.results || {}, y = p.yoy_pct || {}, unit = p.unit || "";
    var h = '<p class="muted">' + E((p.period_type || "期区分不明") + "（" + (p.period_end || "期末不明") + "）") + " ／ " + E((p.announced_at || "").slice(0, 10) || "発表日不明") + " 発表 ／ 単位: " + E(unit || "不明") +
      (K.safeUrl(p.url) ? ' ／ <a href="' + E(p.url) + '" target="_blank" rel="noopener">元の資料</a>' : "") + (K.isFullYear(p) ? "" : " ／ 累計") + "</p>";
    var rows = FKEYS.map(function (k) { return [E(k[1]), numHtml(K.toNum(r[k[0]]), 0), pctHtml(K.toNum(y[k[0]]))]; });
    rows.push(["EPS（1株利益）", numHtml(K.toNum(r.eps), 2) + (K.toNum(r.eps) != null ? '<small class="unit">円</small>' : ""), '<span class="muted">―</span>']);
    h += table("fres", ["項目", "実績" + (unit ? "（" + unit + "）" : ""), "前年同期比"], rows);
    return h;
  }

  function finForecastHtml(fin) {
    var P = fin.periods, p0 = P[0], fr = K.finForecastRows(P), unit = p0.unit || "";
    if (!p0.forecast || !fr.rows.length) return '<p class="empty">会社予想が財務データに入っていません（未取得）。</p>';
    var full = fr.kind === "full";
    var h = '<p class="muted">会社予想の対象: ' + E(p0.forecast.period || "不明") + (full ? "（直近の決算が通期のため、これは次の期の予想です）" : "") + "</p>";
    var heads = ["項目", "会社予想" + (unit ? "（" + unit + "）" : ""), full ? "前の予想との差（実績－予想）" : "進捗率（実績÷通期予想）", full ? "—" : "前回予想→今回"];
    var rows = fr.rows.map(function (x) {
      var mid, chg;
      if (full) {
        mid = x.mid ? pctHtml(x.mid.pct) + ' <small class="unit">差 ' + E((x.mid.diff > 0 ? "＋" : x.mid.diff < 0 ? "－" : "") + K.fmtNum(Math.abs(x.mid.diff))) + "</small>" : NA;
        chg = '<span class="muted">―</span>';
      } else {
        mid = x.mid != null ? E(K.fmtNum(x.mid, 1)) + "%" + (fr.q ? '<small class="unit">均等ペースの目安 ' + fr.q * 25 + "%</small>" : "") : (x.midText ? '<span class="muted">' + E(x.midText) + "</span>" : NA);
        if (x.chg) {
          var lab = x.chg.dir === "up" ? '<span class="up">▲ 上方</span>' : x.chg.dir === "down" ? '<span class="down">▼ 下方</span>' : '<span class="muted">変更なし</span>';
          chg = E(K.fmtNum(x.chg.prev)) + " → " + E(K.fmtNum(x.chg.now)) + " " + lab;
        } else chg = '<span class="muted">比較なし</span>';
      }
      return [E(x.label), numHtml(x.f, 0), mid, chg];
    });
    h += table("ffc", heads, rows);
    if (full) h += '<p class="muted">' + (fr.prev ? "比べた予想: " + E(fr.prev.announced_at ? fr.prev.announced_at.slice(0, 10) : "") + " 発表時点の会社予想" : "同じ期の直前の会社予想がデータにないため、差は出せません（未取得）。") + "</p>";
    else {
      h += '<p class="muted">進捗率は、累計の実績が通期予想の何%かを割り算しただけの値です。' + (fr.q ? "均等ペースの目安は期の経過(" + fr.q + "/4)から機械的に出した数字で、季節による偏りは考慮していません。" : "") +
        (fr.prev ? " 前回予想は " + E((fr.prev.announced_at || "").slice(0, 10)) + " 発表の同じ期の予想です。" : " 同じ期の前回予想がデータにないため、上方・下方の判定は出せません（未取得）。") + "</p>";
    }
    return h;
  }

  function finHistoryHtml(fin) {
    var rows = fin.periods.slice(0, 12).map(function (p) {
      var r = p.results || {}, y = p.yoy_pct || {}, u = p.unit || "";
      var lk = K.safeUrl(p.url) ? '<a href="' + E(p.url) + '" target="_blank" rel="noopener">開く</a>' : '<span class="muted">なし</span>';
      return [E((p.announced_at || "").slice(0, 10) || "不明"), E((p.period_type || "") + " " + (p.period_end || "")), numHtml(K.toNum(r.sales), 0), numHtml(K.toNum(r.operating_income), 0), numHtml(K.toNum(r.net_income), 0), pctHtml(K.toNum(y.operating_income)), lk];
    });
    var unit = (fin.periods[0] && fin.periods[0].unit) || "";
    return table("fhist", ["発表日", "期", "売上高", "営業利益", "純利益", "営業利益 前年同期比", "資料"], rows) +
      '<p class="muted">金額の単位: ' + E(unit || "不明") + (fin.periods.length > 12 ? "。新しい12件を表示しています。" : "。") + "</p>";
  }

  /* 業績修正(上方・下方)と、予想の前回→今回。財務データが無くても出す */
  function revisionHtml(items, code) {
    var irs = items.filter(function (i) { return i.src === "ir"; });
    var revs = irs.filter(function (i) { return /^revision/.test(i.kind); }).sort(function (a, b) { return a.announced_at < b.announced_at ? 1 : -1; });
    var fis = irs.filter(function (i) { return i.kind === "forecast_item" && i.ev && i.ev.prev != null; }).sort(function (a, b) { return a.announced_at < b.announced_at ? 1 : -1; });
    var h = "";
    if (!revs.length && !fis.length) return { n: 0, recent: false, html: '<p class="empty">取得済みのIRに、業績修正・予想数値の変更は見つかっていません（未取得分は含みません）。</p>' };
    revs.slice(0, 8).forEach(function (i) {
      h += '<div class="mline">' + K.chip(i.kind) + " " + E((i.announced_at || "").slice(0, 10)) + " " + E((i.title || "").slice(0, 80)) +
        (K.safeUrl(i.url) ? ' <a href="' + E(i.url) + '" target="_blank" rel="noopener">原文</a>' : "") + "</div>";
    });
    fis.slice(0, 10).forEach(function (i) {
      var e = i.ev;
      h += '<div class="mline">' + K.chip("forecast_item") + " " + E((i.announced_at || "").slice(0, 10)) + " <b>" + E(e.item) + "</b>: 前回 " + E(e.prev) + " → 今回 " + E(e.new) + (e.unit ? E(e.unit) : "") +
        (e.verified ? "" : ' <span class="badge b-ng">原文で確認</span>') + "</div>";
    });
    h += '<p class="muted">IR本文からの自動抽出です。数字の列の対応は原文で確認してください。</p>';
    var rc = K.addDays(K.today(), -7);
    return { n: revs.length + fis.length, recent: revs.some(function (i) { return (i.announced_at || "").slice(0, 10) >= rc; }), html: h };
  }

  function finSection(code, items) {
    var f = K.finGet(code), h = "", rv = revisionHtml(items, code);
    if (f.st === "loading") h += K.det("fm:" + code, "財務・指標", '<p class="muted">財務データを読み込み中…</p>', true, "pf");
    else if (f.st === "none") {
      h += K.det("fm:" + code, "財務・指標", '<p class="warn"><b>財務データ未取得</b>です。この銘柄の財務データファイルが、まだ作られていません。売上・利益・PER・PBRなどは、データが入るまで表示しません（推測では埋めません）。</p>', true, "pf");
    } else if (f.st === "err") {
      h += K.det("fm:" + code, "財務・指標", '<p class="errbox">⚠ 財務データを読み込めませんでした（' + E(f.msg || "不明") + "）。しばらくして開き直してください。</p>", true, "pf");
    } else {
      var fin = f.data, p0 = fin.periods[0];
      var meta = '<p class="muted">出典: ' + E(fin.source || "不明") + " ／ データ更新: " + E((fin.updated_at || "不明").replace("T", " ").slice(0, 16)) + "。自動抽出のため、必ず元の資料で確認してください。</p>";
      if (!p0) h += K.det("fm:" + code, "財務・指標", '<p class="warn"><b>財務データ未取得</b>です（決算の記録が空です）。</p>' + meta, true, "pf");
      else {
        h += K.det("fm:" + code, "株価と指標（計算値）", finMetricsHtml(code, fin) + meta, true, "pf");
        h += K.det("fr:" + code, "最新の決算と前年同期比", finResultsHtml(fin), true, "pf");
        h += K.det("ff:" + code, "会社予想との差", finForecastHtml(fin), false, "pf");
        h += K.det("fh:" + code, "過去の決算履歴 " + Math.min(12, fin.periods.length) + "件", finHistoryHtml(fin), false, "pf");
      }
    }
    h += K.det("fv:" + code, "上方・下方修正と予想の変更（IR） " + rv.n + "件", rv.html, rv.recent, "pf");
    return h;
  }

  /* ---------- 注目（お気に入り）の一覧 ---------- */
  /* 重要なIR: 業績修正 > 予想・配当の修正 > 決算短信 */
  K.irImportance = function (it) {
    if (it.src !== "ir") return null;
    var cat = K.catOf(it);
    if (it.kind === "earnings_actual") return { pri: 3, label: "決算短信(実績)" };
    if (it.kind === "revision_up") return { pri: 1, label: "上方修正" };
    if (it.kind === "revision_down") return { pri: 1, label: "下方修正" };
    var t = ((it.ev && it.ev.title) || "") + (it.title || "");
    if (it.kind === "forecast" || cat === "配当修正") return { pri: 2, label: cat === "配当修正" || /配当/.test(t) ? "配当予想の修正" : "業績予想の変更" };
    if (it.kind !== "forecast_item" && (cat === "決算短信" || /決算短信/.test(t))) return { pri: 3, label: "決算短信" };
    return null;
  };
  K.nextEarnings = function (code, items, today) {
    var L = items.filter(function (i) { return i.kind === "earnings" && i.src !== "memo" && i.code === code && i.date && i.date >= today; })
      .sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : (b.time ? 1 : 0) - (a.time ? 1 : 0); });
    return L[0] || null;
  };
  /* 決算発表日の前日終値 → 翌営業日終値。材料が足りなければ理由つきで「株価データなし」 */
  K.earnReaction = function (code, items, today) {
    var cand = [];
    items.forEach(function (i) {
      if (i.code !== code || i.src === "memo") return;
      var imp = K.irImportance(i);
      if (i.src === "ir" && imp && /^決算短信/.test(imp.label)) cand.push((i.announced_at || "").slice(0, 10));
      else if (i.kind === "earnings" && i.date && i.confirmed) cand.push(i.date);
    });
    cand = cand.filter(function (d) { return d && d <= today; }).sort();
    if (!cand.length) return { st: "noday" };
    var day = cand[cand.length - 1], st = K.volStats(code), rows = st.rows;
    if (!rows.length) return { st: "noprice", day: day };
    var prev = null, next = null;
    rows.forEach(function (r) { if (r.d < day) prev = r; else if (r.d > day && !next) next = r; });
    if (!prev) return { st: "gap", day: day, why: "発表日の前日までの株価がありません" };
    if (!next) return { st: "gap", day: day, why: "発表日の翌営業日の株価がまだありません" };
    if (K.addDays(prev.d, 7) < day || K.addDays(day, 7) < next.d) return { st: "gap", day: day, why: "株価データの日付が発表日から離れています" };
    var sp = (K.state.splits[code] || []).filter(function (d) { return d > prev.d && d <= next.d; });
    if (sp.length && !(K.state.priceMeta[code] || {}).adjusted) return { st: "gap", day: day, why: "この間に株式分割があり、調整前の株価では比べられません" };
    return { st: "ok", day: day, prev: prev, next: next, pct: (next.c / prev.c - 1) * 100 };
  };

  function watchRows() {
    var items = K.buildItems(), today = K.today(), from = K.addDays(today, -7);
    var names = {};
    knownStocks().forEach(function (s) { names[s.code] = s.name; });
    items.forEach(function (i) { if (i.code && i.name && !names[i.code]) names[i.code] = i.name; });
    return K.state.favorites.map(function (code) {
      var ne = K.nextEarnings(code, items, today), best = null, n = 0, hasRev = false;
      items.forEach(function (i) {
        if (i.code !== code || i.src !== "ir") return;
        var d = (i.announced_at || "").slice(0, 10);
        if (d < from) return;
        if (/^revision/.test(i.kind)) hasRev = true;
        var imp = K.irImportance(i);
        if (!imp) return;
        n++;
        if (!best || imp.pri < best.imp.pri || (imp.pri === best.imp.pri && i.announced_at > best.it.announced_at)) best = { it: i, imp: imp };
      });
      var days = ne ? Math.round((K.parseYmd(ne.date) - K.parseYmd(today)) / 86400000) : null;
      return { code: code, name: names[code] || "", next: ne, days: days, best: best, more: n - (best ? 1 : 0), hasRev: hasRev, react: K.earnReaction(code, items, today) };
    });
  }

  K.renderWatch = function () {
    var u = K.sUi, q = (u.wq || "").trim().toLowerCase();
    var all = watchRows(), L = all.filter(function (r) {
      if (q && (r.code + " " + r.name).toLowerCase().indexOf(q) < 0) return false;
      if (u.wnear && !(r.days != null && r.days <= 14)) return false;
      if (u.wrev && !r.hasRev) return false;
      return true;
    });
    L.sort(function (a, b) {
      if (u.wsort === "code") return a.code < b.code ? -1 : 1;
      if (a.next && b.next) return a.next.date < b.next.date ? -1 : a.next.date > b.next.date ? 1 : (a.code < b.code ? -1 : 1);
      if (a.next) return -1;
      if (b.next) return 1;
      return a.code < b.code ? -1 : 1;
    });
    var h = '<div class="filters"><input id="w-q" type="search" placeholder="コード・会社名で検索" value="' + E(u.wq || "") + '">' +
      '<select id="w-sort"><option value="date"' + (u.wsort !== "code" ? " selected" : "") + '>並び: 決算が近い順</option><option value="code"' + (u.wsort === "code" ? " selected" : "") + ">並び: コード順</option></select>" +
      '<label class="chk"><input id="w-near" type="checkbox"' + (u.wnear ? " checked" : "") + '> 決算が14日以内</label>' +
      '<label class="chk"><input id="w-rev" type="checkbox"' + (u.wrev ? " checked" : "") + "> 直近7日に業績修正あり</label></div>";
    h += '<div class="row wrap"><input id="w-add" placeholder="コードを追加(例 7203)" size="10" style="flex:1 1 140px"><button data-act="addfav">★ 注目に追加</button></div>';
    if (!all.length) return h + '<p class="empty">注目の銘柄はまだありません。上の欄にコードを入れるか、「銘柄」「カレンダー」の☆から追加できます。</p>';
    var nd = all.filter(function (r) { return r.next; }).length, nr = all.filter(function (r) { return r.hasRev; }).length;
    h += '<p class="muted">注目 ' + all.length + "銘柄 ／ 決算予定あり " + nd + " ／ 直近7日に業績修正 " + nr + (L.length !== all.length ? " ／ 表示 " + L.length + "件" : "") + "</p>";
    if (!L.length) h += '<p class="empty">条件に合う銘柄がありません。</p>';
    L.forEach(function (r) { h += watchCard(r); });
    return h;
  };

  function watchCard(r) {
    var hot = r.best && r.best.imp.pri === 1;
    var cls = hot ? (r.best.it.kind === "revision_up" ? " hot-up" : " hot-down") : "";
    var h = '<article class="card wrow' + cls + '"><div class="l1"><span class="ttl"><a href="#" data-act="stock" data-code="' + E(r.code) + '">' + E(r.name || "(名称未登録)") + " (" + E(r.code) + ")</a></span>" +
      ' <button class="mini" data-act="fav" data-code="' + E(r.code) + '" aria-label="注目から外す">★</button></div>';
    /* 次の決算 */
    h += '<div class="wl"><span class="wk">次の決算</span> ';
    if (r.next) {
      h += "<b>" + E(K.fmtDay(r.next.date)) + "</b> " + E(r.days === 0 ? "今日" : "あと" + r.days + "日") + " ／ " +
        (r.next.time ? "時刻 " + E(r.next.time) : '<span class="badge b-warn">時刻 未公表</span>') + " " +
        (r.next.confirmed ? '<span class="badge b-ok">日付確定</span>' : '<span class="badge b-warn">未確定</span>') + (r.next.sample ? ' <span class="badge b-sample">サンプル</span>' : "");
    } else h += '<span class="badge b-warn">予定未確認</span>';
    h += "</div>";
    /* 最新の重要IR */
    h += '<div class="wl"><span class="wk">重要IR（7日）</span> ';
    if (r.best) {
      var i = r.best.it, d = (i.announced_at || "").slice(0, 10);
      h += (hot ? '<b class="hotl">' : "<span>") + K.chip(i.kind) + " " + E(r.best.imp.label) + " " + E(K.fmtDay(d)) + (hot ? "</b>" : "</span>") +
        (K.safeUrl(i.url) ? ' <a href="' + E(i.url) + '" target="_blank" rel="noopener">原文</a>' : "") + (r.more > 0 ? ' <span class="muted">ほか' + r.more + "件</span>" : "");
    } else h += '<span class="muted">直近7日の重要IRなし</span>';
    h += "</div>";
    /* 決算前後の株価 */
    var x = r.react;
    h += '<div class="wl"><span class="wk">決算前後の株価</span> ';
    if (x.st === "ok") {
      h += E(K.fmtDay(x.day)) + "発表: 前日終値 " + E(K.fmtNum(x.prev.c, x.prev.c % 1 ? 2 : 0)) + "円 → 翌営業日終値 " + E(K.fmtNum(x.next.c, x.next.c % 1 ? 2 : 0)) + "円 " + pctHtml(x.pct, 1) +
        ' <span class="muted">(' + E(x.prev.d.slice(5)) + "→" + E(x.next.d.slice(5)) + ")</span>";
    } else if (x.st === "noday") h += '<span class="muted">株価データなし（直近の決算発表日が不明）</span>';
    else if (x.st === "noprice") h += '<span class="muted">株価データなし（' + E(K.fmtDay(x.day)) + "発表。株価CSVが未取り込み）</span>";
    else h += '<span class="muted">株価データなし（' + E(x.why) + "）</span>";
    return h + "</div></article>";
  }

  /* ---------- テーマ ---------- */
  var REL = {
    business: { label: "事業上の関係", cls: "b-ok" },
    price: { label: "株価が反応しただけ", cls: "b-warn" },
    unknown: { label: "未分類", cls: "" }
  };
  function themes() {
    var h = '<p class="muted">「事業上の関係」(会社の資料などで確認できる関わり)と「株価が反応しただけ」は別物として記録します。関連があることと、利益が得られることは同じではありません。</p>';
    K.allThemes().forEach(function (t) {
      var th2 = "";
      if (!t.stocks.length) th2 += '<p class="empty">まだ銘柄が登録されていません（根拠を確認できたものだけ登録してください）。</p>';
      t.stocks.forEach(function (s) {
        var r = REL[s.relation] || REL.unknown;
        th2 += '<div class="trow"><a href="#" data-act="stock" data-code="' + E(s.code) + '">' + E(s.name || "") + " (" + E(s.code) + ")</a> " +
          '<span class="badge ' + r.cls + '">' + r.label + "</span>" + (s.sample ? ' <span class="badge b-sample">サンプル</span>' : "") +
          '<div class="muted">根拠: ' + E(s.evidence || "記載なし") + " ／ 確認日: " + E(s.confirmed_at || "未確認") +
          (K.safeUrl(s.url) ? ' ／ <a href="' + E(s.url) + '" target="_blank" rel="noopener">出典</a>' : "") + "</div>" +
          (s.mine ? '<button class="mini" data-act="delts" data-id="' + E(s.id) + '">削除</button>' : "") + "</div>";
      });
      h += K.det("th:" + t.id, E(t.name) + " " + t.stocks.length + "銘柄", th2, false, "pf");
    });
    h += K.det("th-add", "テーマに銘柄を追加", '<div class="form">' +
      '<label>テーマ<input id="ts-theme" list="ts-list" placeholder="例: 地震">' +
      '<datalist id="ts-list">' + K.allThemes().map(function (t) { return '<option value="' + E(t.id) + '">' + E(t.name) + "</option>"; }).join("") + "</datalist></label>" +
      '<label>コード<input id="ts-code" size="8"></label><label>会社名<input id="ts-name"></label>' +
      '<label>関係の種類<select id="ts-rel"><option value="business">事業上の関係</option><option value="price">株価が反応しただけ</option><option value="unknown">未分類</option></select></label>' +
      '<label>根拠（何を見てそう判断したか）<textarea id="ts-ev" rows="2"></textarea></label>' +
      '<label>出典URL（https）<input id="ts-url"></label><label>確認日<input id="ts-date" type="date" value="' + K.today() + '"></label>' +
      '<button data-act="addts">追加</button></div>', false, "pf");
    return h;
  }

  /* ---------- 突発材料 ---------- */
  function breaking() {
    var h = '<p class="warn">ニュースの自動取得は未接続です。ここは手入力の記録欄で、自動検知は行っていません。</p>';
    h += K.det("b-add", "材料を記録", '<div class="form"><label>発生日時<input id="b-at" type="datetime-local"></label>' +
      '<label>見出し<input id="b-title"></label><label>関連銘柄（コードをカンマ区切り）<input id="b-codes" placeholder="例: 1234,5678"></label>' +
      '<label>出典・メモ<textarea id="b-note" rows="2"></textarea></label><button data-act="addb">記録する</button></div>', false, "pf");
    K.state.breaking.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; }).forEach(function (b) {
      h += '<section class="panel"><h4>' + E((b.at || "").replace("T", " ")) + " " + E(b.title) + "</h4><div class=\"muted\">" + E(b.note || "") + "</div>" +
        "<div>関連: " + (b.codes || []).map(function (c) { return '<a href="#" data-act="stock" data-code="' + E(c) + '">' + E(c) + "</a>"; }).join("、") + "</div>";
      (b.followups || []).forEach(function (f) { h += '<div class="mline">続報 ' + E(f.at) + ": " + E(f.text) + "</div>"; });
      h += '<div class="row"><input id="bf-' + E(b.id) + '" placeholder="続報を追記"><button data-act="addbf" data-id="' + E(b.id) + '">追記</button><button data-act="delb" data-id="' + E(b.id) + '">削除</button></div></section>';
    });
    return h;
  }
})(window.KMC);
