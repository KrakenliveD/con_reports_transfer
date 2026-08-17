#!/usr/bin/env python3
"""
上傳 reports/*.md 到 GDrive:/sec_reports/

使用 Google Service Account 認證。
Service Account JSON key 透過環境變數 GDRIVE_CREDENTIALS 傳入。

用法:
  export GDRIVE_CREDENTIALS='{...json...}'
  python scripts/upload_gdrive.py

依賴: google-api-python-client google-auth（按需安裝）
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"

GDRIVE_FOLDER_NAME = os.environ.get("GDRIVE_FOLDER_NAME", "sec_reports")
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "")


GDRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def get_service():
    creds_json = os.environ.get("GDRIVE_CREDENTIALS", "")
    if not creds_json:
        print("⚠️  環境變數 GDRIVE_CREDENTIALS 為空，跳過 GDrive 上傳。",
              file=sys.stderr)
        return None
    try:
        from googleapiclient.discovery import build

        info = json.loads(creds_json)
        if info.get("type") == "service_account":
            # Service Account：適用於 Google Workspace + Shared Drive
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_info(
                info, scopes=[GDRIVE_SCOPE]
            )
        else:
            # OAuth authorized_user（Desktop Client + 個人 Google 帳號，免費 15GB 配額）
            from google.oauth2 import credentials as oauth_creds

            creds = oauth_creds.Credentials.from_authorized_user_info(
                info, scopes=[GDRIVE_SCOPE]
            )
        return build("drive", "v3", credentials=creds)
    except ImportError:
        print("⚠️  缺少 google-api-python-client / google-auth。"
              "運行: pip install google-api-python-client google-auth",
              file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  GDrive 認證失敗: {e}", file=sys.stderr)
        return None


def get_or_create_folder(service, folder_name: str, parent_id: str = None) -> str:
    query = (
        f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
        " and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        file_metadata["parents"] = [parent_id]
    folder = service.files().create(body=file_metadata, fields="id").execute()
    print(f"  📁 建立 GDrive 資料夾: {folder_name} ({folder['id']})",
          file=sys.stderr)
    return folder["id"]


def list_existing_files(service, folder_id: str) -> set:
    """列出資料夾內全部文件（分頁翻頁，避免 pageSize=1000 上限漏列）。"""
    names = set()
    page_token = None
    while True:
        results = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(name), nextPageToken",
                pageSize=1000,
                pageToken=page_token,
            )
            .execute()
        )
        names.update(f["name"] for f in results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    return names


def upload_file(service, file_path: Path, folder_id: str):
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(file_path), mimetype="text/markdown")
    file_metadata = {"name": file_path.name, "parents": [folder_id]}
    uploaded = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, name")
        .execute()
    )
    return uploaded


def main():
    if not REPORTS_DIR.exists():
        print("ℹ️  reports/ 目錄不存在，無檔案需上傳。", file=sys.stderr)
        return

    md_files = sorted(REPORTS_DIR.glob("*.md"))
    if not md_files:
        print("ℹ️  reports/ 中沒有 .md 檔案需上傳。", file=sys.stderr)
        return

    service = get_service()
    if service is None:
        print("💡 跳過 GDrive 上傳。可稍後設定 GDRIVE_CREDENTIALS 後重試。",
              file=sys.stderr)
        return

    folder_id = GDRIVE_FOLDER_ID or get_or_create_folder(service, GDRIVE_FOLDER_NAME)
    existing = list_existing_files(service, folder_id)
    print(f"  📋 GDrive {GDRIVE_FOLDER_NAME} 已有: {len(existing)} 個 .md",
          file=sys.stderr)

    to_upload = [f for f in md_files if f.name not in existing]
    print(f"  📤 需上傳: {len(to_upload)} 個", file=sys.stderr)
    if not to_upload:
        print("✅ 全部已同步，無需上傳。", file=sys.stderr)
        return

    success, failed = 0, []
    for f in to_upload:
        try:
            uploaded = upload_file(service, f, folder_id)
            print(f"  ✅ {f.name} → ({uploaded['id']})", file=sys.stderr)
            success += 1
        except Exception as e:
            print(f"  ❌ {f.name}: {e}", file=sys.stderr)
            failed.append(f.name)

    print(f"\n{'=' * 40}", file=sys.stderr)
    print(f"✅ 上傳成功: {success}", file=sys.stderr)
    if failed:
        print(f"❌ 上傳失敗: {len(failed)}", file=sys.stderr)
        for name in failed:
            print(f"   - {name}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
