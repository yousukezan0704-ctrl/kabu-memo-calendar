/* カレンダー画面（月・週・一覧）と、予定カードの共通部品 */
(function (K) {
  var E = K.esc;
  K.ui = K.ui || { tab: "cal", view: "month", cursor: K.today().slice(0, 7) + "-01", selected: K.today() };

  /* ---------- 共通: 小さな表示部品 ---------- */
  K.chip = function (kind) {
    var k = K.kindOf(kind);
    return '<span class="chip" style="--c:' + k.color + '">' + E(k.label) + "</span>";
  };
  K.originBadge = function (o) {
    var x = K.ORIGIN[o] || K.ORIGIN.official;
    return '<span class="badge ' + x.cls + '">' + E(x.label) + "</span>";
  };
  K.certainty = function (it) {
    if (it.src === "memo") return "";
    if (it.isAnnounce) return '<span class="badge b-ok">発表日</span>';
    if (it.date) {
      return it.confirmed ? '<span class="badge b-ok">日付確定</span>'
        : '<span class="badge b-warn">未確定</span>' + (it.review ? ' <span class="badge b-ng">要確認</span>' : "");
    }
    return '<span class="badge b-warn">時期のみ</span>' + (it.review ? ' <span class="badge b-ng">要確認</span>' : "");
  };

  /* 予定1件のカード。IRの根拠(原文・ページ・URL・最終確認日時)をここで見せる */
  K.itemCard = function (it, opt) {
    opt = opt || {};
    var fav = it.code && K.isFav(it.code);
    var h = '<article class="card' + (it.confirmed ? "" : " unconf") + (it.done ? " isdone" : "") + '" style="--c:' + K.kindOf(it.kind).color + '">';
    h += '<div class="row wrap">' + K.chip(it.kind) + " " + K.originBadge(it.origin) + " " + K.certainty(it);
    if (it.sample) h += ' <span class="badge b-sample">サンプル</span>';
    if (it.src === "ir" && K.RISKY_KINDS[it.kind]) h += ' <span class="badge b-warn">自動抽出・要確認</span>';
    if (it.checkedByMe) h += ' <span class="badge b-ok">確認済み</span>';
    h += "</div>";
    h += '<div class="ttl">' + (it.code ? '<a href="#" data-act="stock" data-code="' + E(it.code) + '">' + E(it.name || "") + " (" + E(it.code) + ")</a>" : E(it.name || "")) + "</div>";
    h += '<div class="body">' + E(it.title) + "</div>";
    if (it.src === "ir") {
      h += '<dl class="kv">';
      h += "<dt>発表</dt><dd>" + E((it.announced_at || "").slice(0, 16)) + "</dd>";
      h += "<dt>対象時期</dt><dd>" + E(it.raw || "記載なし") + (it.date ? " → " + E(K.fmtDay(it.date)) : (it.bucket && it.bucket.start ? " → " + E(it.bucket.label) : "")) + "</dd>";
      h += "<dt>時刻</dt><dd>" + E(K.timeText(it)) + "</dd>";
      if (/^(revision|forecast|fx)/.test(it.kind)) h += "<dt>業績影響時期</dt><dd>" + E(it.impact || "記載なし") + "</dd>";
      h += "</dl>";
      if (it.reason) h += '<div class="warn">確認理由: ' + E(it.reason) + "</div>";
      h += '<blockquote>「' + E(it.quote) + "」<br><small>該当ページ: " + E(it.page) + " ／ 最終確認: " + E((it.checked_at || "").replace("T", " ").slice(0, 16)) + "</small></blockquote>";
      var u = K.safeUrl(it.url);
      if (u) h += '<a class="link" href="' + E(u) + '" target="_blank" rel="noopener">元のIR資料を開く</a>';
    } else if (it.note) {
      h += '<div class="muted">' + E(it.note) + "</div>";
    }
    if (it.src !== "ir" && (it.time || it.kind === "earnings")) h += '<div class="muted">時刻: ' + E(K.timeText(it)) + "</div>";
    if (!opt.noActions) {
      h += '<div class="row wrap acts">';
      if (it.src === "ir") {
        h += '<button data-act="chk" data-id="' + E(it.refId) + '">' + (it.checkedByMe ? "確認済みを外す" : "✓ 確認した") + "</button>";
        h += '<button data-act="tomemo" data-id="' + E(it.id) + '">メモにして再確認日をつける</button>';
      }
      if (it.src === "memo") h += '<button data-act="gomemo" data-id="' + E(it.refId) + '">メモを開く</button>';
      if (it.src === "user") h += '<button data-act="deluser" data-id="' + E(it.refId) + '">この予定を削除</button>';
      if (it.code) h += '<button data-act="fav" data-code="' + E(it.code) + '">' + (fav ? "★ お気に入り解除" : "☆ お気に入り") + "</button>";
      h += "</div>";
    }
    return h + "</article>";
  };

  /* 会社が公表した時刻だけを出す。決算発表で時刻が見つからないときは「未公表」 */
  K.timeText = function (it) {
    if (it.time) return "会社公表 " + it.time;
    return it.kind === "earnings" ? "未公表（会社の公表資料に時刻の記載なし）" : "記載なし";
  };

  /* ---------- 絞り込み欄 ---------- */
  K.filterBar = function () {
    var f = K.filter;
    var themes = K.allThemes();
    var h = '<div class="filters">';
    h += '<input id="f-text" type="search" placeholder="会社名・コードで絞り込み" value="' + E(f.text) + '">';
    h += '<select id="f-theme"><option value="">テーマ: すべて</option>' + themes.map(function (t) {
      return '<option value="' + E(t.id) + '"' + (f.theme === t.id ? " selected" : "") + ">" + E(t.name) + "</option>";
    }).join("") + "</select>";
    h += '<select id="f-origin"><option value="">出どころ: すべて</option>' + Object.keys(K.ORIGIN).map(function (o) {
      return '<option value="' + o + '"' + (f.origin === o ? " selected" : "") + ">" + E(K.ORIGIN[o].label) + "</option>";
    }).join("") + "</select>";
    h += '<label class="chk"><input id="f-fav" type="checkbox"' + (f.fav ? " checked" : "") + "> ★お気に入りのみ</label>";
    h += "</div>";
    h += '<div class="kindrow">' + Object.keys(K.KINDS).filter(function (k) { return k !== "forecast_item"; }).map(function (k) {
      var on = !f.kinds || f.kinds[k];
      return '<button class="kbtn' + (on ? " on" : "") + '" data-act="kind" data-kind="' + k + '" style="--c:' + K.KINDS[k].color + '">' + E(K.KINDS[k].label) + "</button>";
    }).join("") + "</div>";
    return h;
  };

  /* ---------- 月表示 ---------- */
  function byDate(items) {
    var m = {};
    items.forEach(function (it) { if (it.date) (m[it.date] = m[it.date] || []).push(it); });
    return m;
  }
  function monthView(items) {
    var cur = K.parseYmd(K.ui.cursor);
    var y = cur.getFullYear(), mo = cur.getMonth();
    var first = new Date(y, mo, 1), startDow = first.getDay();
    var days = new Date(y, mo + 1, 0).getDate();
    var map = byDate(items), t = K.today();
    var h = '<div class="mhead"><button data-act="prev">◀ 前月</button><strong>' + y + "年" + (mo + 1) + '月</strong><button data-act="next">次月 ▶</button><button data-act="goto-today">今日</button></div>';
    h += '<div class="grid">' + K.WD.map(function (w, i) { return '<div class="dow' + (i === 0 ? " sun" : i === 6 ? " sat" : "") + '">' + w + "</div>"; }).join("");
    for (var i = 0; i < startDow; i++) h += '<div class="cell empty"></div>';
    for (var d = 1; d <= days; d++) {
      var ds = y + "-" + K.pad(mo + 1) + "-" + K.pad(d), list = map[ds] || [];
      h += '<div class="cell' + (ds === t ? " today" : "") + (ds === K.ui.selected ? " sel" : "") + '" data-act="pick" data-date="' + ds + '"><div class="dn">' + d + "</div>";
      list.slice(0, 3).forEach(function (it) {
        h += '<div class="mini' + (it.confirmed ? "" : " unconf") + '" style="--c:' + K.kindOf(it.kind).color + '"><span class="ml">' + E(K.kindOf(it.kind).label) + "</span></div>";
      });
      if (list.length > 3) h += '<div class="more">+' + (list.length - 3) + "</div>";
      h += "</div>";
    }
    return h + "</div>";
  }

  /* ---------- 週表示 ---------- */
  function weekView(items) {
    var sel = K.parseYmd(K.ui.selected);
    var start = K.addDays(K.ui.selected, -sel.getDay()), map = byDate(items), t = K.today();
    var h = '<div class="mhead"><button data-act="wprev">◀ 前週</button><strong>' + E(K.fmtDay(start)) + "〜</strong><button data-act=\"wnext\">次週 ▶</button><button data-act=\"goto-today\">今日</button></div>";
    for (var i = 0; i < 7; i++) {
      var ds = K.addDays(start, i), list = map[ds] || [];
      h += '<section class="wday' + (ds === t ? " today" : "") + '"><h4>' + E(K.fmtDay(ds)) + (list.length ? "" : ' <span class="muted">予定なし</span>') + "</h4>";
      list.forEach(function (it) { h += K.itemCard(it); });
      h += "</section>";
    }
    return h;
  }

  /* ---------- 一覧（日付順） ---------- */
  function listView(items) {
    var from = K.addDays(K.today(), -7), to = K.addDays(K.today(), 90);
    var list = items.filter(function (it) { return it.date && it.date >= from && it.date <= to; })
      .sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
    var h = '<p class="muted">今日の7日前から90日先までを日付順に表示しています。</p>';
    if (!list.length) return h + '<p class="empty">この期間に表示できる予定はありません。</p>';
    var last = "";
    list.forEach(function (it) {
      if (it.date !== last) { h += '<h4 class="dh' + (it.date === K.today() ? " today" : "") + '">' + E(K.fmtDay(it.date)) + "</h4>"; last = it.date; }
      h += K.itemCard(it);
    });
    return h;
  }

  /* ---------- 時期別の予定（日付が決まっていないもの） ---------- */
  function bucketPanel(items) {
    var list = items.filter(function (it) { return !it.date && it.bucket; });
    var h = '<section class="panel"><h3>時期別の予定（日付は未確定）</h3>';
    if (!list.length) return h + '<p class="empty">「春」「年度内」などの時期だけが書かれた予定はありません。</p></section>';
    list.sort(function (a, b) { return (a.bucket.start || "9999") < (b.bucket.start || "9999") ? -1 : 1; });
    h += '<p class="muted">会社が日付まで決めていない予定です。原文のまま残し、解釈が曖昧なものは「要確認」と表示します。</p>';
    list.forEach(function (it) { h += '<div class="bk"><div class="bkl">' + E(it.bucket.label) + "</div>" + K.itemCard(it) + "</div>"; });
    return h + "</section>";
  }

  K.renderCal = function () {
    var all = K.applyFilter(K.buildItems());
    var h = (K.statusAlert ? K.statusAlert() : "") + (K.homeBanner ? K.homeBanner() : "");
    h += K.filterBar();
    h += '<div class="seg">' + [["month", "月"], ["week", "週"], ["list", "一覧"]].map(function (v) {
      return '<button class="' + (K.ui.view === v[0] ? "on" : "") + '" data-act="view" data-v="' + v[0] + '">' + v[1] + "</button>";
    }).join("") + '<button data-act="addevent">＋ 予定を追加</button></div>';
    if (K.ui.view === "month") h += monthView(all);
    else if (K.ui.view === "week") h += weekView(all);
    else h += listView(all);
    if (K.ui.view !== "week" && K.ui.view !== "list") {
      var sel = byDate(all)[K.ui.selected] || [];
      h += '<section class="panel"><h3>' + E(K.fmtDay(K.ui.selected)) + " の予定とメモ</h3>";
      h += sel.length ? sel.map(function (it) { return K.itemCard(it); }).join("") : '<p class="empty">この日の予定はありません。</p>';
      var ms = K.state.memos.filter(function (m) { return (m.createdAt || "").slice(0, 10) === K.ui.selected; });
      if (ms.length) h += "<h4>この日に作ったメモ</h4>" + ms.map(function (m) { return '<div class="mline">' + E(m.name || m.code || "メモ") + ' <a href="#" data-act="gomemo" data-id="' + E(m.id) + '">開く</a></div>'; }).join("");
      h += "</section>";
    }
    h += bucketPanel(all);
    return h;
  };
})(window.KMC);
