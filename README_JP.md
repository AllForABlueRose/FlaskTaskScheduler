# FlaskTaskScheduler

Flaskで構築された軽量なローカルタスクスケジューラです。

FlaskTaskSchedulerは、ブラウザ上からPythonタスクの作成・スケジュール・実行を行えるWebアプリケーションです。クラウドサービスや外部スケジューラを使わず、ローカル環境で簡単な自動化を実現できます。

## 主な機能

- Webベースのタスク管理
- ユーザー認証と権限管理
- ドラッグ＆ドロップによる週間スケジュール
- 15分単位のスケジューリング
- バックグラウンド実行
- Pythonコード実行
- 入力パラメータ対応
- SQLiteによるローカル保存
- 実行中のスリープ防止

## 必要環境

- Python 3.10以上
- Flask
- SQLite

## インストール

```bash
git clone https://github.com/AllForABlueRose/FlaskTaskScheduler.git
cd FlaskTaskScheduler
pip install -r requirements.txt
```

## 起動方法

```bash
python app.py
```

起動後、以下へアクセス：

```text
http://localhost:5000
```

## 注意事項

- タスクは15分単位でスケジュールされます。
- スケジューラが自動で実行対象を確認します。
- タスク実行にはPythonの `exec()` を使用しています。

> 信頼できるローカル環境でのみ使用してください。

## ライセンス

MIT License
