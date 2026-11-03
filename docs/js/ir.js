/* 重要IR画面: 取得状況（どこまで読めたか）と、抽出した項目の一覧 */
(function (K) {
  var E = K.esc;
  K.irUi = K.irUi || { limit: 60, reviewOnly: false, showFailed: false };

  function coverage() {
    var s = K.data.status, h = '<section class="panel cov"><h3>取得状況</h3>';
    if (!s) {
      h += '<p class="warn">実データはまだ取得されていません（収集処理が未実行、または data/status.json が読めません）。下の「サンプル」は架空のデータです。</p>';
      if (K.data.loadErrors.length) h += '<p class="muted">' + E(K.data.loadErrors.join(" / ")) + "</p>";
      return h + "</section>";
    }
    var mine = Object.keys(K.state.checked).filter(function (k) { return K.state.checked[k]; }).length;
    h += s.complete
      ? '<p class="ok">対象期間の一覧をすべて取得し、全文精査も完了しています。</p>'
      : '<p class="warn">⚠ 全件の全文精査は完了していません。未処理・失敗がある間は「完了」とは扱いません。</p>';
    h += '<dl class="kv big">' +
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
    h += '<p class="muted">抽出はルールによる自動処理です。見落とし・取り違えがあり得るため、必ず元資料で確認してください。</p>';
    if (s.errors && s.errors.length) h += "<details><summary>エラー詳細 (" + s.errors.length + ")</summary><ul>" + s.errors.map(function (x) { return "<li>" + E(x) + "</li>"; }).join("") + "</ul></details>";
    return h + "</section>";
  }

  function extra(it) {
    var e = it.ev, h = "";
    if (!e) return h;
    if (e.values) h += '<div class="muted">抽出した数値: ' + E(e.item) + " … " + E(e.values.join(" / ")) + "（列の意味は原文で確認）</div>";
    if (e.correction) h += '<div class="warn">訂正・差し替えの資料から抽出されています</div>';
    if (e.history && e.history.length) {
      h += "<details><summary>変更履歴 (" + e.history.length + ")</summary>" + e.history.map(function (x) {
        return '<div class="hist">' + E((x.checked_at || "").slice(0, 16)) + " 時点: 対象時期「" + E(x.target_text) + "」 時刻「" + E(x.time_text || "記載なし") + "」 p." + E(x.page) + "</div>";
      }).join("") + "</details>";
    }
    var prev = K.items.filter(function (o) {
      return o.src === "ir" && o.code === it.code && o.kind === it.kind && o.announced_at < it.announced_at && o.refId !== it.refId;
    }).sort(function (a, b) { return a.announced_at < b.announced_at ? 1 : -1; })[0];
    if (prev) h += '<div class="muted">前回の同種資料(' + E(prev.announced_at.slice(0, 10)) + "): 対象時期「" + E(prev.raw || "記載なし") + "」→ 今回「" + E(it.raw || "記載なし") + "」" + (prev.raw === it.raw ? "（同じ）" : "（違う: 要確認）") + "</div>";
    return h;
  }

  K.renderIR = function () {
    var items = K.buildItems().filter(function (it) { return it.src === "ir"; });
    items = K.applyFilter(items);
    if (K.irUi.reviewOnly) items = items.filter(function (it) { return it.review && !it.checkedByMe; });
    items.sort(function (a, b) { return a.announced_at < b.announced_at ? 1 : -1; });
    var h = coverage() + K.filterBar();
    h += '<label class="chk"><input id="ir-review" type="checkbox"' + (K.irUi.reviewOnly ? " checked" : "") + "> 「要確認」だけ表示</label>";
    h += "<p class=\"muted\">" + items.length + "件が該当します。</p>";
    if (!items.length) h += '<p class="empty">表示できるIR項目がありません。</p>';
    items.slice(0, K.irUi.limit).forEach(function (it) {
      var card = K.itemCard(it).replace(/<\/article>$/, extra(it) + "</article>");
      h += card;
    });
    if (items.length > K.irUi.limit) h += '<button data-act="more-ir">さらに表示（残り ' + (items.length - K.irUi.limit) + "件）</button>";
    var failed = K.data.index.filter(function (x) { return x.status === "failed"; });
    if (failed.length) {
      h += '<section class="panel"><h3>取得に失敗した資料（' + failed.length + "件）</h3><p class=\"muted\">本文を読めていません。元資料を直接開いて確認してください。</p>";
      failed.slice(0, 40).forEach(function (x) {
        h += '<div class="mline">' + E(x.name) + "(" + E(x.code) + ") " + E(x.title) + " — " + E(x.note || "") + (K.safeUrl(x.url) ? ' <a href="' + E(x.url) + '" target="_blank" rel="noopener">開く</a>' : "") + "</div>";
      });
      h += "</section>";
    }
    return h;
  };
})(window.KMC);
