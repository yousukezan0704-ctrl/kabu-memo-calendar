"""収集したデータ(docs/data の IR・財務・履歴)を、非公開リポジトリへ送る。
公開サイト(GitHub Pages)には載せない。iPhoneのアプリは、読み取り専用トークンでここから読む。
使い方: python tools/publish_private.py   (collect_now.bat が収集のあとで呼びます)
・コピーして上書きするだけで、非公開リポジトリのファイルは消さない。
・送るのは events/ir_index/status と financials/ history/ のみ。メモや保有銘柄(ブラウザ内)は含まれない。"""
import os
import shutil
import subprocess
import sys
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "data")
REPO_URL = "https://github.com/yousukezan0704-ctrl/kabu-memo-private-data.git"
LOCAL = os.path.join(os.path.dirname(ROOT), "kabu-memo-private-data")
FILES = ["events.json", "ir_index.json", "status.json"]
DIRS = ["financials", "history"]


def git(*args):
    r = subprocess.run(["git", "-C", LOCAL] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    if not os.path.isdir(os.path.join(LOCAL, ".git")):
        r = subprocess.run(["git", "clone", REPO_URL, LOCAL], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("クローンできませんでした:", r.stderr.strip()[:300])
            return 1
    git("pull", "--rebase", "-q")
    dst = os.path.join(LOCAL, "data")
    os.makedirs(dst, exist_ok=True)
    # 検証してから送る: 構造の問題があれば送らず、精度未確認の種類は保留にして外す
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import validate_data
    problems = validate_data.check(SRC, dst)
    if problems:
        print("検証に失敗しました。送信しません:")
        for p in problems:
            print(" -", p)
        return 1
    import tempfile
    stage = os.path.join(tempfile.mkdtemp(prefix="kmc_stage_"), "data")  # 毎回あたらしい場所(前回の残りに左右されない)
    shutil.copytree(SRC, stage, ignore=shutil.ignore_patterns("*.md"))
    held = validate_data.hold(stage)
    print("保留(精度未確認): %d 件" % held)
    SRC_USE = stage
    n = 0
    for f in FILES + ["held.json"]:
        p = os.path.join(SRC_USE, f)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(dst, f))
            n += 1
    seen = os.path.join(ROOT, "state", "seen.json")
    if os.path.isfile(seen):  # クラウド収集が続きから動けるよう、取得済みの記録も置く
        os.makedirs(os.path.join(LOCAL, "state"), exist_ok=True)
        shutil.copy2(seen, os.path.join(LOCAL, "state", "seen.json"))
    for d in DIRS:
        sd = os.path.join(SRC_USE, d)
        if os.path.isdir(sd):
            os.makedirs(os.path.join(dst, d), exist_ok=True)
            for f in os.listdir(sd):
                if f.endswith(".json"):
                    shutil.copy2(os.path.join(sd, f), os.path.join(dst, d, f))
                    n += 1
    git("add", "-A")
    code, out = git("status", "--porcelain")
    if not out.strip():
        print("変更なし（%d ファイル確認）" % n)
        return 0
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    code, out = git("commit", "-q", "-m", "data %s" % stamp)
    if code != 0:
        print("コミットに失敗:", out[:300])
        return 1
    code, out = git("push", "-q")
    if code != 0:
        print("送信に失敗:", out[:300])
        return 1
    print("非公開リポジトリへ送信しました（%d ファイル）" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
