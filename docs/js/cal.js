/* カレンダー画面（月・週・一覧）と、予定カードの共通部品 */
(function (K) {
  var E = K.esc;
  K.ui = K.ui || { tab: "cal", view: "month", cursor: K.today().slice(0, 7) + "-01", selected: K.today(), listLimit: 40 };

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
    if (it.kind === "earnings_actual") return '<span class="badge b-ok">発表済み(実績)</span>';
    if (it.isAnnounce) return '<span class="badge b-ok">発表日</span>';
    if (it.date) {
      return it.confirmed ? '<span class="badge b-ok">日付確定</span>'
        : '<span class="badge b-warn">未確定</span>' + (it.review ? ' <span class="badge b-ng">要確認</span>' : "");
    }
    return '<span class="badge b-warn">時期のみ</span>' + (it.review ? ' <span class="badge b-ng">要確認</span>' : "");
  };

  /* 確認状況: 日付が確定していない・要確認のものは「確定」「確認済み」にしない */
  K.statusBadge = function (it) {
    if (it.src !== "ir") return "";
    if (it.checkedByMe) return "";
    var ok = it.confirmed && !it.review && it.date;
    if (it.kind === "earnings_actual" && !it.review) ok = true;
    return ok ? '<span class="badge b-ok st">確認済み</span>' : '<span class="badge b-ng st">要確認</span>';
  };
  /* 情報源の短い表記（TDnetの資料はURLで判定） */
  K.sourceLabel = function (it) {
    if (it.src === "user") return "自分で入力";
    if (it.src === "memo") return "自分のメモ";
    if (it.sample) return "サンプル（架空）";
    return /tdnet/i.test(it.url || "") ? "TDnet（会社の適時開示）" : "会社公表の資料";
  };

  function md(s) { return (s || "").slice(5, 10).replace("-", "/"); }

  /* 予定1件のカード（コンパクト）。
     1行目=種類+会社 / 2行目=要点 / 3行目=発表日・対象時期・確かさ。原文などは「根拠を見る」に畳む。
     opt.pre = カード本文の下に常に見せたいHTML、opt.fold = 「根拠を見る」の中に足すHTML */
  K.itemCard = function (it, opt) {
    opt = opt || {};
    var fav = it.code && K.isFav(it.code);
    var h = '<article class="card' + (it.confirmed ? "" : " unconf") + (it.done ? " isdone" : "") + '" style="--c:' + K.kindOf(it.kind).color + '">';
    h += '<div class="l1">' + K.chip(it.kind) + ' <span class="ttl">' +
      (it.code ? '<a href="#" data-act="stock" data-code="' + E(it.code) + '">' + E(it.name || "") + " (" + E(it.code) + ")</a>" : E(it.name || "")) + "</span></div>";
    h += '<div class="body">' + E(it.title) + "</div>";
    h += '<div class="l3">';
    if (it.src === "ir") {
      h += '<span class="muted">発表 ' + E(md(it.announced_at)) + " ／ 対象 " + E(it.raw || "未取得") + (it.date ? " → " + E(K.fmtDay(it.date)) : "") + "</span> ";
      if (it.kind === "earnings" || it.kind === "earnings_actual") h += '<span class="muted">／ 時刻 ' + E(K.timeText(it)) + "</span> ";
    } else if (it.time || it.kind === "earnings") {
      h += '<span class="muted">時刻 ' + E(K.timeText(it)) + "</span> ";
    }
    h += (it.kind === "forecast_item" ? "" : K.certainty(it) + " ") + K.originBadge(it.origin);
    h += " " + K.statusBadge(it);
    if (it.sample) h += ' <span class="badge b-sample">サンプル</span>';
    if (it.src === "ir" && K.catOf(it)) h += ' <span class="badge b-cat">' + E(K.catOf(it)) + "</span>";
    if (it.src === "ir" && K.RISKY_KINDS[it.kind]) h += ' <span class="badge b-warn">自動抽出・要確認</span>';
    if (it.src === "ir" && /^revision/.test(it.kind) && String(it.refId).indexOf("table") >= 0 && it.ev && it.ev.note) h += ' <span class="badge b-warn">表の数値から判定</span>';
    if (it.checkedByMe) h += ' <span class="badge b-ok">確認済み</span>';
    h += "</div>";
    if (it.ev && it.ev.note) h += '<div class="note">注記: ' + E(it.ev.note) + "</div>";
    if (opt.pre) h += opt.pre;
    if (it.src === "ir") {
      var f = '<dl class="kv">';
      f += "<dt>情報源</dt><dd>" + E(K.sourceLabel(it)) + "</dd>";
      f += "<dt>発表日</dt><dd>" + E((it.announced_at || "").slice(0, 16) || "未取得") + "</dd>";
      f += "<dt>確認状況</dt><dd>" + (it.checkedByMe ? "自分で確認済み" : (it.confirmed && !it.review && it.date) || it.kind === "earnings_actual" ? "確認済み（会社の公表資料から抽出）" : "要確認（自動抽出のため、元資料で確かめてください）") + "</dd>";
      if (it.bucket && it.bucket.start) f += "<dt>時期の解釈</dt><dd>" + E(it.bucket.label) + "</dd>";
      f += "<dt>時刻</dt><dd>" + E(K.timeText(it)) + "</dd>";
      if (/^(revision|forecast|fx)/.test(it.kind)) f += "<dt>業績影響時期</dt><dd>" + E(it.impact || "記載なし") + "</dd>";
      f += "</dl>";
      if (it.reason) f += '<div class="warn">確認理由: ' + E(it.reason) + "</div>";
      f += '<blockquote>「' + E(it.quote) + "」<br><small>該当ページ: " + E(it.page) + " ／ 最終確認: " + E((it.checked_at || "").replace("T", " ").slice(0, 16)) + "</small></blockquote>";
      var u = K.safeUrl(it.url);
      if (u) f += '<a class="link" href="' + E(u) + '" target="_blank" rel="noopener">元のIR資料を開く</a>';
      f += opt.fold || "";
      h += K.det("ev:" + it.id, "根拠を見る", f, false, "sub");
    } else if (it.note) {
      h += '<div class="muted">' + E(it.note) + "</div>";
    }
    if (!opt.noActions) {
      var main = "", more = "";
      if (it.src === "ir") {
        main += '<button data-act="chk" data-id="' + E(it.refId) + '">' + (it.checkedByMe ? "確認済みを外す" : "✓ 確認した") + "</button>";
        main += '<button data-act="tomemo" data-id="' + E(it.id) + '">メモにする</button>';
      }
      if (it.src === "memo") main += '<button data-act="gomemo" data-id="' + E(it.refId) + '">メモを開く</button>';
      if (it.src === "user") more += '<button data-act="deluser" data-id="' + E(it.refId) + '">この予定を削除</button>';
      if (it.code) more += '<button data-act="fav" data-code="' + E(it.code) + '">' + (fav ? "★ お気に入り解除" : "☆ お気に入り") + "</button>";
      if (main || more) {
        h += '<div class="row wrap acts">' + main +
          (more ? K.det("mo:" + it.id, "…", '<div class="row wrap">' + more + "</div>", false, "morefold") : "") + "</div>";
      }
    }
    return h + "</article>";
  };

  /* 会社が公表した時刻だけを出す。決算発表で時刻が見つからないときは「未公表」 */
  K.timeText = function (it) {
    if (it.time) return "会社公表 " + it.time;
    return it.kind === "earnings" ? "未公表（会社の公表資料に時刻の記載なし）" : "記載なし";
  };

  /* ---------- 絞り込み欄（折りたたみ） ---------- */
  K.activeFilter = function () {
    var f = K.filter;
    return !!((f.text || "").trim() || f.theme || f.fav || f.origin || f.kinds);
  };
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
    return K.det("filter", "🔍 絞り込み" + (K.activeFilter() ? ' <span class="badge b-warn">絞り込み中</span>' : ""), h, false, "filterfold");
  };

  /* ---------- 日付ごと・種類ごとのグループ ---------- */
  function rank(k) { return k === "mine" ? 0 : k === "earnings" ? 1 : 2 + Object.keys(K.KINDS).indexOf(k); }
  /* 種類ごとの折りたたみ。自分の確認(メモ)と決算は常に開く。件数が少ない日(5件以下)も開く */
  function groups(items, keyPrefix) {
    var by = {};
    items.forEach(function (it) { (by[it.kind] = by[it.kind] || []).push(it); });
    return Object.keys(by).sort(function (a, b) { return rank(a) - rank(b); }).map(function (k) {
      var g = by[k], open = k === "mine" || k === "earnings" || items.length <= 5;
      return K.det(keyPrefix + ":" + k, K.chip(k) + ' <span class="cn">' + g.length + "件</span>",
        g.map(function (it) { return K.itemCard(it); }).join(""), open, "grp");
    }).join("");
  }

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
    var h = '<div class="mhead"><button data-act="prev">◀ 前月</button><strong>' + y + "年" + (mo + 1) + '月</strong><button data-act="next">次月 ▶</button></div>';
    h += '<div class="grid">' + K.WD.map(function (w, i) { return '<div class="dow' + (i === 0 ? " sun" : i === 6 ? " sat" : "") + '">' + w + "</div>"; }).join("");
    for (var i = 0; i < startDow; i++) h += '<div class="cell empty"></div>';
    for (var d = 1; d <= days; d++) {
      var ds = y + "-" + K.pad(mo + 1) + "-" + K.pad(d), list = map[ds] || [];
      var kinds = [];
      list.forEach(function (it) { if (kinds.indexOf(it.kind) < 0) kinds.push(it.kind); });
      h += '<div class="cell' + (ds === t ? " today" : "") + (ds === K.ui.selected ? " sel" : "") + '" data-act="pick" data-date="' + ds + '"><div class="dn">' + d + "</div>";
      if (list.length) {
        h += '<div class="dots">' + kinds.slice(0, 3).map(function (k) { return '<i style="--c:' + K.kindOf(k).color + '"></i>'; }).join("") + '</div><div class="cnt">' + list.length + "</div>";
      }
      h += "</div>";
    }
    return h + "</div>";
  }

  /* ---------- 週表示 ---------- */
  function weekView(items) {
    var sel = K.parseYmd(K.ui.selected);
    var start = K.addDays(K.ui.selected, -sel.getDay()), map = byDate(items), t = K.today();
    var h = '<div class="mhead"><button data-act="wprev">◀ 前週</button><strong>' + E(K.fmtDay(start)) + "〜</strong><button data-act=\"wnext\">次週 ▶</button></div>";
    for (var i = 0; i < 7; i++) {
      var ds = K.addDays(start, i), list = map[ds] || [];
      h += '<section class="wday' + (ds === t ? " today" : "") + '"><h4>' + E(K.fmtDay(ds)) + (list.length ? ' <span class="muted">' + list.length + "件</span>" : ' <span class="muted">予定なし</span>') + "</h4>";
      if (list.length) h += groups(list, "wk:" + ds);
      h += "</section>";
    }
    return h;
  }

  /* ---------- 一覧（日付順・直近30日） ---------- */
  function listView(items) {
    var from = K.today(), to = K.addDays(K.today(), 30);
    var list = items.filter(function (it) { return it.date && it.date >= from && it.date <= to; })
      .sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
    var h = '<p class="muted">今日から30日先までを、日付ごと・種類ごとにまとめています。</p>';
    if (!list.length) return h + '<p class="empty">この期間に表示できる予定はありません。</p>';
    var map = byDate(list), dates = Object.keys(map).sort(), shown = 0, i;
    for (i = 0; i < dates.length && (shown < K.ui.listLimit || i === 0); i++) {
      var ds = dates[i];
      h += '<h4 class="dh' + (ds === K.today() ? " today" : "") + '">' + E(K.fmtDay(ds)) + ' <span class="muted">' + map[ds].length + "件</span></h4>" + groups(map[ds], "ls:" + ds);
      shown += map[ds].length;
    }
    if (i < dates.length) h += '<button data-act="more-list">もっと見る（残り ' + (dates.length - i) + "日分）</button>";
    return h;
  }

  /* ---------- 時期別の予定（日付が決まっていないもの。初期は閉） ---------- */
  function bucketPanel(items) {
    var list = items.filter(function (it) { return !it.date && it.bucket; });
    var title = "時期別の予定（日付は未確定） " + list.length + "件";
    if (!list.length) return K.det("bucket", E(title), '<p class="empty">「春」「年度内」などの時期だけが書かれた予定はありません。</p>', false, "pf");
    list.sort(function (a, b) { return (a.bucket.start || "9999") < (b.bucket.start || "9999") ? -1 : 1; });
    var h = '<p class="muted">会社が日付まで決めていない予定です。原文のまま残し、解釈が曖昧なものは「要確認」と表示します。</p>';
    list.slice(0, K.ui.bucketLimit || 20).forEach(function (it) { h += '<div class="bk"><div class="bkl">' + E(it.bucket.label) + "</div>" + K.itemCard(it) + "</div>"; });
    if (list.length > (K.ui.bucketLimit || 20)) h += '<button data-act="more-bucket">さらに表示（残り ' + (list.length - (K.ui.bucketLimit || 20)) + "件）</button>";
    return K.det("bucket", E(title), h, false, "pf");
  }

  K.renderCal = function () {
    var all = K.applyFilter(K.buildItems());
    var h = (K.statusAlert ? K.statusAlert() : "") + (K.homeBanner ? K.homeBanner() : "");
    h += '<div class="seg">' + [["month", "月"], ["week", "週"], ["list", "一覧"]].map(function (v) {
      return '<button class="' + (K.ui.view === v[0] ? "on" : "") + '" data-act="view" data-v="' + v[0] + '">' + v[1] + "</button>";
    }).join("") + '<button data-act="goto-today">今日</button><button data-act="addevent">＋ 予定</button></div>';
    h += K.filterBar();
    if (K.ui.view === "month") h += monthView(all);
    else if (K.ui.view === "week") h += weekView(all);
    else h += listView(all);
    if (K.ui.view === "month") {
      var sel = byDate(all)[K.ui.selected] || [];
      h += '<section class="panel daypanel"><h3>' + E(K.fmtDay(K.ui.selected)) + " の予定とメモ" + (sel.length ? ' <span class="muted">' + sel.length + "件</span>" : "") + "</h3>";
      h += sel.length ? groups(sel, "dy:" + K.ui.selected) : '<p class="empty">この日の予定はありません。</p>';
      var ms = K.state.memos.filter(function (m) { return (m.createdAt || "").slice(0, 10) === K.ui.selected; });
      if (ms.length) h += "<h4>この日に作ったメモ</h4>" + ms.map(function (m) { return '<div class="mline">' + E(m.name || m.code || "メモ") + ' <a href="#" data-act="gomemo" data-id="' + E(m.id) + '">開く</a></div>'; }).join("");
      h += "</section>";
    }
    h += bucketPanel(all);
    return h;
  };
})(window.KMC);
