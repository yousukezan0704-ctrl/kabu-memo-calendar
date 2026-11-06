/* 画面の切り替えと、ボタン操作のまとめ役 */
(function (K) {
  var E = K.esc, $ = function (id) { return document.getElementById(id); };
  /* 画面下のナビ（親指で押す）。[id, 文字, 絵文字]。watch/search は「銘柄・テーマ」画面の注目／銘柄のサブタブへ移る */
  var TABS = [["cal", "カレンダー", "📅"], ["ir", "重要IR", "📣"], ["watch", "注目", "⭐"], ["search", "銘柄", "🔍"], ["memo", "メモ・設定", "📝"]];
  function activeTab() {
    if (K.ui.tab !== "stocks") return K.ui.tab;
    return K.sUi.sub === "watch" && !K.sUi.code ? "watch" : "search";
  }

  function render(keepFocusId) {
    /* 描き直す前に、いま開いている折りたたみを記録する（toggleイベントの遅れで閉じてしまうのを防ぐ） */
    Array.prototype.forEach.call($("main").querySelectorAll("details[data-key]"), function (d) { K.openState[d.dataset.key] = d.open; });
    var nav = TABS.map(function (t) {
      var on = activeTab() === t[0];
      return '<button class="tab' + (on ? " on" : "") + '" data-act="tab" data-v="' + t[0] + '"' + (on ? ' aria-current="page"' : "") + '><span class="ti" aria-hidden="true">' + t[2] + "</span><span class=\"tn\">" + t[1] + "</span></button>";
    }).join("");
    $("tabs").innerHTML = nav;
    var main = $("main"), h = "";
    try {
      if (K.ui.tab === "cal") h = K.renderCal();
      else if (K.ui.tab === "ir") h = K.renderIR();
      else if (K.ui.tab === "stocks") h = K.renderStocks();
      else h = K.renderMemo();
    } catch (e) {
      h = '<p class="warn">画面の表示でエラーが起きました: ' + E(e.message) + "。バックアップを書き出してから再読み込みしてください。</p>";
      if (window.console) console.error(e);
    }
    main.innerHTML = h;
    if (keepFocusId && $(keepFocusId)) {
      var el = $(keepFocusId);
      el.focus();
      try { el.setSelectionRange(el.value.length, el.value.length); } catch (e) { /* 数値などは無視 */ }
    }
  }
  K.render = render;

  function go(tab) {
    if (tab === "watch" || tab === "search") { K.ui.tab = "stocks"; K.sUi.sub = tab === "watch" ? "watch" : "stocks"; K.sUi.code = ""; }
    else K.ui.tab = tab;
    render(); window.scrollTo(0, 0);
  }

  function openMemo(id) { K.mUi.id = id; go("memo"); }

  function addEventDialog() {
    var d = $("dlg");
    d.innerHTML = '<form method="dialog" class="form"><h3>予定を追加</h3>' +
      '<label>種類<select id="ae-kind">' + Object.keys(K.KINDS).filter(function (k) { return k !== "forecast_item"; }).map(function (k) { return '<option value="' + k + '"' + (k === "mine" ? " selected" : "") + ">" + E(K.KINDS[k].label) + "</option>"; }).join("") + "</select></label>" +
      '<label>出どころ<select id="ae-origin"><option value="memo">自分のメモ</option><option value="official">会社公表（自分で転記。元URLを付ける）</option><option value="inference">AIによる推測</option></select></label>' +
      '<label>コード<input id="ae-code" size="8"></label><label>会社名<input id="ae-name"></label>' +
      '<label>内容<input id="ae-title"></label>' +
      '<label>日付の確かさ<select id="ae-prec"><option value="day">日付が決まっている</option><option value="month">月だけ</option><option value="season">季節（春など）</option><option value="fy">年度内・期など</option><option value="unknown">時期不明</option></select></label>' +
      '<label>日付（月・季節のときは目安の日でも空でも可）<input id="ae-date" type="date"></label>' +
      '<label>原文の言い回し（例: 来春）<input id="ae-raw"></label>' +
      '<label>会社公表の時刻（書いてある場合のみ。空欄なら「未公表」と表示）<input id="ae-time" placeholder="例 15:00"></label>' +
      '<p class="muted">決算発表予定日は、会社のIR日程ページや、東証の<a href="https://www.jpx.co.jp/listing/event-schedules/financial-announcement/index.html" target="_blank" rel="noopener">決算発表予定日一覧</a>（東証の規約上、データの転載はできないため、見て自分で入力してください）で確認できます。</p>' +
      '<label>元資料URL（https）<input id="ae-url"></label><label>メモ<textarea id="ae-note" rows="2"></textarea></label>' +
      '<div class="row"><button value="ok" id="ae-ok">追加</button><button value="cancel">やめる</button></div></form>';
    d.showModal();
    $("ae-ok").addEventListener("click", function (ev) {
      var prec = $("ae-prec").value, date = $("ae-date").value;
      if (prec === "day" && !date) { ev.preventDefault(); K.toast("日付を入れてください", true); return; }
      if (!$("ae-title").value.trim()) { ev.preventDefault(); K.toast("内容を入れてください", true); return; }
      var url = $("ae-url").value.trim();
      K.state.userEvents.push({
        id: K.uid(), kind: $("ae-kind").value, origin: $("ae-origin").value, code: $("ae-code").value.trim().toUpperCase(),
        name: $("ae-name").value.trim(), title: $("ae-title").value.trim(), precision: prec, date: date, rawText: $("ae-raw").value.trim(),
        time: $("ae-time").value.trim(), url: K.safeUrl(url), note: $("ae-note").value.trim(), confirmed: prec === "day" && $("ae-origin").value === "official"
      });
      K.save(); setTimeout(render, 0);
    });
  }

  var NOTIFY_IDS = { "n-before": "before", "n-today": "today", "n-ir": "ir", "n-memo": "memo", "n-browser": "browser" };
  var A = {
    tab: function (t) { go(t.dataset.v); },
    view: function (t) { K.ui.view = t.dataset.v; render(); },
    prev: function () { var d = K.parseYmd(K.ui.cursor); d.setMonth(d.getMonth() - 1); K.ui.cursor = K.ymd(d); render(); },
    next: function () { var d = K.parseYmd(K.ui.cursor); d.setMonth(d.getMonth() + 1); K.ui.cursor = K.ymd(d); render(); },
    wprev: function () { K.ui.selected = K.addDays(K.ui.selected, -7); render(); },
    wnext: function () { K.ui.selected = K.addDays(K.ui.selected, 7); render(); },
    "goto-today": function () { K.ui.selected = K.today(); K.ui.cursor = K.today().slice(0, 7) + "-01"; render(); },
    pick: function (t) { K.ui.selected = t.dataset.date; render(); },
    kind: function (t) {
      var k = t.dataset.kind, all = Object.keys(K.KINDS);
      if (!K.filter.kinds) { K.filter.kinds = {}; all.forEach(function (x) { K.filter.kinds[x] = true; }); }
      K.filter.kinds[k] = !K.filter.kinds[k];
      if (all.every(function (x) { return K.filter.kinds[x]; })) K.filter.kinds = null;
      render();
    },
    chk: function (t) { K.state.checked[t.dataset.id] = !K.state.checked[t.dataset.id]; K.save(); render(); },
    fav: function (t) { K.toggleFav(t.dataset.code); render(); },
    stock: function (t) {
      if (K.ui.tab !== "stocks") K.sUi.sub = "stocks";   // 注目・銘柄の一覧から開いたときは、戻る先をそのまま残す
      K.ui.tab = "stocks"; K.sUi.code = t.dataset.code; render(); window.scrollTo(0, 0);
    },
    addfav: function () {
      var c = ($("w-add").value || "").trim().toUpperCase();
      if (!/^[0-9A-Z]{4}$/.test(c)) { K.toast("コードは英数字4桁です（例 7203）", true); return; }
      if (!K.isFav(c)) K.toggleFav(c);
      render();
    },
    srctest: function () {
      var repo = ($("src-repo").value || "").trim() || K.DEFAULT_REPO, tok = ($("src-token").value || "").trim(), old = K.srcGet();
      if (!K.srcValidRepo(repo)) { K.toast("リポジトリ名は「所有者/名前」の形で入れてください", true); return; }
      if (tok && !/^[A-Za-z0-9_-]{20,}$/.test(tok)) { K.toast("トークンの形が正しくありません（コピーし直してください）", true); return; }
      if (!tok && old) tok = old.token;
      if (!tok) { K.toast("トークンを入力してください", true); return; }
      if (!K.srcSave(repo, tok)) { K.toast("この端末に保存できませんでした（ブラウザの設定を確認してください）", true); return; }
      K.srcUi = { msg: "接続テスト中…", ok: null }; render();
      K.fetchData("status.json").then(function (j) {
        K.srcUi = { msg: "接続できました（取得 " + K.nowStamp() + (j && j.generated_at ? " ／ データ更新 " + String(j.generated_at).replace("T", " ").slice(0, 16) : "") + "）。データを読み込みます。", ok: true };
        return K.reloadAll();
      }).catch(function (e) {
        K.srcUi = { msg: "接続できませんでした: " + (e && e.message ? e.message : "不明なエラー"), ok: false }; render();
      });
    },
    srcclear: function () {
      if (!confirm("この端末に保存したトークンを消して、接続を解除しますか？")) return;
      K.srcClear(); K.srcUi = { msg: "接続を解除しました（トークンをこの端末から消しました）", ok: true };
      K.reloadAll();
    },
    irseen: function () { K.setNotify("seenAt", K.nowStamp()); K.toast("既読にしました"); render(); },
    sback: function () { K.sUi.code = ""; render(); },
    ssub: function (t) { K.sUi.sub = t.dataset.v; render(); },
    "open-code": function () {
      var c = ($("s-code").value || "").trim().toUpperCase();
      if (!/^[0-9A-Z]{4}$/.test(c)) { K.toast("コードは英数字4桁です（例 7203）", true); return; }
      K.sUi.code = c; render();
    },
    irsub: function (t) { K.irUi.sub = t.dataset.v; render(); },
    "more-cmp": function () { K.irUi.cmpLimit = (K.irUi.cmpLimit || 20) + 20; render(); },
    "more-ir": function () { K.irUi.limit += 20; render(); },
    "more-list": function () { K.ui.listLimit += 40; render(); },
    "more-bucket": function () { K.ui.bucketLimit = (K.ui.bucketLimit || 20) + 20; render(); },
    addevent: addEventDialog,
    deluser: function (t) {
      if (!confirm("この予定を削除しますか？")) return;
      K.state.userEvents = K.state.userEvents.filter(function (u) { return u.id !== t.dataset.id; }); K.save(); render();
    },
    tomemo: function (t) {
      var it = K.items.filter(function (x) { return x.id === t.dataset.id; })[0];
      if (!it) return;
      var m = K.newMemo({
        code: it.code, name: it.name, irUrl: K.safeUrl(it.url), irTitle: it.title,
        reason: "IR: " + it.title, checks: "原文を確認する（" + (it.kindLabel || "") + "）", reviewDate: K.quickDate("nextweek")
      });
      K.toast("メモを作りました。再確認日は来週の月曜にしてあります（変更できます）");
      openMemo(m.id);
    },
    newmemo: function (t) { var m = K.newMemo({ code: t.dataset.code || "", name: t.dataset.code ? K.stockName(t.dataset.code) : "" }); openMemo(m.id); },
    gomemo: function (t) { openMemo(t.dataset.id); },
    mback: function () { K.mUi.id = ""; render(); },
    mfilter: function (t) { K.mUi.filter = t.dataset.v; render(); },
    qdate: function (t) { K.memoInput("reviewDate", K.quickDate(t.dataset.q)); render(); },
    qclear: function () { K.memoInput("reviewDate", ""); render(); },
    delmemo: function (t) {
      if (!confirm("このメモを削除しますか？（バックアップがないと元に戻せません）")) return;
      K.state.memos = K.state.memos.filter(function (m) { return m.id !== t.dataset.id; }); K.mUi.id = ""; K.save(); render();
    },
    backup: function () { K.exportBackup(); render(); },
    undorestore: function () {
      if (!confirm("直前の復元を取り消して、復元前の状態に戻しますか？")) return;
      var ok = K.undoRestore();
      K.toast(ok ? "元に戻しました" : "戻せるデータがありません", !ok); render();
    },
    ics: function () {
      var r = K.makeIcs();
      if (!r.count) { K.toast("書き出せる予定がありません（追跡中で再確認日のあるメモ、または注目銘柄の確定した決算予定が対象です。通知がOFFの項目は含みません）", true); return; }
      K.download("株メモ_確認日.ics", r.text, "text/calendar");
      K.toast("メモ " + r.memoCount + "件・決算予定 " + r.earnCount + "件を書き出しました。開いてカレンダーに追加してください");
    },
    notiftest: function () {
      if (!("Notification" in window)) { K.toast("このブラウザは通知に対応していません。カレンダー取り込み(.ics)をお使いください", true); return; }
      Notification.requestPermission().then(function (p) {
        if (p === "granted") { new Notification("株メモ", { body: "通知のテストです（アプリを開いている間の通知）" }); K.toast("通知を出しました"); }
        else K.toast("通知が許可されていません（" + p + "）", true);
      });
    },
    addsplit: function (t) {
      var d = $("split-date").value; if (!d) { K.toast("日付を選んでください", true); return; }
      var a = K.state.splits[t.dataset.code] = K.state.splits[t.dataset.code] || [];
      if (a.indexOf(d) < 0) a.push(d); K.save(); render();
    },
    clearsplit: function (t) { delete K.state.splits[t.dataset.code]; K.save(); render(); },
    delprices: function (t) {
      if (!confirm("この銘柄の株価データを削除しますか？")) return;
      delete K.state.prices[t.dataset.code]; delete K.state.priceMeta[t.dataset.code]; K.save(); render();
    },
    addts: function () {
      var th = $("ts-theme").value.trim(), code = $("ts-code").value.trim().toUpperCase();
      if (!th || !/^[0-9A-Z]{4}$/.test(code)) { K.toast("テーマと4桁のコードを入れてください", true); return; }
      K.state.themeStocks.push({ id: K.uid(), theme: th, code: code, name: $("ts-name").value.trim(), relation: $("ts-rel").value, evidence: $("ts-ev").value.trim(), url: K.safeUrl($("ts-url").value.trim()), confirmed_at: $("ts-date").value });
      K.save(); render();
    },
    delts: function (t) { K.state.themeStocks = K.state.themeStocks.filter(function (s) { return s.id !== t.dataset.id; }); K.save(); render(); },
    addb: function () {
      var title = $("b-title").value.trim(); if (!title) { K.toast("見出しを入れてください", true); return; }
      K.state.breaking.push({ id: K.uid(), at: $("b-at").value || K.nowStamp().replace(" ", "T").slice(0, 16), title: title, note: $("b-note").value.trim(), codes: $("b-codes").value.split(/[,、\s]+/).map(function (s) { return s.trim().toUpperCase(); }).filter(Boolean), followups: [] });
      K.save(); render();
    },
    addbf: function (t) {
      var b = K.state.breaking.filter(function (x) { return x.id === t.dataset.id; })[0], v = $("bf-" + t.dataset.id).value.trim();
      if (!b || !v) return; b.followups.push({ at: K.nowStamp().slice(0, 16), text: v }); K.save(); render();
    },
    delb: function (t) { if (confirm("この記録を削除しますか？")) { K.state.breaking = K.state.breaking.filter(function (x) { return x.id !== t.dataset.id; }); K.save(); render(); } }
  };

  document.addEventListener("click", function (ev) {
    var t = ev.target.closest("[data-act]");
    if (!t) return;
    var fn = A[t.dataset.act];
    if (!fn) return;
    if (t.tagName === "A") ev.preventDefault();
    fn(t, ev);
  });

  /* 折りたたみ(<details>)の開閉を覚える。toggle は泡立たないので capture で受ける */
  document.addEventListener("toggle", function (ev) {
    var t = ev.target;
    if (t && t.tagName === "DETAILS" && t.dataset && t.dataset.key) K.openState[t.dataset.key] = t.open;
  }, true);

  document.addEventListener("input", function (ev) {
    var t = ev.target;
    if (t.dataset && t.dataset.f) { K.memoInput(t.dataset.f, t.value); var s2 = $("savestate2"); if (s2) { s2.className = "savestate saving"; s2.textContent = "保存中…"; } return; }
    var id = t.id;
    if (id === "f-text") { K.filter.text = t.value; render(id); }
    else if (id === "s-q") { K.sUi.q = t.value; render(id); }
    else if (id === "w-q") { K.sUi.wq = t.value; render(id); }
  });

  document.addEventListener("change", function (ev) {
    var t = ev.target, id = t.id;
    if (t.dataset && t.dataset.f) {
      K.memoInput(t.dataset.f, t.value);
      if (t.dataset.f === "status" || t.dataset.f === "reviewDate") render();
      return;
    }
    if (id === "f-theme") { K.filter.theme = t.value; render(); }
    else if (id === "f-origin") { K.filter.origin = t.value; render(); }
    else if (id === "f-fav") { K.filter.fav = t.checked; render(); }
    else if (id === "ir-review") { K.irUi.reviewOnly = t.checked; render(); }
    else if (id === "set-sample") { K.state.settings.showSample = t.checked; K.save(); render(); }
    else if (id === "w-sort") { K.sUi.wsort = t.value; render(); }
    else if (id === "w-near") { K.sUi.wnear = t.checked; render(); }
    else if (id === "w-rev") { K.sUi.wrev = t.checked; render(); }
    else if (NOTIFY_IDS[id]) {
      if (id === "n-browser" && t.checked) {
        if (!("Notification" in window)) { K.toast("このブラウザはブラウザ通知に対応していません", true); render(); return; }
        Notification.requestPermission().then(function (p) {
          if (p === "granted") { K.setNotify("browser", true); K.toast("アプリを開いている間の通知をONにしました"); }
          else { K.setNotify("browser", false); K.toast("通知が許可されていないためOFFのままです（" + p + "）", true); }
          render();
        });
        return;
      }
      K.setNotify(NOTIFY_IDS[id], t.checked); render();
    }
    else if (id === "n-ck") { K.state.settings.notifyChecked = t.value; K.save(); }
    else if (id === "n-note") { K.state.settings.notifyNote = t.value; K.save(); }
    else if (id === "csv-adj") {
      var c = K.sUi.code; K.state.priceMeta[c] = K.state.priceMeta[c] || {}; K.state.priceMeta[c].adjusted = t.checked; K.save(); render();
    } else if (id === "csv-file" && t.files[0]) {
      var code = K.sUi.code, f = t.files[0];
      K.readCsvFile(f).then(function (text) {
        var r = K.parseCsv(text);
        if (!r.ok) { K.toast("取り込めません: " + r.msg, true); return; }
        var old = K.state.prices[code] || [], map = {};
        old.forEach(function (x) { map[x.d] = x; });
        r.rows.forEach(function (x) { map[x.d] = x; });    // 同じ日は新しいCSVで更新（二重登録しない）
        K.state.prices[code] = Object.keys(map).sort().map(function (k) { return map[k]; }).slice(-600);
        K.state.priceMeta[code] = Object.assign(K.state.priceMeta[code] || {}, { importedAt: K.nowStamp(), source: "CSV取込（" + f.name + "）", adjusted: $("csv-adj").checked });
        K.save(); K.toast(r.rows.length + "行を取り込みました" + (r.bad ? "（読めなかった行 " + r.bad + "）" : "")); render();
      }).catch(function (e) { K.toast("読み込み失敗: " + e.message, true); });
    } else if (id === "restore-file" && t.files[0]) {
      t.files[0].text().then(function (text) {
        var v = K.validateBackup(text);
        if (!v.ok) { K.toast("復元できません: " + v.msg, true); return; }
        if (!confirm("現在のデータを、" + (v.exportedAt || "不明な日時") + " のバックアップで置き換えます。よろしいですか？\n（直前の状態は「復元を取り消す」で戻せます）")) return;
        K.toast(K.restoreBackup(v.data) ? "復元しました" : "復元後の保存に失敗しました", false); render();
      });
    }
  });

  /* ---- 起動 ---- */
  K.load();
  var sw = "serviceWorker" in navigator && location.protocol.indexOf("http") === 0;
  if (sw) navigator.serviceWorker.register("sw.js").catch(function () { /* 未対応でも動く */ });
  window.addEventListener("beforeunload", function () { K.saveNow(); });
  render();
  K.loadData().then(function () {
    render();
    if (K.fireNotices) { K.fireNotices(); setInterval(K.fireNotices, 15 * 60 * 1000); }   // 開いている間だけ（日付が変わったら再確認）
  });
  $("savestate").textContent = K.saveStatus.text;
})(window.KMC);
