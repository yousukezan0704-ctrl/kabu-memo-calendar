(function (K) {
  var E = K.esc;
  K.irUi = K.irUi || { limit: 20, reviewOnly: false, showFailed: false };

  /* "2026-11-03T21:01:55+09:00" -> "21:01"（今日でなければ "11/2 21:01"） */
  function hm(v) {
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2})/.exec(v || "");
    if (!m) return "不明";
    return (m[1] + "-" + m[2] + "-" + m[3] === K.today() ? "" : (+m[2]) + "/" + (+m[3]) + " ") + m[4];
  }

  /* 取得状況: 1行の要約＋詳細は折りたたみ。赤い警告(失敗・停止)は常に上に出す */
  function coverage() {
    var s = K.data.status, h = K.statusAlert() + '<section class="panel cov"><h3>取得状況</h3>';
    if (!s) {
      h += '<p class="warn">実データはまだ取得されていません（収集処理が未実行、または data/status.json が読めません）。下の「サンプル」は架空のデータです。</p>';
      if (K.data.loadErrors.length) h += '<p class="muted">' + E(K.data.loadErrors.join(" / ")) + "</p>";
      return h + "</section>";
    }
    var lr = s.last_run || null;
    h += '<p class="sumline">' + E(s.listed) + "件中<b>" + E(s.done) + "</b>件読了・未処理" + E(s.pending) + "・失敗" + E(s.failed) +
      "・最終更新 " + E(hm(s.generated_at)) + (lr ? "・自動取得 <b>" + (lr.ok ? "成功" : "失敗") + "</b>" : "") + "</p>";
    h += s.complete ? '<p class="ok">全件の全文精査まで完了しています。</p>'
      : '<p class="warn">⚠ 全件の全文精査は完了していません（「完了」とは扱いません）。</p>';
    var mine = Object.keys(K.state.checked).filter(function (k) { return K.state.checked[k]; }).length;
    var d = "";
    if (lr) d += '<p class="muted">直近の自動取得: ' + E((lr.at || "不明").replace("T", " ").slice(0, 16)) + "（" + (lr.trigger === "schedule" ? "定時実行" : lr.trigger === "workflow_dispatch" ? "手動実行" : E(lr.trigger || "不明")) + "）／ <b>" + (lr.ok ? "成功" : "失敗") + "</b></p>";
    d += '<dl class="kv big">' +
      "<dt>対象範囲</dt><dd>直近" + E(s.range.days) + "日分の適時開示（一覧取得できた日: " + E((s.range.index_ok_days || []).join(", ") || "なし") + "）</dd>" +
      "<dt>一覧に載った件数</dt><dd>" + E(s.listed) + "件</dd>" +
      "<dt>本文を読んだ（取得済み）</dt><dd>" + E(s.done) + "件</dd>" +
      "<dt>未処理</dt><dd>" + E(s.pending) + "件（次回以降の自動取得で順に処理）</dd>" +
      "<dt>取得失敗</dt><dd>" + E(s.failed) + "件</dd>" +
      "<dt>対象外にした</dt><dd>" + E(s.skipped) + "件（人事・総会など。本文は読んでいない）</dd>" +
      "<dt>あなたが確認済み</dt><dd>" + mine + "件</dd>" +
      "<dt>最終更新</dt><dd>" + E((s.generated_at || "").replace("T", " ").slice(0, 16)) + "</dd>" +
      "<dt>取得元</dt><dd>" + E(s.source) + "</dd>" +
      "<dt>取得元の利用条件</dt><dd>" + E(s.source_terms || "未確認") + "</dd></dl>";
    d += '<p class="muted">抽出はルールによる自動処理です。見落とし・取り違えがあり得るため、必ず元資料で確認してください。</p>';
    if (s.errors && s.errors.length) d += "<details><summary>エラー詳細 (" + s.errors.length + ")</summary><ul>" + s.errors.map(function (x) { return "<li>" + E(x) + "</li>"; }).join("") + "</ul></details>";
    h += K.det("cov-detail", "取得状況の詳しい内容", d, false, "sub");
    return h + "</section>";
  }

  /* IRカード用の追加表示。pre=常に見せる / fold=「根拠を見る」の中 */
  function extra(it) {
    var e = it.ev, pre = "", fold = "";
    if (!e) return { pre: pre, fold: fold };
    if (e.prev != null) {
      pre += '<div class="cmp"><b>' + E(e.item) + "</b>: 前回予想 " + E(e.prev) + " → 今回 " + E(e.new) +
        (e.diff != null ? "（差 " + (e.diff > 0 ? "+" : "") + E(e.diff.toLocaleString()) + "）" : "") +
        (e.verified ? ' <span class="badge b-ok">資料内の差額と一致</span>' : ' <span class="badge b-warn">列の対応は原文で確認</span>') + "</div>";
    } else if (e.values) pre += '<div class="muted">抽出した数値: ' + E(e.item) + " … " + E(e.values.join(" / ")) + "（列の意味は原文で確認）</div>";
    if (e.correction) pre += '<div class="warn">訂正・差し替えの資料から抽出されています</div>';
    if (e.history && e.history.length) {
      fold += "<details><summary>変更履歴 (" + e.history.length + ")</summary>" + e.history.map(function (x) {
        return '<div class="hist">' + E((x.checked_at || "").slice(0, 16)) + " 時点: 対象時期「" + E(x.target_text) + "」 時刻「" + E(x.time_text || "記載なし") + "」 p." + E(x.page) + "</div>";
      }).join("") + "</details>";
    }
    var prev = K.items.filter(function (o) {
      return o.src === "ir" && o.code === it.code && o.kind === it.kind && o.announced_at < it.announced_at && o.refId !== it.refId;
    }).sort(function (a, b) { return a.announced_at < b.announced_at ? 1 : -1; })[0];
    if (prev) fold += '<div class="muted">前回の同種資料(' + E(prev.announced_at.slice(0, 10)) + "): 対象時期「" + E(prev.raw || "記載なし") + "」→ 今回「" + E(it.raw || "記載なし") + "」" + (prev.raw === it.raw ? "（同じ）" : "（違う: 要確認）") + "</div>";
    return { pre: pre, fold: fold };
  }

  K.renderIR = function () {
    var sub = K.irUi.sub || "all";
    if (sub === "earn") return K.statusAlert() + K.irSubnav() + K.earningsPanel();
    if (sub === "cmp") return K.statusAlert() + K.irSubnav() + K.comparePanel();
    var items = K.buildItems().filter(function (it) { return it.src === "ir"; });
    items = K.applyFilter(items);
    if (K.irUi.reviewOnly) items = items.filter(function (it) { return it.review && !it.checkedByMe; });
    items.sort(function (a, b) { return (a.sample ? 1 : 0) - (b.sample ? 1 : 0) || (a.announced_at < b.announced_at ? 1 : -1); });
    var h = K.irSubnav() + coverage() + K.filterBar() + K.kindNotice();
    h += '<label class="chk"><input id="ir-review" type="checkbox"' + (K.irUi.reviewOnly ? " checked" : "") + "> 「要確認」だけ表示</label>";
    h += "<p class=\"muted\">" + items.length + "件が該当します。</p>";
    if (!items.length) h += '<p class="empty">表示できるIR項目がありません。</p>';
    items.slice(0, K.irUi.limit).forEach(function (it) {
      h += K.itemCard(it, extra(it));
    });
    if (items.length > K.irUi.limit) h += '<button data-act="more-ir">さらに表示（残り ' + (items.length - K.irUi.limit) + "件）</button>";
    var failed = K.data.index.filter(function (x) { return x.status === "failed"; });
    if (failed.length) {
      var fb = '<p class="muted">本文を読めていません。元資料を直接開いて確認してください。</p>';
      failed.slice(0, 40).forEach(function (x) {
        fb += '<div class="mline">' + E(x.name) + "(" + E(x.code) + ") " + E(x.title) + " — " + E(x.note || "") + (K.safeUrl(x.url) ? ' <a href="' + E(x.url) + '" target="_blank" rel="noopener">開く</a>' : "") + "</div>";
      });
      h += K.det("failed", "取得に失敗した資料（" + failed.length + "件）", fb, false, "pf");
    }
    return h;
  };
})(window.KMC);

