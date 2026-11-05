"""iPhone(Safari/WebKit)相当で、PCのデータ配信から財務表示まで通るかを確認する。
使い方: python tools/iphone_check.py   (docs/data にデータがある状態で)
実機ではありません。WebKit(Safariと同じ描画エンジン)のiPhone風画面での確認です。"""
import functools
import http.server
import os
import sys
import threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = sys.argv[1] if len(sys.argv) > 1 else "2003"


def main():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.join(ROOT, "docs"))
    h.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8771), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    res, errs = [], []
    with sync_playwright() as p:
        dev = p.devices["iPhone 13"]
        b = p.webkit.launch()
        ctx = b.new_context(**dev)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8771/index.html")
        pg.wait_for_timeout(1500)
        pg.evaluate("""(c)=>{var a=document.createElement('a');a.dataset.act='stock';a.dataset.code=c;a.href='#';document.body.appendChild(a);a.click();}""", CODE)
        pg.wait_for_timeout(2000)
        t = pg.inner_text("body")
        res.append(("財務の見出し", "最新の決算と前年同期比" in t))
        res.append(("売上高の表示", "売上高" in t))
        res.append(("未取得でない", "財務データ未取得" not in t))
        res.append(("横スクロールなし", pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")))
        shot = os.path.join(os.environ.get("TEMP", "."), "iphone_check_%s.png" % CODE)
        pg.screenshot(path=shot, full_page=False)
        b.close()
    ok = all(v for _, v in res) and not errs
    for k, v in res:
        print(("OK   " if v else "NG   ") + k)
    print("ページエラー:", errs)
    print("画面写真:", shot)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
