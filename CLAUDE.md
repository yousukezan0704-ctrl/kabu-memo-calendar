# 株メモカレンダー（株IRカレンダー）恒久ルール

次のセッションは、まずこの順に読む: CLAUDE.md → progress.md → next_tasks.md → checks.md（必要なら plan.md、引き継ぎ.md）。

## 目的
日本株のIR・決算を自動収集し、iPhoneのホーム画面から使える個人用アプリ（PWA）。日常利用はiPhoneのみ。PCは開発・管理用。
ユーザーは初心者。返答は日本語（です・ます）、専門用語はかみくだき、最後に「今回覚えておくとよいこと」を付ける。Windows/PowerShell前提。

## 恒久ルール
- 無料のみ・カード登録なし。課金が出る操作は事前確認。
- 取得できない情報は推測で補わない。情報源・取得日時・欠損を明示する。誤判定の恐れがあるものは「要確認」で、確定表示しない。
- TDnet由来データ（docs/data/*, state/, 検証レポート.md）は git に入れず公開サイトに出さない。公開範囲の変更は必ず事前確認（利用条件が未確認。調査/TDnet利用条件の公式確認.md）。
- 自動収集（GitHub Actions）は、精度検証の完了と利用条件の確認まで停止を維持。公開前は tools/validate_data.py を必ず通す。
- 既存データ・GitHub履歴を削除しない。秘密情報（トークン等）をチャット・コード・ログに出さない。
- 画面を変えたら docs/sw.js の CACHE 版番号を上げる。
- 同じファイルを複数の担当が同時に編集しない。

## 担当の分け方（必要なときだけサブエージェント）
- 抽出担当: collector/extract.py, dates_jp.py, tests/test_all.py
- 財務担当: collector/financials.py, tests/test_financials.py
- 画面担当: docs/index.html, style.css, js/*, tools/ui_test.py
- 検証担当: 検証レポート.md のみ（照合・精度測定）
- 調査担当: 調査/ のみ
- 主任（メインのAI）: collect.py, docs/data, state, sw.js, bat/tools, 記録、コミット

## 実行
- テスト: `cd collector/tests; python -m unittest test_all test_financials test_collect test_validate test_export`
- 画面テスト: `python -X utf8 tools/ui_test.py` / iPhone相当: `python -X utf8 tools/iphone_check.py`
- 収集: `python collector/collect.py --days 1 --budget 600 ...` → `python tools/publish_private.py`（検証ゲート付き）

## 自律ループ
優先タスク選択→完了条件→実装→テスト→失敗原因→修正→再テスト→記録(progress.md)→次へ。同じ問題の修正が3回失敗したら原因を記録して別の安全な作業へ。
承認が必要: 本番データ削除、破壊的変更、課金、公開・公開範囲変更、認証・秘密情報の変更、大量削除、重要なセキュリティ変更。
