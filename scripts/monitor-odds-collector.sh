#!/bin/bash
#
# HKJC Odds Collector Monitor
# 獨立監控腳本 - 使用 Docker Compose 確保 odds-collector 永遠運行
#
# 使用方式：
#   ./monitor-odds-collector.sh              # 前台運行（測試用）
#   ./monitor-odds-collector.sh --daemon     # 後台守護進程
#   launchctl load ~/Library/LaunchAgents/com.fatlung.hkjc-odds-monitor.plist  # macOS 開機自啟
#

set -euo pipefail

PROJECT_DIR="/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC"
CONTAINER_NAME="hkjc-odds-collector"
CHECK_INTERVAL=30  # 每 30 秒檢查一次
LOG_DIR="/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/logs"
LOG_FILE="${LOG_DIR}/odds-monitor.log"

# 確保日誌目錄存在
mkdir -p "${LOG_DIR}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

check_and_restart() {
    local status
    local started_at
    
    # 檢查容器狀態
    status=$(docker inspect --format '{{.State.Status}}' "${CONTAINER_NAME}" 2>/dev/null || echo "not_found")
    started_at=$(docker inspect --format '{{.State.StartedAt}}' "${CONTAINER_NAME}" 2>/dev/null || echo "unknown")
    
    case "${status}" in
        running)
            log "✅ ${CONTAINER_NAME} is running (started: ${started_at})"
            return 0
            ;;
        exited|dead|created|restarting|paused)
            log "⚠️ ${CONTAINER_NAME} is ${status}, restarting..."
            log "   Attempting docker compose restart..."
            
            if cd "${PROJECT_DIR}" && docker compose restart odds-collector 2>&1 | tee -a "${LOG_FILE}"; then
                sleep 5
                local new_status
                new_status=$(docker inspect --format '{{.State.Status}}' "${CONTAINER_NAME}" 2>/dev/null || echo "unknown")
                if [ "${new_status}" = "running" ]; then
                    log "✅ ${CONTAINER_NAME} restarted successfully"
                    return 0
                else
                    log "❌ Failed to restart ${CONTAINER_NAME}, current status: ${new_status}"
                    return 1
                fi
            else
                log "❌ Docker compose restart failed"
                return 1
            fi
            ;;
        not_found)
            log "⚠️ ${CONTAINER_NAME} not found, creating..."
            if cd "${PROJECT_DIR}" && docker compose up -d odds-collector 2>&1 | tee -a "${LOG_FILE}"; then
                sleep 5
                log "✅ ${CONTAINER_NAME} created and started"
                return 0
            else
                log "❌ Failed to create ${CONTAINER_NAME}"
                return 1
            fi
            ;;
        *)
            log "⚠️ Unknown status '${status}', attempting restart..."
            cd "${PROJECT_DIR}" && docker compose restart odds-collector 2>&1 | tee -a "${LOG_FILE}"
            ;;
    esac
}

daemon_mode() {
    log "========================================="
    log "HKJC Odds Collector Monitor Started"
    log "Container: ${CONTAINER_NAME}"
    log "Check Interval: ${CHECK_INTERVAL}s"
    log "Log: ${LOG_FILE}"
    log "========================================="
    
    while true; do
        check_and_restart
        sleep "${CHECK_INTERVAL}"
    done
}

case "${1:-}" in
    --daemon|-d)
        daemon_mode
        ;;
    --once)
        check_and_restart
        ;;
    *)
        echo "HKJC Odds Collector Monitor"
        echo ""
        echo "Usage: $0 [OPTION]"
        echo ""
        echo "Options:"
        echo "  (none)     Run once and exit"
        echo "  --daemon    Run continuously as daemon"
        echo "  --once      Run health check once and exit"
        echo ""
        echo "For macOS auto-start, load with:"
        echo "  launchctl load ~/Library/LaunchAgents/com.fatlung.hkjc-odds-monitor.plist"
        echo ""
        echo "Current status:"
        docker inspect --format '{{.State.Status}} ({{.State.StartedAt}})' "${CONTAINER_NAME}" 2>/dev/null || echo "Container not found"
        ;;
esac
