/* 銘柄・テーマ画面: 銘柄一覧／銘柄詳細／テーマ／突発材料 */
(function (K) {
  var E = K.esc;
  K.sUi = K.sUi || { sub: "stocks", code: "" };

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
    var h = '<div class="seg">' + [["stocks", "銘柄"], ["themes", "テーマ"], ["breaking", "突発材料"]].map(function (v) {
      return '<button class="' + (u.sub === v[0] ? "on" : "") + '" data-act="ssub" data-v="' + v[0] + '">' + v[1] + "</button>";
    }).join("") + "</div>";
    if (u.sub === "themes") return h + themes();
    if (u.sub === "breaking") return h + breaking();
    return h + list();
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
    var items = K.buildItems().filter(function (it) { return it.code === code; });
    var irs = items.filter(function (it) { return it.src === "ir"; });
    var h = '<button data-act="sback">← 一覧へ</button> <h2 class="inl">' + E(name || "") + " (" + E(code) + ")</h2> " +
      '<button data-act="fav" data-code="' + E(code) + '">' + (K.isFav(code) ? "★ お気に入り" : "☆ お気に入りに追加") + "</button>";
    var th = K.allThemes().filter(function (t) { return t.stocks.some(function (s) { return s.code === code; }); });
    h += '<div class="muted">テーマ: ' + (th.length ? th.map(function (t) { return E(t.name); }).join("、") : "未登録") + "</div>";

    /* 株価・出来高 */
    h += '<section class="panel"><h3>株価・出来高（引け後の日足）</h3>';
    if (!st.rows.length) {
      h += '<p class="warn">未取得です。無料で自動取得できる出典はまだ接続していません。証券会社などからダウンロードしたCSVを取り込めます。</p>';
    } else {
      var last = st.series[st.series.length - 1], r = last.row;
      h += '<dl class="kv big"><dt>最新データ日</dt><dd>' + E(r.d) + "</dd>" +
        "<dt>終値</dt><dd>" + E(r.c.toLocaleString()) + "円" + (last.prevChange != null ? "（前日比 " + (last.prevChange >= 0 ? "+" : "") + last.prevChange.toFixed(2) + "%）" : "") + "</dd>" +
        "<dt>出来高</dt><dd>" + (r.v == null ? "欠損" : r.v.toLocaleString() + "株") + "</dd>" +
        "<dt>売買代金</dt><dd>" + (last.value == null ? "欠損" : Math.round(last.value / 1e6).toLocaleString() + "百万円" + (last.valueIsEstimate ? "（終値×出来高の概算）" : "")) + "</dd>" +
        "<dt>直前20営業日の平均出来高</dt><dd>" + (last.avg == null ? "算出不可" : Math.round(last.avg).toLocaleString() + "株") + "</dd>" +
        "<dt>平均との比</dt><dd>" + (last.ratio == null ? "比較できません" : last.ratio.toFixed(2) + "倍") + "</dd>" +
        "<dt>比較した期間</dt><dd>" + (last.from ? E(last.from) + " 〜 " + E(last.to) + "（" + last.n + "日分）" : "なし") + "</dd>" +
        "<dt>データの取り込み</dt><dd>" + E(st.meta.importedAt || "不明") + " ／ 出典: " + E(st.meta.source || "不明") + "</dd></dl>";
      if (last.note) h += '<p class="warn">' + E(last.note) + "</p>";
      if (st.excludedIntraday) h += '<p class="warn">本日分は取引時間中（または引け直後）の途中データのため、比較から除いています。</p>';
      if (st.gaps.length) h += '<p class="warn">欠損の可能性: ' + E(st.gaps.slice(0, 5).join(" / ")) + "</p>";
      if (st.missingVol) h += '<p class="warn">出来高が空欄の日が' + st.missingVol + "日あります。</p>";
      var sp = K.state.splits[code] || [];
      if (sp.length && !st.meta.adjusted) h += '<p class="warn">株式分割日 ' + E(sp.join(", ")) + " が登録されています。調整前のデータは分割をまたぐ比較ができません。</p>";
      var irDates = irs.filter(function (i) { return i.announced_at; }).map(function (i) { return { date: i.announced_at.slice(0, 10) }; });
      h += K.chartSvg(st.series, irDates);
      h += '<p class="muted">青線=終値、棒=出来高（橙=20日平均の' + K.surgeThreshold + "倍以上）、紫の点線=IR発表日。発表日が休日の場合は次の営業日に置いています。</p>";
      var surges = st.series.filter(function (o) { return o.ratio != null && o.ratio >= K.surgeThreshold; }).slice(-5).reverse();
      if (surges.length) {
        h += "<h4>出来高が増えた日と、関連しそうなIR</h4>";
        surges.forEach(function (o) {
          var near = irs.filter(function (i) { var a = (i.announced_at || "").slice(0, 10); return a >= K.addDays(o.row.d, -2) && a <= o.row.d; });
          h += '<div class="mline">▲ ' + E(o.row.d) + "：平均の" + o.ratio.toFixed(1) + "倍 → " +
            (near.length ? "直前のIR: " + near.map(function (i) { return E(i.kindLabel + "(" + i.announced_at.slice(0, 10) + ")"); }).join("、")
              : "取得済みの範囲に関連IRは見つかりません（未取得・未処理の可能性もあります）") + "</div>";
        });
        h += '<p class="muted">出来高が多いこと自体は、買い・売りの根拠や特定の株の性質の判定にはなりません。</p>';
      }
    }
    h += '<div class="row wrap"><label class="btnlike">CSVを取り込む<input id="csv-file" type="file" accept=".csv,.txt" hidden></label>' +
      '<label class="chk"><input id="csv-adj" type="checkbox"' + (st.meta.adjusted ? " checked" : "") + "> 取り込むCSVは分割調整済み</label></div>" +
      '<div class="row wrap"><input id="split-date" type="date"><button data-act="addsplit" data-code="' + E(code) + '">株式分割日を登録</button>' +
      ((K.state.splits[code] || []).length ? '<button data-act="clearsplit" data-code="' + E(code) + '">分割日を消す</button>' : "") + "</div>";
    if (st.rows.length) h += '<button data-act="delprices" data-code="' + E(code) + '">この銘柄の株価データを削除</button>';
    h += "</section>";

    /* 決算発表の予定（日付があるものだけ。時刻が無ければ未公表） */
    var er = items.filter(function (i) { return i.kind === "earnings" && i.date && i.date >= K.today(); }).sort(function (a, b) { return a.date < b.date ? -1 : 1; });
    h += '<section class="panel"><h3>決算発表の予定</h3>';
    if (!er.length) h += '<p class="empty">この銘柄の決算発表予定日は、取得済みの資料・入力済みの予定にありません（未確認）。自分で入力する場合は「カレンダー」→「＋予定を追加」。</p>';
    er.forEach(function (i) { h += '<div class="plan">' + K.chip("earnings") + " " + E(K.fmtDay(i.date)) + " ／ 時刻: " + E(K.timeText(i)) + " " + K.originBadge(i.origin) + "</div>"; });
    h += "</section>";

    /* 計画の進捗 */
    var plans = irs.filter(function (i) { return /^(launch|development|production|alliance|delay)$/.test(i.kind); })
      .sort(function (a, b) { return a.announced_at < b.announced_at ? -1 : 1; });
    h += '<section class="panel"><h3>計画の進捗（IRから抽出）</h3>';
    if (!plans.length) h += '<p class="empty">取得済みのIRに、発売・開発・量産・提携などの記載は見つかっていません（未取得分は含みません）。</p>';
    plans.forEach(function (p) {
      var over = p.bucket && p.bucket.end && p.bucket.end < K.today() || (p.date && p.date < K.today());
      h += '<div class="plan">' + K.chip(p.kind) + " " + E((p.announced_at || "").slice(0, 10)) + " 発表 ／ 時期: " + E(p.raw || "記載なし") + " — " + E(p.title) +
        (over ? '<div class="warn">予定時期を過ぎています。完了または変更のIRは、取得済みの範囲では確認できていません（延期・中止とは判定していません）。</div>' : "") + "</div>";
    });
    h += "</section>";

    /* 時系列 */
    var tl = [];
    irs.forEach(function (i) { tl.push({ at: i.announced_at || "", t: "IR", html: K.chip(i.kind) + " " + E(i.title) + (i.raw && i.raw !== "記載なし" ? "（時期: " + E(i.raw) + "）" : "") + (i.sample ? ' <span class="badge b-sample">サンプル</span>' : "") }); });
    K.memoByCode(code).forEach(function (m) {
      tl.push({ at: m.createdAt || "", t: "メモ", html: '<span class="badge o-memo">自分のメモ</span> ' + E((m.reason || "").slice(0, 60)) + (m.reviewDate ? "（再確認日 " + E(m.reviewDate) + "）" : "") + ' <a href="#" data-act="gomemo" data-id="' + E(m.id) + '">開く</a>' });
    });
    items.filter(function (i) { return i.src === "user"; }).forEach(function (i) { tl.push({ at: i.date || "", t: "予定", html: K.chip(i.kind) + " " + K.originBadge(i.origin) + " " + E(i.title) }); });
    tl.sort(function (a, b) { return a.at < b.at ? 1 : -1; });
    h += '<section class="panel"><h3>時系列（新しい順）</h3>' + (tl.length ? tl.map(function (x) { return '<div class="tl"><span class="tld">' + E(x.at.slice(0, 16)) + "</span> " + x.html + "</div>"; }).join("") : '<p class="empty">まだ記録がありません。</p>') + "</section>";

    h += '<section class="panel"><h3>自分のメモ</h3><button data-act="newmemo" data-code="' + E(code) + '">＋ この銘柄のメモを作る</button>' +
      K.memoByCode(code).map(function (m) { return '<div class="mline">' + E((m.reason || "（理由なし）").slice(0, 50)) + ' <a href="#" data-act="gomemo" data-id="' + E(m.id) + '">開く</a></div>'; }).join("") + "</section>";
    return h;
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
      h += '<section class="panel"><h3>' + E(t.name) + "</h3>";
      if (!t.stocks.length) h += '<p class="empty">まだ銘柄が登録されていません（根拠を確認できたものだけ登録してください）。</p>';
      t.stocks.forEach(function (s) {
        var r = REL[s.relation] || REL.unknown;
        h += '<div class="trow"><a href="#" data-act="stock" data-code="' + E(s.code) + '">' + E(s.name || "") + " (" + E(s.code) + ")</a> " +
          '<span class="badge ' + r.cls + '">' + r.label + "</span>" + (s.sample ? ' <span class="badge b-sample">サンプル</span>' : "") +
          '<div class="muted">根拠: ' + E(s.evidence || "記載なし") + " ／ 確認日: " + E(s.confirmed_at || "未確認") +
          (K.safeUrl(s.url) ? ' ／ <a href="' + E(s.url) + '" target="_blank" rel="noopener">出典</a>' : "") + "</div>" +
          (s.mine ? '<button class="mini" data-act="delts" data-id="' + E(s.id) + '">削除</button>' : "") + "</div>";
      });
      h += "</section>";
    });
    h += '<section class="panel"><h3>テーマに銘柄を追加</h3><div class="form">' +
      '<label>テーマ<input id="ts-theme" list="ts-list" placeholder="例: 地震">' +
      '<datalist id="ts-list">' + K.allThemes().map(function (t) { return '<option value="' + E(t.id) + '">' + E(t.name) + "</option>"; }).join("") + "</datalist></label>" +
      '<label>コード<input id="ts-code" size="8"></label><label>会社名<input id="ts-name"></label>' +
      '<label>関係の種類<select id="ts-rel"><option value="business">事業上の関係</option><option value="price">株価が反応しただけ</option><option value="unknown">未分類</option></select></label>' +
      '<label>根拠（何を見てそう判断したか）<textarea id="ts-ev" rows="2"></textarea></label>' +
      '<label>出典URL（https）<input id="ts-url"></label><label>確認日<input id="ts-date" type="date" value="' + K.today() + '"></label>' +
      '<button data-act="addts">追加</button></div></section>';
    return h;
  }

  /* ---------- 突発材料 ---------- */
  function breaking() {
    var h = '<p class="warn">ニュースの自動取得は未接続です。ここは手入力の記録欄で、自動検知は行っていません。</p>';
    h += '<section class="panel"><h3>材料を記録</h3><div class="form"><label>発生日時<input id="b-at" type="datetime-local"></label>' +
      '<label>見出し<input id="b-title"></label><label>関連銘柄（コードをカンマ区切り）<input id="b-codes" placeholder="例: 1234,5678"></label>' +
      '<label>出典・メモ<textarea id="b-note" rows="2"></textarea></label><button data-act="addb">記録する</button></div></section>';
    K.state.breaking.slice().sort(function (a, b) { return a.at < b.at ? 1 : -1; }).forEach(function (b) {
      h += '<section class="panel"><h4>' + E((b.at || "").replace("T", " ")) + " " + E(b.title) + "</h4><div class=\"muted\">" + E(b.note || "") + "</div>" +
        "<div>関連: " + (b.codes || []).map(function (c) { return '<a href="#" data-act="stock" data-code="' + E(c) + '">' + E(c) + "</a>"; }).join("、") + "</div>";
      (b.followups || []).forEach(function (f) { h += '<div class="mline">続報 ' + E(f.at) + ": " + E(f.text) + "</div>"; });
      h += '<div class="row"><input id="bf-' + E(b.id) + '" placeholder="続報を追記"><button data-act="addbf" data-id="' + E(b.id) + '">追記</button><button data-act="delb" data-id="' + E(b.id) + '">削除</button></div></section>';
    });
    return h;
  }
})(window.KMC);
