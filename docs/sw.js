// 画面のファイルだけを端末に保存して、オフラインでも開けるようにする。
// data/ 以下(収集データ)は常に最新を取りに行き、失敗したときだけ保存分を使う。
const CACHE = "kmc-shell-v8";
const SHELL = ["./", "index.html", "style.css", "manifest.webmanifest", "js/util.js", "js/store.js", "js/data.js", "js/prices.js", "js/cal.js", "js/ir.js", "js/stocks.js", "js/memo.js", "js/main.js"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin) return;
  if (u.pathname.includes("/data/")) {
    e.respondWith(fetch(e.request).then((r) => { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, cp)); return r; }).catch(() => caches.match(e.request)));
  } else {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request, { ignoreSearch: true })));
  }
});
