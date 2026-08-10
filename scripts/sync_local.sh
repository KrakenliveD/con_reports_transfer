#!/usr/bin/env bash
# 從 GDrive:/sec_reports/ 同步 MD 研報副本到本地（供分析使用）
# 前置: rclone 已設定 remote（名稱可改下方 GDRIVE_REMOTE）
set -euo pipefail

GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive}"
GDRIVE_FOLDER="sec_reports"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)/reports"

mkdir -p "$LOCAL_DIR"
rclone sync "${GDRIVE_REMOTE}:${GDRIVE_FOLDER}/" "$LOCAL_DIR"
echo "✅ 已同步 ${GDRIVE_REMOTE}:${GDRIVE_FOLDER}/ → $LOCAL_DIR"
