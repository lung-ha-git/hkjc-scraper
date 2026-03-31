#!/bin/bash
# HKJC Docker 一鍵停止腳本
# 用途: 快速停止所有 HKJC 服務

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 腳本所在目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          HKJC Docker 服務停止腳本                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 檢查 Docker 是否運行
if ! docker info > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Docker 未運行，無需停止${NC}"
    exit 0
fi

# 檢查是否有運行中的容器
echo -e "${YELLOW}▶ 檢查運行中的服務...${NC}"
RUNNING_CONTAINERS=$(docker compose ps -q 2>/dev/null || true)

if [ -z "$RUNNING_CONTAINERS" ]; then
    echo -e "${GREEN}✓ 沒有運行中的服務${NC}"
    exit 0
fi

echo -e "${BLUE}當前運行的服務:${NC}"
docker compose ps
echo ""

# 停止服務
echo -e "${YELLOW}▶ 正在停止服務...${NC}"
docker compose down

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✓ 所有服務已停止                          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}數據已保留，下次啟動時會自動恢復${NC}"
echo -e "重新啟動: ${YELLOW}./docker/start.sh${NC}"