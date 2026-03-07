# Sagami-YouTube-Downloader

## 使い方

1. `Sagami Youtube Downloader.exe` を実行

2. YouTube URL を入力  
3. 保存先フォルダを選択  
4. 必要に応じて「時間指定」に `開始~終了` を入力（例: `0:00~0:15`）  
5. 「詳細設定」で以下を設定  
   - 出力形式（`MP4 / MP3 / WAV / M4A`）  
   - ファイル名テンプレート  
   - サムネイル埋め込み（MP4のみ）  
6. メイン画面で品質を設定  
   - `MP4` のとき: 画質 / FPS  
   - `MP3 / WAV / M4A` のとき: 音質  
7. 「ダウンロードを開始」をクリック

- ダウンロード中はボタンのテキストが「ダウンロード中…」に変化  
- 完了すると通知メッセージが表示されます

## 更新確認

- 起動時にアプリ更新を自動確認します（最新版の場合は通知しません）  
- 手動で確認する場合は「アプリ更新を確認」をクリック  
- 更新に失敗した場合は、`logs` フォルダに `txt（ini形式）` のログが出力されます

## ログ出力

- エラー時は `logs` フォルダに `txt（ini形式）` のログを出力します  
- 例: `download_error_YYYYMMDD_HHMMSS.txt`, `update_error_YYYYMMDD_HHMMSS.txt`

## ビルド方法（Nuitka）
Nuitkaでビルドするのを推奨します

### 事前準備
- Python 3.13
- `pip install -r requirements.txt`
- `pip install nuitka`
- Visual Studio C++ Build Tools（MSVC）

### Sagami Youtube Downloader.exeをビルド
```powershell
python -m nuitka --standalone --enable-plugin=pyqt6 --windows-console-mode=disable --windows-icon-from-ico=".\\Sagami Youtube Downloader.ico" --output-dir=nuitka_dist --output-filename="Sagami Youtube Downloader.exe" --include-data-file=assets/app_icon.png=app_icon.png --include-data-file=yt-dlp.exe=yt-dlp.exe --include-data-file=config.json=config.json main.py
```

### Sagami Youtube Updater.exeをビルド
```powershell
python -m nuitka --standalone --windows-console-mode=disable --windows-icon-from-ico=".\\Sagami Youtube Downloader.ico" --output-dir=nuitka_dist --output-filename="Sagami Youtube Updater.exe" update.py
```

### 配布用フォルダへまとめる（任意）
```powershell
$pkg = "nuitka_dist\\Sagami Youtube Nuitka Package"; New-Item -ItemType Directory -Force -Path $pkg | Out-Null; Copy-Item -Path "nuitka_dist\\main.dist\\*" -Destination $pkg -Recurse -Force; Copy-Item -Path "nuitka_dist\\update.dist\\Sagami Youtube Updater.exe" -Destination $pkg -Force
```