/* ---- 決算発表の予定・予想比較・自動更新の異常表示 ---- */
(function (K) {
  var E = K.esc;

  /* ---- サンプル（架空）: 実データに少ない種類を画面で確認するための見本。日付は「今日」からの相対 ---- */
  function sampleExtras() {
    var t = K.today(), ann = t + " 15:00:00";
    function base(id, kind, label) {
      return { id: id, kind: kind, kind_label: label, code: "0000", name: "サンプル工業(架空)", announced_at: ann, impact_period: "通期",
        checked_at: t + "T09:00:00+09:00", origin: "official", extractor: "sample", confirmed: false, needs_review: false,
        page: 1, url: "", title: "（架空）サンプルのIR", time_text: null, target: null, target_text: "記載なし", quote: "（架空の例です）" };
    }
    function earn(id, name, code, plusDays, time) {
      var d = K.addDays(t, plusDays), e = base(id, "earnings", "決算発表");
      e.name = name; e.code = code; e.summary = "決算発表の予定（架空）";
      e.target = { raw: d, start: d, end: d, precision: "day", needs_review: false, reason: "" };
      e.target_text = d; e.time_text = time; e.confirmed = true;
      e.quote = "決算を" + d + (time ? " " + time + "に" : "に") + "発表する予定です。（架空）";
      return e;
    }
    function item(id, nm, prev, nw, diff, verified) {
      var e = base(id, "forecast_item", "予想数値の変更");
      e.item = nm; e.prev = prev; e.new = nw; e.diff = diff; e.verified = verified;
      e.values = [prev, nw]; e.summary = nm + ": 前回 " + prev + " → 今回 " + nw;
      e.title = "（架空）通期業績予想の修正に関するお知らせ"; e.quote = nm + " " + prev + " " + nw + (diff != null ? " " + diff : "");
      e.page = 2;
      return e;
    }
    return [
      earn("sample-e1", "サンプル工業(架空)", "0000", 3, "15:00"),
      earn("sample-e2", "サンプル商事(架空)", "0001", 7, null),
      earn("sample-e3", "サンプル食品(架空)", "0002", 12, "13:30"),
      item("sample-f1", "売上高", "100,000", "110,000", 10000, true),
      item("sample-f2", "営業利益", "8,000", "7,200", -800, true),
      item("sample-f3", "経常利益", "8,100", "7,500", null, false)
    ];
  }
  var origLoad = K.loadData;
  K.loadData = function () {
    return origLoad.apply(this, arguments).then(function (r) {
      var s = K.data.sample;
      if (s && s.events && !s.events.some(function (e) { return /^sample-/.test(e.id); })) s.events = s.events.concat(sampleExtras());
      return r;
    });
  };

  /* ---- 自動更新の異常表示（失敗・停止・読み込み不可） ---- */
  function stamp(v) { return v ? String(v).replace("T", " ").slice(0, 16) : "不明"; }
  K.statusAlert = function () {
    var s = K.data.status;
    if (!s) {
      return K.data.loadErrors.length ? '<p class="errbox">⚠ 自動取得の状況ファイルを読めませんでした。表示中の情報が古い可能性があります。</p>' : "";
    }
    var lr = s.last_run || null, h = "";
    var ms = s.generated_at ? new Date(s.generated_at).getTime() : NaN, age = (Date.now() - ms) / 86400000;
    if (lr && lr.ok === false) {
      h += '<p class="errbox">⚠ 直近の自動取得は失敗しました（' + E(stamp(lr.at)) + "）。原因: " + E(lr.error || "不明") + "。データは前回成功時のままです。</p>";
    }
    if (isNaN(age)) h += '<p class="errbox">⚠ データの最終更新日時が分かりません。自動更新の状態を確認してください。</p>';
    else if (age > 4) h += '<p class="errbox">⚠ データの最終更新が' + Math.floor(age) + "日前です。自動更新が止まっている可能性があります（GitHubのActionsタブで確認）。</p>";
    return h;
  };

  /* ---- 決算発表の予定 ---- */
  function earningsPanel() {
    var today = K.today();
    var all = K.buildItems().filter(function (it) { return it.kind === "earnings" && it.src !== "memo"; });
    var up = all.filter(function (it) { return it.date && it.date >= today; }).sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
    var undated = all.filter(function (it) { return !it.date; });
    var h = '<section class="panel"><h3>決算発表の予定（今後）</h3>';
    h += '<p class="muted">会社が公表した日付と時刻だけを載せています。時刻が書かれていない場合は「未公表」と表示します（推測はしません）。</p>';
    if (!up.length) {
      h += '<p class="empty">今のところ、日付つきの決算発表予定は見つかっていません。決算発表日は、会社のIR日程ページや、東証の<a href="https://www.jpx.co.jp/listing/event-schedules/financial-announcement/index.html" target="_blank" rel="noopener">決算発表予定日一覧</a>で確認できます。カレンダーの「＋ 予定を追加」で自分で入力もできます。</p>';
    } else {
      h += '<div class="tbl-wrap"><table class="tbl earn"><thead><tr><th>日付</th><th>会社</th><th>時刻</th><th>確かさ</th></tr></thead><tbody>';
      up.forEach(function (it) {
        var days = Math.round((K.parseYmd(it.date) - K.parseYmd(today)) / 86400000);
        var rel = days === 0 ? "今日" : "あと" + days + "日";
        var timeCell = it.time ? E(it.time) : '<span class="badge b-warn">未公表</span>';
        var u = K.safeUrl(it.url);
        h += "<tr><td data-l=\"日付\"><b>" + E(K.fmtDay(it.date)) + '</b><br><small class="muted">' + E(rel) + "</small></td>" +
          '<td data-l="会社">' + (it.code ? '<a href="#" data-act="stock" data-code="' + E(it.code) + '">' + E(it.name || "") + " (" + E(it.code) + ")</a>" : E(it.name || "")) +
          (it.sample ? ' <span class="badge b-sample">サンプル</span>' : "") + "</td>" +
          '<td data-l="時刻">' + timeCell + "</td>" +
          '<td data-l="確かさ">' + (it.confirmed ? '<span class="badge b-ok">日付確定</span>' : '<span class="badge b-warn">未確定</span>') +
          (u ? ' <a href="' + E(u) + '" target="_blank" rel="noopener">元資料</a>' : "") + "</td></tr>";
      });
      h += "</tbody></table></div>";
    }
    if (undated.length) {
      h += "<h4>日付が決まっていない決算関連（" + undated.length + "件）</h4>";
      undated.slice(0, 20).forEach(function (it) {
        var u = K.safeUrl(it.url);
        h += '<div class="mline">' + E(it.name || "") + (it.code ? "(" + E(it.code) + ")" : "") + " — " + E(it.title) + "（原文: " + E(it.raw || "記載なし") + "）" +
          (it.review ? ' <span class="badge b-ng">要確認</span>' : "") + (it.sample ? ' <span class="badge b-sample">サンプル</span>' : "") +
          (u ? ' <a href="' + E(u) + '" target="_blank" rel="noopener">開く</a>' : "") + "</div>";
      });
    }
    return h + "</section>";
  }

  /* ---- 予想の前回→今回 ---- */
  function fmtDiff(d) {
    if (d == null) return '<span class="muted">なし</span>';
    var s = (d > 0 ? "＋" : d < 0 ? "－" : "") + Math.abs(d).toLocaleString();
    return '<span class="' + (d > 0 ? "up" : d < 0 ? "down" : "") + '">' + (d > 0 ? "▲ " : d < 0 ? "▼ " : "") + E(s) + "</span>";
  }
  function comparePanel() {
    var items = K.applyFilter(K.buildItems().filter(function (it) { return it.kind === "forecast_item" || (it.ev && it.ev.prev != null); }));
    var groups = {}, order = [];
    items.forEach(function (it) {
      var key = (it.code || "") + "|" + (it.url || it.title || "") + "|" + (it.sample ? "s" : "r");
      if (!groups[key]) { groups[key] = []; order.push(key); }
      groups[key].push(it);
    });
    order.sort(function (a, b) { return groups[a][0].announced_at < groups[b][0].announced_at ? 1 : -1; });
    var h = '<section class="panel"><h3>業績予想の「前回 → 今回」</h3>';
    h += '<p class="muted">会社が出した予想の修正を、表の形にしました。単位（百万円・円など）は資料によって違うので、原文で確認してください。「原文で確認」が付いた行は、表の列の読み取りに自信がありません。</p>';
    h += K.filterBar();
    if (!order.length) return h + '<p class="empty">表示できる予想の比較はありません。</p></section>';
    h += "<p class=\"muted\">" + order.length + "件の資料があります。</p>";
    order.slice(0, K.irUi.cmpLimit || 20).forEach(function (key) {
      var g = groups[key], f = g[0], u = K.safeUrl(f.url);
      var bad = g.filter(function (x) { return !x.ev.verified; }).length;
      h += '<article class="card cmpcard"><div class="ttl">' +
        (f.code ? '<a href="#" data-act="stock" data-code="' + E(f.code) + '">' + E(f.name || "") + " (" + E(f.code) + ")</a>" : E(f.name || "")) +
        (f.sample ? ' <span class="badge b-sample">サンプル</span>' : "") + "</div>" +
        '<div class="body">' + E(f.title) + '</div><div class="muted">発表: ' + E((f.announced_at || "").slice(0, 16)) + " ／ 該当ページ: " + E(f.page) + "</div>";
      if (bad) h += '<p class="warn">⚠ ' + bad + "行は、前回・今回の列の対応が確認できていません。必ず原文で確認してください。</p>";
      h += '<div class="tbl-wrap"><table class="tbl cmp"><thead><tr><th>項目</th><th>前回予想</th><th>今回予想</th><th>差</th><th>確認</th></tr></thead><tbody>';
      g.forEach(function (it) {
        var e = it.ev, ok = !!e.verified;
        var basis = e.verify_basis ? '<br><small class="muted basis">確認の根拠: ' + E(e.verify_basis) + "</small>" : "";
        var sec = e.section ? '<br><small class="muted">見出し: ' + E(e.section) + "</small>" : "";
        var per = e.impact_period && e.impact_period !== "記載なし" ? '<br><small class="muted">対象期間: ' + E(e.impact_period) + "</small>" : "";
        var un = e.unit ? '<small class="unit">' + E(e.unit) + "</small>" : "";
        var diffCell = e.diff_text ? E(e.diff_text) : fmtDiff(e.diff) + (e.diff != null ? un : "");
        var noteHtml = e.note ? '<div class="note">' + E(e.note) + "</div>" : "";
        h += '<tr class="' + (ok ? "" : "unver") + '"><td data-l="項目"><b>' + E(e.item || "") + "</b>" + per + sec + "</td>" +
          '<td data-l="前回予想" class="num">' + E(e.prev) + un + "</td>" +
          '<td data-l="今回予想" class="num">' + E(e.new) + un + "</td>" +
          '<td data-l="差" class="num">' + diffCell + "</td>" +
          '<td data-l="確認">' + (ok ? '<span class="badge b-ok">' + (e.verify_basis && e.verify_basis.indexOf("差額") < 0 ? "列の見出しで確認" : "差額が一致") + "</span>" + basis + noteHtml :
            '<span class="badge b-ng">原文で確認</span>' + noteHtml + basis + (u ? ' <a href="' + E(u) + '" target="_blank" rel="noopener">原文を開く</a>' : "")) + "</td></tr>";
      });
      h += "</tbody></table></div>";
      if (u) h += '<a class="link" href="' + E(u) + '" target="_blank" rel="noopener">元のIR資料を開く</a>';
      h += "</article>";
    });
    if (order.length > (K.irUi.cmpLimit || 20)) h += '<button data-act="more-cmp">さらに表示（残り ' + (order.length - (K.irUi.cmpLimit || 20)) + "件）</button>";
    return h + "</section>";
  }

  K.kindNotice = function () {
    var risky = Object.keys(K.RISKY_KINDS).map(function (k) { return E(K.KINDS[k].label); }).join("・");
    var b = "<p>上方・下方修正と予想の比較: 比較的正確ですが、原文での確認をおすすめします。</p>" +
      "<p>" + risky + ': <span class="badge b-warn">試験的・誤りが残る可能性。必ず原文で確認</span></p>';
    return K.det("kindnote", "⚠ 種類ごとの注意（自動抽出の精度）", b, false, "sub kindnote");
  };
  K.irSubnav = function () {
    var sub = K.irUi.sub || "all";
    return '<div class="subtabs irsub">' + [["all", "すべて"], ["earn", "決算発表の予定"], ["cmp", "予想の比較"]].map(function (v) {
      return '<button class="' + (sub === v[0] ? "on" : "") + '" data-act="irsub" data-v="' + v[0] + '">' + v[1] + "</button>";
    }).join("") + "</div>";
  };
  K.earningsPanel = earningsPanel;
  K.comparePanel = comparePanel;
})(window.KMC);
