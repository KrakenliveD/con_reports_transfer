# AGENTS.md

券商研报全云端传输管线：每日 cron（GitHub Actions）抓研报清单 → 下载 PDF → pymupdf 转 Markdown → 上传 GDrive `/sec_reports/` → commit manifest。本机零操作。

## 安全守则（最高优先）

- **任何数据源网址一律不得写入 repo**。所有端点/模板通过 `.env`（本机）或 GitHub Secrets（云端）注入：
  `REPORT_API_BASE`、`PDF_URL_TEMPLATE`（含 `{infoCode}` 占位）、`DOWNLOAD_REFERER`（选用）、`GDRIVE_CREDENTIALS`（OAuth authorized_user JSON）。
- 本机 `.env` 已存在（gitignored），是唯一数据来源；代码只用 scripts/config.py 的 `get/require` 读取。

## 管线与执行

依赖顺序：`fetch_reports.py`（→ `manifest/pending.json`）→ `convert_pdf.py`（→ `reports/*.md`，更新 `downloaded.json`）→ `upload_gdrive.py`（→ GDrive）。多步骤操作务须依此顺序。

- 一律从 repo 根目录执行 `python scripts/<name>.py`（不是套件，config.py 在同一目录）。
- 无 requirements/lockfile；依赖须自行安装。本机：`uv venv && uv pip install pymupdf requests`；CI 用 `pip install pymupdf requests google-api-python-client google-auth`（Python 3.11）。
- 冒烟测试（需先设好 `.env`）：
  ```
  python scripts/fetch_reports.py --days 1 --limit 3
  python scripts/convert_pdf.py
  ```
- `--days` 预设 7（涵盖周末/假期）；`--limit N` 截断冒烟用。

## 状态文件与去重（易搞错）

- `pending.json`：每次 fetch 重写。
- `downloaded.json`：累积去重 store，跨日跳过已下载；**勿删**，删了会全量重载。
- `reports/` 与 `.env` 皆 gitignored → 报告只经 GDrive 交付。
- `manifest/` 由 workflow bot 提交进 repo；`GDRIVE_CREDENTIALS` 未设定时 upload 自动跳过（非错误）。

## 运作细节

- workflow 需 `concurrency: report-transfer`（防止并行修改 `downloaded.json`）+ `permissions: contents: write`（bot commit manifest）。
- PDF 下载网址附加 `?{unix_ms}.pdf` cache-bust；非 `application/pdf` 回应即 raise。
- 文件名 `{infoCode}_{title}.md`（title 清特殊字符、截断 40 字符）＝GDrive 文件名。
- GDrive 端以文件名去重（`list pageSize=1000` → 2026-08-17 已改分页翻页）；文件夹自动创建。上传用 OAuth 个人账号（authorized_user，邮箱与凭据见本地 PROGRESS.md）；勿改回 SA（SA 无存储配额，上传必失败）。
- 用 `import pymupdf`（新 API），勿用旧 `fitz`。logs 走 stderr；任一失败则 exit 1。
- **排除词表与非券商清单必须用简体字**（东财 API 标题/机构名为简体；2026-08-17 前用繁体词表导致 47% 定期汇报 + 全部非券商漏网）。改词表时务必跑 `python -m unittest discover -s tests`。
- convert 单篇失败不再 exit 1（2026-08-17）：部分成功照常上传，失败篇留待下轮重试。
- 注释/输出用简体中文，新代码保持一致。