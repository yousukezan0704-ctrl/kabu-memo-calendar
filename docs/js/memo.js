/* メモ画面: 銘柄メモ（自動保存）、再確認日、通知(.ics)、バックアップ */
(function (K) {
  var E = K.esc;
  K.mUi = K.mUi || { id: "", filter: "open" };

  K.homeBanner = function () {
    var due = K.dueMemos(), t = K.today();
    var h = '<section class="home">';
    var st = K.data.status;
    if (!K.hasRealData()) h += '<div class="warn">実データは未取得です。表示中のものにサンプル(架空)が含まれる場合は「サンプル」と書いてあります。</div>';
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

  /* ---------- 通知・バックアップ ---------- */
  function tools() {
    var s = K.state.settings;
    var h = K.det("tool-notif", "通知（再確認日のお知らせ）", '<p class="warn">iPhoneでこのアプリを閉じていても届くかは、実機での確認が必要です。まだ確認していません（下の記録は自己申告です）。</p>' +
      "<ol><li><b>おすすめ: iPhoneの標準カレンダーに取り込む</b>（.ics）。取り込んだ予定の通知はiPhone本体が出すため、このアプリを閉じていても届く見込みです。前日18:00と当日7:30にお知らせを付けます。</li>" +
      "<li>アプリを開いている間だけ出る通知（ブラウザ通知）。ホーム画面に追加したアプリでのみ動く場合があります。</li>" +
      "<li>どちらも使えなくても、期限が来たメモは画面の上部に「期限到来／期限超過」として出ます。</li></ol>" +
      '<div class="row wrap"><button data-act="ics">再確認日を .ics で書き出す</button><button data-act="notiftest">通知のテスト</button></div>' +
      '<label>実機での確認結果（自分で記録）<select id="n-ck">' + ["未確認", "確認OK（アプリを閉じても届いた）", "確認NG（届かなかった）"].map(function (o) {
        return '<option' + (s.notifyChecked === o ? " selected" : "") + ">" + o + "</option>";
      }).join("") + '</select></label><input id="n-note" placeholder="メモ（機種・iOSのバージョンなど）" value="' + E(s.notifyNote) + '">', false, "pf");
    h += K.det("tool-backup", "バックアップと復元", '<p class="muted">データはこの端末のブラウザの中にだけあります。端末の故障や設定削除に備えて、ときどき書き出してください。最後の書き出し: ' + E(s.lastBackup || "まだありません") + "</p>" +
      '<div class="row wrap"><button data-act="backup">バックアップを書き出す</button><label class="btnlike">バックアップから復元<input id="restore-file" type="file" accept=".json,application/json" hidden></label>' +
      '<button data-act="undorestore">復元を取り消す</button></div>', false, "pf");
    h += K.det("tool-set", "表示設定", '<label class="chk"><input id="set-sample" type="checkbox"' + (s.showSample ? " checked" : "") + "> サンプル（架空のデータ）を表示する</label>", false, "pf");
    return h;
  }

  /* .ics: 再確認日（終日予定）＋ 前日18:00 / 当日7:30 のアラーム */
  K.makeIcs = function () {
    function esc(s) { return String(s || "").replace(/[\\;,]/g, function (c) { return "\\" + c; }).replace(/\r?\n/g, "\\n"); }
    var L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//kabu-memo-calendar//JP", "CALSCALE:GREGORIAN"];
    var n = 0, stamp = K.today().replace(/-/g, "") + "T000000Z";
    K.state.memos.forEach(function (m) {
      if (m.status !== "open" || !m.reviewDate) return;
      n++;
      var d = m.reviewDate.replace(/-/g, ""), nx = K.addDays(m.reviewDate, 1).replace(/-/g, "");
      L.push("BEGIN:VEVENT", "UID:" + m.id + "@kabu-memo", "DTSTAMP:" + stamp, "DTSTART;VALUE=DATE:" + d, "DTEND;VALUE=DATE:" + nx,
        "SUMMARY:" + esc("株を調べる: " + (m.name || m.code)), "DESCRIPTION:" + esc((m.checks || m.reason || "") + "\n（自分の確認日。会社の予定ではありません）"),
        "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("明日は株の確認日: " + (m.name || m.code)), "TRIGGER:-PT6H", "END:VALARM",   // 前日18:00
        "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + esc("今日は株の確認日: " + (m.name || m.code)), "TRIGGER:PT7H30M", "END:VALARM",   // 当日7:30
        "END:VEVENT");
    });
    L.push("END:VCALENDAR");
    return { text: L.join("\r\n"), count: n };
  };
})(window.KMC);
