/* 自分のデータの保存。入力のたびに自動保存し、保存状態を画面に出す。
   保存先はこの端末のブラウザ内(localStorage)。書けなかった場合は赤い警告を出す。 */
(function (K) {
  var KEY = "kmc.v1";
  var PREV = "kmc.v1.before-restore";
  var empty = function () {
    return {
      version: 1, memos: [], userEvents: [], favorites: [], checked: {}, themeStocks: [],
      prices: {}, splits: {}, priceMeta: {}, breaking: [],
      settings: { showSample: true, notifyChecked: "未確認", notifyNote: "" },
      savedAt: null
    };
  };
  K.state = empty();
  K.saveStatus = { kind: "idle", text: "未保存の変更はありません", at: null };

  function setStatus(kind, text) {
    K.saveStatus = { kind: kind, text: text, at: K.nowStamp() };
    var el = document.getElementById("savestate");
    if (el) { el.className = "savestate " + kind; el.textContent = text; }
  }

  K.load = function () {
    try {
      var raw = localStorage.getItem(KEY);
      if (raw) {
        var obj = JSON.parse(raw);
        K.state = Object.assign(empty(), obj);
        K.state.settings = Object.assign(empty().settings, obj.settings || {});
        setStatus("ok", "前回の保存を読み込みました " + (K.state.savedAt || ""));
      }
    } catch (e) {
      setStatus("bad", "保存データを読めませんでした。バックアップから復元してください");
    }
  };

  var doSave = function () {
    try {
      K.state.savedAt = K.nowStamp();
      localStorage.setItem(KEY, JSON.stringify(K.state));
      setStatus("ok", "保存済み " + K.state.savedAt.slice(11));
      return true;
    } catch (e) {
      setStatus("bad", "保存できませんでした（容量不足またはブラウザの設定）。「メモ」→バックアップで書き出してください");
      return false;
    }
  };
  var deferred = K.debounce(doSave, 400);
  K.save = function () { setStatus("saving", "保存中…"); deferred(); };
  K.saveNow = doSave;

  /* ---- バックアップ／復元 ---- */
  K.exportBackup = function () {
    var out = JSON.stringify({ app: "kabu-memo-calendar", exportedAt: K.nowStamp(), data: K.state }, null, 1);
    K.download("株メモ_バックアップ_" + K.today() + ".json", out, "application/json");
    K.state.settings.lastBackup = K.nowStamp();
    K.save();
  };
  K.validateBackup = function (text) {
    var o;
    try { o = JSON.parse(text); } catch (e) { return { ok: false, msg: "JSONとして読めません" }; }
    if (!o || o.app !== "kabu-memo-calendar" || !o.data) return { ok: false, msg: "このアプリのバックアップではありません" };
    var d = o.data;
    if (!Array.isArray(d.memos) || !Array.isArray(d.userEvents)) return { ok: false, msg: "データの形が正しくありません" };
    return { ok: true, data: d, exportedAt: o.exportedAt };
  };
  K.restoreBackup = function (d) {
    try { localStorage.setItem(PREV, JSON.stringify(K.state)); } catch (e) { /* 退避に失敗しても復元は続ける */ }
    K.state = Object.assign(empty(), d);
    K.state.settings = Object.assign(empty().settings, d.settings || {});
    return doSave();
  };
  K.undoRestore = function () {
    try {
      var raw = localStorage.getItem(PREV);
      if (!raw) return false;
      K.state = Object.assign(empty(), JSON.parse(raw));
      return doSave();
    } catch (e) { return false; }
  };

  /* ---- よく使う更新 ---- */
  K.memoByCode = function (code) { return K.state.memos.filter(function (m) { return m.code === code; }); };
  K.isFav = function (code) { return K.state.favorites.indexOf(code) >= 0; };
  K.toggleFav = function (code) {
    var i = K.state.favorites.indexOf(code);
    if (i >= 0) K.state.favorites.splice(i, 1); else K.state.favorites.push(code);
    K.save();
  };
  K.newMemo = function (p) {
    var m = Object.assign({
      id: K.uid(), code: "", name: "", reason: "", checks: "", irUrl: "", irTitle: "",
      reviewDate: "", status: "open", dropReason: "", endCondition: "", doneNote: "",
      createdAt: K.nowStamp(), updatedAt: K.nowStamp()
    }, p || {});
    K.state.memos.unshift(m);
    K.save();
    return m;
  };
  /* 少ない操作で再確認日を決める */
  K.quickDate = function (kind) {
    var t = K.today();
    var d = K.parseYmd(t);
    if (kind === "tomorrow") return K.addDays(t, 1);
    if (kind === "nextweek") {   // 次の月曜
      var add = (8 - d.getDay()) % 7 || 7;
      return K.addDays(t, add);
    }
    if (kind === "week") return K.addDays(t, 7);
    if (kind === "month") return K.addDays(t, 30);
    return t;
  };
  /* ホーム用: 期限が来た／過ぎた確認 */
  K.dueMemos = function () {
    var t = K.today();
    return K.state.memos.filter(function (m) { return m.status === "open" && m.reviewDate && m.reviewDate <= t; })
      .sort(function (a, b) { return a.reviewDate < b.reviewDate ? -1 : 1; });
  };
})(window.KMC);
