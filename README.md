# 芸人出演情報オートカレンダー

FANYチケットを5分おきに検索し、登録した出演者の出演情報を自動でカレンダーへ反映します。
さらに「軟水」など指定した出演者の新規公演だけLINEへ通知します。

## 仕組み

FANYチケット
→ GitHub Actions（5分おきに実行）
→ 出演者名で検索
→ 公演詳細ページで出演者名を確認
→ 日付・公演名・会場・開演時刻・URLを抽出
→ data/events.jsonへ保存
→ GitHub Pagesのカレンダーが表示
→ 新規公演だけLINE Messaging APIで通知

FANYの検索ページには「出演者/公演名/会場名」の検索欄があり、検索結果には公演日、会場、出演者が掲載されています。
また公演詳細ページには日時・会場名・出演者の項目があります。

## 重要

FANYに公式APIが公開されていることを確認できていないため、この版は公開HTMLを取得して解析する方式です。
サイトのHTML構造が変更された場合はスクレイパーの修正が必要です。
アクセス頻度を5分間隔にしていますが、GitHub Actionsのscheduled workflowは実行時刻が遅延する場合があります。「必ず5分以内」を保証する仕組みではありません。

## 1. GitHubへアップロード

このフォルダをそのまま新規GitHubリポジトリへアップロードしてください。

## 2. 追跡する芸人

`config/performers.json`を編集します。

例:
- ドンデコルテ
- CITY
- 素敵じゃないか
- 軟水

`notify: true`はメモ用で、実際の通知対象は`notification.performer_ids`です。

## 3. LINE通知

LINE Notifyは2025年3月31日に終了しているため、Messaging APIを使用します。

GitHubリポジトリの Settings → Secrets and variables → Actions → New repository secret から以下を登録:

- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_TO`

LINE_CHANNEL_ACCESS_TOKEN:
LINE DevelopersでMessaging APIチャネルを作成し、チャネルアクセストークンを発行。

LINE_TO:
通知先のLINE user ID、または公式アカウントが参加しているグループのID。

自分へ送る場合は、LINE公式アカウントを友だち追加し、LINE Developersコンソールの「あなたのユーザーID」を確認する方法があります。
WebhookからuserIdを取得する方法もあります。

## 4. GitHub Pages

Settings → Pages → Deploy from a branch → main / root を選択。

公開URLの末尾を `/app/` にするとカレンダーが表示されます。
例:
https://USERNAME.github.io/REPOSITORY/app/

## 5. GitHub Actions

Actionsタブでworkflowが有効になっていることを確認。
最初は「Run workflow」で手動実行して、スクレイピング結果を確認するのがおすすめです。

## 6. ローカルテスト

Python 3.12以上:

pip install -r requirements.txt
python scraper.py

`data/events.new.json`が生成されます。

## 今後の拡張候補

- FANY以外の劇場・チケットサイト
- 出演者をWEB画面から追加できる管理画面
- 「軟水だけ」「東京だけ」などの通知条件
- LINEで「今月の軟水」と送ると一覧を返すBot
- 公演追加だけでなく出演者変更・公演中止も通知
- Supabase/FirebaseによるクラウドDB化
