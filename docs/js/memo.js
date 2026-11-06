/* メモ画面: 銘柄メモ（自動保存）、再確認日、通知(.ics)、バックアップ */
(function (K) {
  var E = K.esc;
  K.mUi = K.mUi || { id: "", filter: "open" };

  /* ---------- お知らせ（ホーム上部）。注目（お気に入り）銘柄だけが対象。設定でONの項目だけ出す ---------- */
  /* 一覧を作る。type: before(決算前日) / today(決算当日) / ir(重要IR新着)。決算は日付が確定しているものだけ */
  K.noticeList = function () {
    var cfg = K.notifyCfg(), fav = K.state.favorites, out = [];
    if (!fav.length) return out;
    var items = K.buildItems().slice().sort(function (a, b) { return (b.time ? 1 : 0) - (a.time ? 1 : 0); });
    var t = K.today();
    function earn(date, type, on) {
      if (!on) return;
      var seen = {};
      items.forEach(function (i) {
        if (i.kind !== "earnings" || i.src === "memo" || i.date !== date || !i.confirmed || fav.indexOf(i.code) < 0) return;
        var k = i.code + date;
        if (seen[k]) return;
        seen[k] = 1;
        out.push({ key: type + ":" + i.code + ":" + date, type: type, it: i, date: date });
      });
    }
    earn(K.addDays(t, 1), "before", cfg.before);
    earn(t, "today", cfg.today);
    if (cfg.ir) {
      var lo = K.addDays(t, -7) + " 00:00:00";
      if (cfg.seenAt && cfg.seenAt > lo) lo = cfg.seenAt;
      var by = {};
      items.forEach(function (i) {
        if (fav.indexOf(i.code) < 0) return;
        var imp = K.irImportance(i);
        if (!imp || (i.announced_at || "") <= lo) return;
        var k = i.code + "|" + (i.url || i.refId);
        if (!by[k] || imp.pri < by[k].imp.pri) by[k] = { key: "ir:" + k, type: "ir", it: i, imp: imp };
      });
      Object.keys(by).map(function (k) { return by[k]; }).sort(function (a, b) {
        return a.imp.pri - b.imp.pri || (a.it.announced_at < b.it.announced_at ? 1 : -1);
      }).forEach(function (x) { out.push(x); });
    }
    return out;
  };
  function who(it) { return (it.name || "") + (it.code ? " (" + it.code + ")" : ""); }
  K.noticeText = function (n) {
    var i = n.it;
    if (n.type === "ir") return n.imp.label + ": " + who(i);
    return (n.type === "before" ? "明日" : "今日") + "は決算発表: " + who(i) + "（" + (i.time ? "時刻 " + i.time : "時刻 未公表") + "）";
  };
  K.noticeBox = function () {
    var L = K.noticeList();
    if (!L.length) return "";
    var body = "";
    L.slice(0, 10).forEach(function (n) {
      var i = n.it, link = '<a href="#" data-act="stock" data-code="' + E(i.code) + '">' + E(who(i)) + "</a>";
      if (n.type === "ir") {
        var hot = n.imp.pri === 1;
        body += '<div class="ntc' + (hot ? " hot" : "") + '">' + K.chip(i.kind) + " " + (hot ? "<b>" : "") + E(n.imp.label) + (hot ? "</b>" : "") + " " + link +
          ' <span class="muted">' + E((i.announced_at || "").slice(5, 16)) + "</span>" + (K.safeUrl(i.url) ? ' <a href="' + E(i.url) + '" target="_blank" rel="noopener">原文</a>' : "") + "</div>";
      } else {
        body += '<div class="ntc"><span class="badge ' + (n.type === "today" ? "b-ng" : "b-warn") + '">' + (n.type === "today" ? "今日" : "明日") + "</span> 決算発表 " + link +
          " " + E(K.fmtDay(n.date)) + " ／ " + (i.time ? "時刻 " + E(i.time) : '<span class="badge b-warn">時刻 未公表</span>') + "</div>";
      }
    });
    if (L.length > 10) body += '<p class="muted">ほか ' + (L.length - 10) + "件</p>";
    if (L.some(function (n) { return n.type === "ir"; })) {
      var seen = K.notifyCfg().seenAt;
      body += '<div class="row wrap"><button data-act="irseen">重要IRを既読にする</button><span class="muted">' + (seen ? E(seen.slice(0, 16)) + " に既読にした以降（最大7日）" : "直近7日分") + "</span></div>";
    }
    return K.det("notices", "🔔 お知らせ（注目銘柄） " + L.length + "件", body, true, "pf notices");
  };

  K.homeBanner = function () {
    var due = K.notifyCfg().memo ? K.dueMemos() : [], t = K.today();
    var h = '<section class="home">';
    var st = K.data.status;
    if (!K.hasRealData()) h += '<div class="warn">実データは未取得です。表示中のものにサンプル(架空)が含まれる場合は「サンプル」と書いてあります。</div>';
    h += K.noticeBox();
    if (!due.length) return h + "</section>";
    h += "<h3>⏰ 自分が調べる日が来ています（" + due.length + "件）</h3>";
    due.slice(0, 6).forEach(function (m) {
      var over = m.reviewDate < t;
      h += '<div class="due ' + (over ? "over" : "now") + '"><b>' + (over ? "期限超過 " : "今日 ") + "</b>" + E(m.reviewDate) + " " + E(m.name || m.code || "") + " " +
        E((m.checks || m.reason || "").split("\n")[0].slice(0, 40)) + ' <a href="#" data-act="gomemo" data-id="' + E(m.id) + '">開く</a></div>';
    });
    return h + "</section>";
  };

  K.renderMemo = function () {
    if (K.mUi.id) {
      var m = K.state.memos.filter(function (x) { return x.id === K.mUi.id; })[0];
      if (m) return editor(m);
      K.mUi.id = "";
    }
    return listPage();
  };

  function listPage() {
    var f = K.mUi.filter;
    var L = K.state.memos.filter(function (m) { return f === "all" || (f === "open" ? m.status === "open" : m.status !== "open"); });
    L.sort(function (a, b) { return (a.reviewDate || "9999") < (b.reviewDate || "9999") ? -1 : 1; });
    var h = K.homeBanner();
    h += '<div class="subtabs">' + [["open", "追跡中"], ["closed", "終了"], ["all", "すべて"]].map(function (v) {
      return '<button class="' + (f === v[0] ? "on" : "") + '" data-act="mfilter" data-v="' + v[0] + '">' + v[1] + "</button>";
    }).join("") + "</div>" + '<button class="wide" data-act="newmemo" data-code="">＋ 新しいメモ</button>';
    if (!L.length) h += '<p class="empty">メモがありません。「＋ 新しいメモ」で作れます。</p>';
    L.forEach(function (m) {
      var t = K.today(), st = m.status === "open" ? (m.reviewDate && m.reviewDate < t ? "期限超過" : m.reviewDate === t ? "今日" : "追跡中") : m.status === "done" ? "確認済み" : "見送り";
      h += '<article class="card"><div class="row wrap"><span class="badge o-memo">自分のメモ</span> <span class="badge">' + st + "</span></div>" +
        '<div class="ttl">' + E(m.name || "") + " " + (m.code ? "(" + E(m.code) + ")" : "") + "</div>" +
        '<div class="body">' + E((m.reason || "（注目理由なし）").slice(0, 80)) + "</div>" +
        '<div class="muted">再確認日: ' + E(m.reviewDate || "未設定") + "</div>" +
        '<button data-act="gomemo" data-id="' + E(m.id) + '">開く・編集</button></article>';
    });
    h += tools();
    return h;
  }

  function editor(m) {
    var h = '<button data-act="mback">← メモ一覧へ</button>';
    h += '<section class="panel"><h3>メモ</h3><div class="form">' +
      '<label>コード<input data-f="code" value="' + E(m.code) + '" size="8"></label>' +
      '<label>会社名<input data-f="name" value="' + E(m.name) + '"></label>' +
      '<label>注目理由<textarea data-f="reason" rows="3">' + E(m.reason) + "</textarea></label>" +
      '<label>確認事項（調べること）<textarea data-f="checks" rows="3">' + E(m.checks) + "</textarea></label>" +
      '<label>元のIR（URLかタイトル）<input data-f="irUrl" value="' + E(m.irUrl) + '"></label>' +
      '<label>追跡を終える条件<input data-f="endCondition" value="' + E(m.endCondition) + '" placeholder="例: 量産開始のIRが出たら終了"></label>' +
      "</div>";
    h += '<h4>自分が調べる日（再確認日）</h4><div class="row wrap">' +
      [["tomorrow", "明日"], ["nextweek", "来週(月曜)"], ["week", "1週間後"], ["month", "1か月後"]].map(function (q) {
        return '<button data-act="qdate" data-q="' + q[0] + '">' + q[1] + "</button>";
      }).join("") + '<input type="date" data-f="reviewDate" value="' + E(m.reviewDate) + '"><button data-act="qclear">日付を消す</button></div>';
    h += '<p class="muted">これは「自分が調べる日」です。会社が何かを行う日（決算発表など）とは別に、色の違う「自分の確認」としてカレンダーに出ます。</p>';
    h += '<h4>結果</h4><div class="form"><label>メモの状態<select data-f="status">' +
      [["open", "追跡中"], ["done", "確認済み"], ["dropped", "見送り"]].map(function (o) { return '<option value="' + o[0] + '"' + (m.status === o[0] ? " selected" : "") + ">" + o[1] + "</option>"; }).join("") + "</select></label>" +
      '<label>見送り理由・確認結果<textarea data-f="dropReason" rows="2">' + E(m.dropReason) + "</textarea></label></div>";
    h += '<div class="row"><span id="savestate2" class="savestate ' + K.saveStatus.kind + '">' + E(K.saveStatus.text) + '</span> <button data-act="delmemo" data-id="' + E(m.id) + '" class="danger">このメモを削除</button></div></section>';
    return h;
  }

  /* 入力のたびに呼ばれる（main.js から）。自動保存。 */
  K.memoInput = function (field, value) {
    var m = K.state.memos.filter(function (x) { return x.id === K.mUi.id; })[0];
    if (!m) return;
    m[field] = value;
    m.updatedAt = K.nowStamp();
    K.save();
  };

  /* ---------- 非公開リポジトリへの接続（トークンは画面に出さない） ---------- */
  K.srcUi = K.srcUi || { msg: "", ok: null };
  function srcPanel() {
    var cfg = K.srcGet(), r = K.srcUi;
    var h = '<p class="muted">IRのデータ（予定・財務・履歴）は<b>非公開のGitHubリポジトリ</b>に置いてあります。外出先のiPhoneでも、1回設定すれば見られます。</p>' +
      '<ol class="steps"><li>下の「トークン」欄に、GitHubで作ったトークンを貼る</li><li>「保存して接続テスト」を押す</li><li>「接続できました」と出れば完了。「カレンダー」に戻る</li></ol>' +
      '<p class="warn"><b>トークンの作り方（GitHub → Settings → Developer settings → Fine-grained tokens）</b><br>・対象は<b>この1リポジトリだけ</b>を選ぶ<br>・権限は<b>Contents: Read-only のみ</b><br>・<b>有効期限</b>を付ける<br>トークンは他人に見せないでください。この端末のブラウザにだけ保存され、バックアップや書き出しには含まれません。</p>' +
      '<label>リポジトリ名（所有者/名前）<input id="src-repo" autocomplete="off" value="' + E(cfg ? cfg.repo : K.DEFAULT_REPO) + '"></label>' +
      '<label>トークン<input id="src-token" type="password" autocomplete="off" placeholder="' + (cfg ? "設定済み ••••（変える場合だけ入力）" : "github_pat_ から始まる文字列") + '"></label>' +
      '<p class="muted">状態: ' + (cfg ? "<b>設定済み ••••</b>" : "未設定（この端末では公開サイトの相対パスだけを読みます）") + "</p>" +
      '<div class="row wrap"><button data-act="srctest">保存して接続テスト</button>' + (cfg ? '<button class="danger" data-act="srcclear">接続を解除（この端末のトークンを消す）</button>' : "") + "</div>";
    h += '<p class="muted small">パソコンで open_app.bat から開いた場合は、この設定は不要です。</p>';
    if (r.msg) h += '<p id="src-result" class="' + (r.ok ? "okbox" : "errbox") + '">' + E(r.msg) + "</p>";
    return h;
  }

  /* ---------- 通知・バックアップ ---------- */
  function tools() {
    var s = K.state.settings;
    var nc = K.notifyCfg();
    function ck(id, on, label) { return '<label class="chk"><input id="' + id + '" type="checkbox"' + (on ? " checked" : "") + "> " + label + "</label>"; }
    var h = K.det("tool-notif", "通知・お知らせの設定", '<p class="muted">項目ごとにON/OFFを選べます（この端末に保存）。対象は「注目」（お気に入り）の銘柄です。決算の通知は、日付が確定しているものだけです。</p>' +
      ck("n-before", nc.before, "決算の前日") + ck("n-today", nc.today, "決算の当日") + ck("n-ir", nc.ir, "重要IRの新着（業績修正・配当修正・決算短信）") + ck("n-memo", nc.memo, "メモの再確認日") +
      "<h4>どこに届くか</h4>" +
      "<ol><li><b>アプリを開いたときの「お知らせ」欄</b>（カレンダー・メモの上部）。ONの項目だけ出ます。</li>" +
      "<li><b>iPhoneの標準カレンダー（おすすめ）</b>: 下のボタンで .ics を書き出して取り込むと、前日18:00と当日7:30にiPhone本体が知らせます。OFFの項目は .ics にも含めません。</li>" +
      "<li><b>アプリを開いている間のブラウザ通知</b>: " + ck("n-browser", nc.browser, "ONにする（初回に許可を求めます）") + "ホーム画面に追加したアプリでのみ動く場合があります。</li></ol>" +
      '<p class="warn"><b>未実装:</b> iPhoneでアプリを閉じていても届く「プッシュ通知」は、無料の範囲では実装していません（実機での確認と、外部サービスの設定が必要なためです）。閉じている間の通知が必要なときは .ics をお使いください。</p>' +
      '<div class="row wrap"><button data-act="ics">再確認日と決算予定を .ics で書き出す</button><button data-act="notiftest">通知のテスト</button></div>' +
      '<label>実機での確認結果（自分で記録）<select id="n-ck">' + ["未確認", "確認OK（アプリを閉じても届いた）", "確認NG（届かなかった）"].map(function (o) {
        return '<option' + (s.notifyChecked === o ? " selected" : "") + ">" + o + "</option>";
      }).join("") + '</select></label><input id="n-note" placeholder="メモ（機種・iOSのバージョンなど）" value="' + E(s.notifyNote) + '">', false, "pf");
    h += K.det("tool-src", "非公開データの接続（IRの収集データ）", srcPanel(), false, "pf");
    h += K.det("tool-backup", "バックアップと復元", '<p class="muted">データはこの端末のブラウザの中にだけあります。端末の故障や設定削除に備えて、ときどき書き出してください。最後の書き出し: ' + E(s.lastBackup || "まだありません") + "</p>" +
      '<div class="row wrap"><button data-act="backup">バックアップを書き出す</button><label class="btnlike">バックアップから復元<input id="restore-file" type="file" accept=".json,application/json" hidden></label>' +
      '<button data-act="undorestore">復元を取り消す</button></div>', false, "pf");
    h += K.det("tool-set", "表示設定", '<label class="chk"><input id="set-sample" type="checkbox"' + (s.showSample ? " checked" : "") + "> サンプル（架空のデータ）を表示する</label>", false, "pf");
    return h;
  }

  /* .ics: 再確認日（終日予定）＋ 注目銘柄の確定した決算予定。アラームは 前日18:00 / 当日7:30（ONの項目だけ） */
  K.makeIcs = function () {
    function esc(s) { return String(s || "").replace(/[\\;,]/g, function (c) { return "\\" + c; }).replace(/\r?\n/g, "\\n"); }
    var cfg = K.notifyCfg();
    var L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//kabu-memo-calendar//JP", "CALSCALE:GREGORIAN"];
    var n = 0, ne = 0, stamp = K.today().replace(/-/g, "") + "T000000Z";
    if (cfg.memo) K.state.memos.forEach(function (m) {
      if (m.status !== "open" || !m.reviewDate) return;
      n++;
      var d = m.reviewDate.replace(/-/g, ""), nx = K.addDays(m.reviewDate, 1).replace(/-/g, "");
      L.push("BEGIN:VEVENT", "UID:" + m.id + "@kabu-memo", "DTSTAMP:" + stamp, "DTSTART;VALUE=DATE:" + d, "DTEND;VALUE=DATE:" + nx,
        "SUMMARY:" + esc("株を調べる: " + (m.name || m.code)), "DESCRIPTION:" + esc((m.checks || m.reason || "") + "\n（自分の確認日。会社の予定ではありません）"),
        "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("明日は株の確認日: " + (m.name || m.code)), "TRIGGER:-PT6H", "END:VALARM",   // 前日18:00
        "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("今日は株の確認日: " + (m.name || m.code)), "TRIGGER:PT7H30M", "END:VALARM",   // 当日7:30
        "END:VEVENT");
    });
    if ((cfg.before || cfg.today) && K.state.favorites.length) {
      var t = K.today(), seen = {};
      K.buildItems().slice().sort(function (a, b) { return (b.time ? 1 : 0) - (a.time ? 1 : 0); }).forEach(function (i) {
        if (i.kind !== "earnings" || i.src === "memo" || !i.date || i.date < t || !i.confirmed || K.state.favorites.indexOf(i.code) < 0) return;
        var k = i.code + i.date;
        if (seen[k]) return;
        seen[k] = 1; ne++;
        var d = i.date.replace(/-/g, ""), nx = K.addDays(i.date, 1).replace(/-/g, ""), nm = (i.name || "") + "(" + i.code + ")";
        var tm = i.time ? "会社公表 " + i.time : "時刻は未公表";
        L.push("BEGIN:VEVENT", "UID:earn-" + i.code + "-" + d + "@kabu-memo", "DTSTAMP:" + stamp, "DTSTART;VALUE=DATE:" + d, "DTEND;VALUE=DATE:" + nx,
          "SUMMARY:" + esc("決算発表: " + nm), "DESCRIPTION:" + esc("会社が公表した決算発表の予定日です（" + tm + "）。日付は元の資料で確認してください。"));
        if (cfg.before) L.push("BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("明日は決算発表: " + nm), "TRIGGER:-PT6H", "END:VALARM");
        if (cfg.today) L.push("BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("今日は決算発表: " + nm + "（" + tm + "）"), "TRIGGER:PT7H30M", "END:VALARM");
        L.push("END:VEVENT");
      });
    }
    L.push("END:VCALENDAR");
    return { text: L.join("\r\n"), count: n + ne, memoCount: n, earnCount: ne };
  };

  /* ---------- アプリを開いている間のブラウザ通知（同じ内容は1回だけ） ---------- */
  function show(title, body, tag) {
    try { new Notification(title, { body: body, tag: tag }); }
    catch (e) {
      if (navigator.serviceWorker && navigator.serviceWorker.getRegistration) {
        navigator.serviceWorker.getRegistration().then(function (r) { if (r) r.showNotification(title, { body: body, tag: tag }); }).catch(function () { /* 出せなければ画面のお知らせだけ */ });
      }
    }
  }
  K.fireNotices = function () {
    var cfg = K.notifyCfg();
    if (!cfg.browser || !("Notification" in window) || Notification.permission !== "granted") return 0;
    var t = K.today(), list = K.noticeList().map(function (n) { return { key: n.key, title: n.type === "ir" ? "重要IR" : "決算発表", text: K.noticeText(n) }; });
    if (cfg.memo) K.dueMemos().forEach(function (m) { list.push({ key: "m:" + m.id + ":" + t, title: "メモの再確認日", text: (m.reviewDate < t ? "期限超過: " : "今日: ") + (m.name || m.code || "メモ") }); });
    var fired = cfg.fired, lim = K.addDays(t, -8), c = 0;
    Object.keys(fired).forEach(function (k) { if (fired[k] < lim) delete fired[k]; });
    list.forEach(function (x) {
      if (fired[x.key]) return;
      fired[x.key] = t; c++;
      show("株メモ: " + x.title, x.text, x.key);
    });
    if (c) { K.state.settings.notify = cfg; K.save(); }
    return c;
  };
})(window.KMC);
