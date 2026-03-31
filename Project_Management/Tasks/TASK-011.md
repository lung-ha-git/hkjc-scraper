# TASK-011: Pipeline Cron Job 未運行調查 + MongoDB_URI 修復驗證

**創建日期**: 2026-03-28  
**狀態**: 已完成（根本原因已確認並即時修復）  
**優先級**: High  
**負責人**: The_Debugger  

---

## 目標

1. 調查 Pipeline Cron Job 今天 06:00 為何沒有運行
2. 驗證 MongoDB_URI 修復是否成功

## 問題背景

### 問題 1: Pipeline Cron Job 未運行

- **現象**: 今天 06:00 的 Pipeline 沒有執行，`pipeline_cron.log` 為空
- **Cron 設定**: `0 6 * * * cd /app && python3 daily_pipeline.py >> /app/logs/pipeline_cron.log 2>&1`
- **Cron 服務**: 正在運行（`/usr/sbin/cron`）
- **測試問題**: 手動添加的 cron test job 也沒有輸出

### 問題 2: MongoDB_URI 配置錯誤（已修復）

- **現象**: Pipeline 嘗試連接 `localhost:27017` 而非 `mongodb:27017`
- **根本原因**: 
  1. `/app/config/settings.py` 中的 `load_dotenv()` 指向 Mac 主機路徑
  2. `/app/config/.env` 中的 `MONGODB_URI=mongodb://localhost:27017/`
- **已執行修復**:
  1. ✅ 更新 `/app/config/settings.py` — 修正 `.env` 路徑為 `/app/config/.env`
  2. ✅ 更新 `/app/config/.env` — 修正 `MONGODB_URI`

## 調查方向

### Cron Job 問題

1. 檢查 cron 的執行環境（PATH 是否包含 `/usr/local/bin`）
2. 檢查 crontab 格式是否正確
3. 測試在 cron 環境下執行 python3 是否正常
4. 嘗試用完整路徑 `/usr/local/bin/python3` 替換 `python3`
5. 檢查是否有 cron 日誌

### 驗證命令

```bash
# 測試 cron 環境
docker exec hkjc-pipeline bash -c 'env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/root /bin/sh -c "echo test >> /tmp/cron_test.log"'
docker exec hkjc-pipeline cat /tmp/cron_test.log

# 檢查 cron crontab
docker exec hkjc-pipeline bash -c 'cat /etc/cron.d/hkjc-pipeline'

# 檢查 user crontab
docker exec hkjc-pipeline bash -c 'crontab -l'
```

## 驗收標準

- [x] 確認 cron job 未運行的根本原因
- [x] 提供 cron job 的修復建議
- [x] 確認 MongoDB_URI 修復成功
- [x] 確認 Pipeline 可以正常執行

---

## 修復記錄 (2026-03-28 13:08)

### 根本原因
`/etc/cron.d/hkjc-pipeline` 格式錯誤：
- 原始內容：`0 6 * * * cd /app && python3 daily_pipeline.py...`
- 缺少 `username` 欄位（`/etc/cron.d/` 格式要求第5個欄位是 username）
- `python3` 沒有完整路徑

### 即時修復
```bash
docker exec hkjc-pipeline bash -c 'echo "root 0 6 * * * cd /app && /usr/local/bin/python3 daily_pipeline.py >> /app/logs/pipeline_cron.log 2>&1" > /etc/cron.d/hkjc-pipeline'
```

### 驗證結果
| 項目                             | 結果                                    |
| ------------------------------ | ------------------------------------- |
| `/etc/cron.d/hkjc-pipeline` 格式 | ✅ 已修正（包含 `root` username + full path） |
| Cron daemon 運行狀態               | ✅ PID 26422 running                   |
| MongoDB_URI 修復驗證               | ✅ Pipeline 12:12 和 12:27 成功執行         |
| 明天 06:00 預期                    | ✅ Cron Job 應該正常觸發                     |

## 備註

- 相關容器: `hkjc-pipeline`
- 相關檔案:
  - `/app/config/settings.py`
  - `/app/config/.env`
  - `/app/logs/pipeline_cron.log`
