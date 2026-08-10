# con_reports_transfer — 券商研報全雲端 PDF→MD 傳輸管線

從東方財富每日抓取行業研報，下載 PDF、純文字轉 Markdown，上傳 Google Drive。
**全雲端運行**（GitHub Actions），每日定時，免費資源串接，本機零操作。

```
GitHub Actions (每日 cron, 公開倉庫免費)
  → fetch_reports.py  東財列表 API (qType=1 行業研報, 排除定期彙報/非券商)
  → convert_pdf.py    下載 PDF → pymupdf 純文字 → reports/*.md
  → upload_gdrive.py  上傳 GDrive:/sec_reports/（平鋪）
  → commit manifest   更新去重清單（pending/downloaded.json）

本機（可選）
  → scripts/sync_local.sh  rclone sync 拉取 MD 副本
```

---

## 一、架構

| 環節 | 工具 |
|------|------|
| 排程 | GitHub Actions `schedule`（每日 UTC 22:00 = 北京 06:00）+ 手動觸發 |
| 資料源 | 東方財富 `reportapi.eastmoney.com/report/list`（`qType=1` 行業研報） |
| PDF 下載 | `pdf.dfcfw.com/pdf/H3_{infoCode}_1.pdf` |
| PDF→MD | pymupdf 純文字提取（無 LLM） |
| 去重 | `manifest/downloaded.json` 累積 infoCode，跨日不重複下載 |
| 儲存 | Google Drive `/sec_reports/`（SA 自動建資料夾） |
| 交付 | GDrive（雲端主儲存）+ 本機 rclone 同步副本 |

### 目錄結構

```
.
├── .github/workflows/daily.yml   # 每日 cron + 手動觸發
├── scripts/
│   ├── fetch_reports.py          # 抓東財清單 → pending.json
│   ├── convert_pdf.py            # 下載+轉MD+去重
│   ├── upload_gdrive.py          # 上傳 GDrive
│   └── sync_local.sh             # 本機 rclone 拉取
├── manifest/
│   ├── pending.json              # 本次待處理清單（每次運行重寫）
│   └── downloaded.json           # 已下載 infoCode（累積）
└── reports/                      # MD 產出（gitignored，rclone 目標）
```

---

## 二、一次性設定

### 1. GitHub Secrets：`GDRIVE_CREDENTIALS`

產生 Google Service Account JSON：

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 新建專案（或選既有專案）
3. 左側 **APIs & Services → Library** → 啟用 **Google Drive API**
4. **APIs & Services → Credentials → Create Credentials → Service Account**
5. 建立後在該 SA 右側 **⋮ → Manage keys → Add Key → Create new key → JSON** → 下載 JSON 檔
6. 開啟該 JSON 檔，複製**完整內容**
7. 到 GitHub 倉庫 **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `GDRIVE_CREDENTIALS`
   - Secret: 貼上完整 JSON
8. 首次運行時 `upload_gdrive.py` 會用 SA 自動建立 `sec_reports` 資料夾（SA 自建自管，無需手動共享）

> SA 產生的資料夾歸 SA 所有，你個人帳號的 GDrive 可能看不到。如需可見：
> 建好後用該 SA 的 email（`{name}@{project}.iam.gserviceaccount.com`）把資料夾共享給你個人帳號，或改用 OAuth Client ID + 個人帳號授權（進階選項）。

### 2. （選用）本機 rclone 同步

```bash
# 若無 rclone remote，先設定（rclone config → New remote → type: drive）
rclone config

# 下載本地副本
GDRIVE_REMOTE=gdrive ./scripts/sync_local.sh
```

### 3. （選用）本機開發測試

```bash
cd /home/lavik/project/con_reports_transfer
uv venv && source .venv/bin/activate && uv pip install pymupdf requests

# 小批量冒煙
python scripts/fetch_reports.py --days 1 --limit 3
python scripts/convert_pdf.py
```

---

## 三、運作說明

- **排程**：每日 UTC 22:00（北京 06:00）掃描前一日研報；窗口 `--days 7` 涵蓋週末/假期
- **排除**：標題含「周報/月報/日報/行業跟踪/季度」等定期彙報 → 不轉檔；非券商源（諮詢公司等）過濾
- **去重**：`downloaded.json` 記錄已處理 infoCode；跨日重跑自動跳過
- **手動觸發**：GitHub Actions 頁面 → Run workflow，可帶 `days` 參數
- **md 檔頭**：保留 metadata（title/infoCode/行業/券商/日期/PDF連結）供未來溯源

## 四、已知限制

- 東財 API 為公開介面，可能變動；變動時更新 `scripts/fetch_reports.py`
- 單次運行下載全量非定期研報（視窗口 ~數十至百篇），公開倉庫 Actions 免費額度充足
- GitHub Actions 排程要求倉庫每 60 天有活動；本管線每日自動 commit，自動保持活躍
