/* 共通の小さな道具。画面に出す文字は必ず esc() を通す（データ由来の文字でHTMLが壊れないように）。 */
window.KMC = window.KMC || {};
(function (K) {
  K.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  K.safeUrl = function (u) {
    return /^https:\/\//i.test(u || "") ? u : "";
  };
  K.pad = function (n) { return (n < 10 ? "0" : "") + n; };
  K.ymd = function (d) { return d.getFullYear() + "-" + K.pad(d.getMonth() + 1) + "-" + K.pad(d.getDate()); };
  K.parseYmd = function (s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || "");
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  };
  K.today = function () { return K.ymd(new Date()); };
  K.addDays = function (s, n) { var d = K.parseYmd(s); d.setDate(d.getDate() + n); return K.ymd(d); };
  K.WD = ["日", "月", "火", "水", "木", "金", "土"];
  K.fmtDay = function (s) {
    var d = K.parseYmd(s);
    return d ? (d.getMonth() + 1) + "月" + d.getDate() + "日(" + K.WD[d.getDay()] + ")" : s;
  };
  K.nowStamp = function () {
    var d = new Date();
    return K.ymd(d) + " " + K.pad(d.getHours()) + ":" + K.pad(d.getMinutes()) + ":" + K.pad(d.getSeconds());
  };
  K.uid = function () { return Date.now().toString(36) + Math.random().toString(36).slice(2, 7); };
  K.debounce = function (fn, ms) {
    var t;
    return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms); };
  };
  K.download = function (name, text, mime) {
    var blob = new Blob([text], { type: mime || "application/octet-stream" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  };
  K.toast = function (msg, bad) {
    var t = document.getElementById("toast");
    if (!t) return;
    t.textContent = msg;
    t.className = "toast show" + (bad ? " bad" : "");
    clearTimeout(K._tt);
    K._tt = setTimeout(function () { t.className = "toast"; }, 3500);
  };

  /* 予定の種類: 文字(label) と 色(color) の両方で区別する */
  K.KINDS = {
    earnings:      { label: "決算",       color: "#1a56db" },
    revision_up:   { label: "上方修正",   color: "#0e7a4b" },
    revision_down: { label: "下方修正",   color: "#c0262d" },
    forecast:      { label: "予想変更",   color: "#8a5a00" },
    forecast_item: { label: "予想数値",   color: "#8a5a00" },
    fx:            { label: "為替",       color: "#007c89" },
    launch:        { label: "発売",       color: "#7a3fc4" },
    development:   { label: "開発・承認", color: "#a3369b" },
    production:    { label: "量産・設備", color: "#9a4a14" },
    alliance:      { label: "提携・受注", color: "#2b6a9e" },
    buyback:       { label: "自社株買い", color: "#4a5a6a" },
    delay:         { label: "延期・変更", color: "#b3261e" },
    mine:          { label: "自分の確認", color: "#c2410c" },
    other:         { label: "その他",     color: "#555555" }
  };
  /* 自動抽出の誤りが残りやすい種類（検証結果による） */
  K.RISKY_KINDS = { launch: 1, production: 1, fx: 1, delay: 1, alliance: 1, buyback: 1 };
  /* 折りたたみ(<details>)。開閉は K.openState に覚え、画面を描き直しても閉じない。
     sum は HTML（呼び出し側で esc 済みのこと）。def は初期状態(true=開く) */
  K.openState = {};
  K.det = function (key, sum, body, def, cls) {
    var o = Object.prototype.hasOwnProperty.call(K.openState, key) ? K.openState[key] : !!def;
    return '<details class="fold' + (cls ? " " + cls : "") + '" data-key="' + K.esc(key) + '"' + (o ? " open" : "") + "><summary>" + sum + '</summary><div class="foldbody">' + body + "</div></details>";
  };
  K.kindOf = function (k) { return K.KINDS[k] || K.KINDS.other; };
  K.ORIGIN = {
    official:  { label: "会社公表", cls: "o-official" },
    memo:      { label: "自分のメモ", cls: "o-memo" },
    inference: { label: "AI推測", cls: "o-inf" }
  };
})(window.KMC);
