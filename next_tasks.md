# 次回作業（優先順）

1. rule-v11 の再取得結果を確認（重複・needs_review件数・dividend）→ 検証担当で再測定（提携20件前後、修正の見落とし率、配当の照合）
2. dividend と XBRL配当行(xrvd)の重複整理（collect.py）
3. ui_test / iphone_check を回し、sw の版を上げ、publish_private → コミット・push
4. PER・PBR・株価の無料データ調査（調査担当）。取れない項目は「未取得」と明示
5. 自動収集の再開可否の判断（精度測定の結果＋TDnet利用条件）。再開前にユーザー承認
6. 権限設定の提案（下記）を、ユーザー承認のうえ適用

## ユーザーにお願いすること
- 公開してよいデータの範囲の決定（公開する場合のみ）
- EDINETを使う場合のみ、無料APIキー登録

## 権限の調査結果（2026-11-07）と提案（未適用・承認待ち）
- 設定の層: ①グローバル ~/.claude/settings.json（ask: 削除・移動・コピー・git push/reset/clean・Invoke-WebRequest/curl・WebFetch・Artifact・Drive・Docs。bypass/autoモードは無効化）②プロジェクト .claude/settings.json（python collector/tools/unittest、git status/diff/log/add/commit/pull --rebase、Edit/Write は許可。強制push・repo delete は deny）。
- 確認が出る主な原因: (1) `cd X && ...` や `;`/`|` でつないだ複合コマンド（部品ごとに照合され、1つでも未許可なら確認）(2) `python -c` の一行実行（許可の形に当てはまらない）(3) cat/tail/sed/printf/Select-String など未登録の読み取り系 (4) git push・コピー・通信（ask なので意図どおり確認）(5) 公開サイト確認の Invoke-WebRequest。
- 安全に減らす案（どれもプロジェクト側 .claude/settings.json の allow に追加。削除・書き込み・通信は増やさない）:
  a. 読み取り専用を追加: PowerShell(Get-Content*), (Get-ChildItem*), (Select-String*), (Test-Path*), Bash(tail*), (head*), (ls*), (wc*)。
  b. 作業ディレクトリを最初から固定し、cd を使わない（運用で対応。設定不要）。
  c. 一行Pythonは tools/ のスクリプトにして `python tools/…` で呼ぶ（運用で対応）。
  d. 既存の `python -X utf8 *` と `python -I *` は任意のコードを実行できるほど広い。将来は `python -X utf8 tools/*` に絞るのが安全（要承認）。
  e. git push（通常）の許可は、あなたが「毎回確認しなくてよい」と決めたときだけ。強制pushは今の deny を維持。
- やらないこと: bypass/auto モードの有効化、ask の全面削除。

## 旧メモ: 権限の見直し案
- 現状: プロジェクト設定でテスト・python・git add/commit/pull --rebase・Edit/Write は許可済み。git push はグローバル設定で確認が必要。
- 承認が多い原因: (a) `cd ... && ...` のような連結コマンド (b) 削除・コピー・Invoke-WebRequest・WebFetch の確認設定 (c) git push (d) 新規の python -c の一行実行
- 提案: ツールの Bash/PowerShell で cd せずに作業ディレクトリを使う、python の一行実行は tools/ 配下のスクリプトにして許可済み形式(python tools/*)で呼ぶ。git push（強制でない）の許可は、ユーザーが望むなら追加。全面解除はしない。
