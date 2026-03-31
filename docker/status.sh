#!/bin/bash
# HKJC Docker 狀態查看腳本
# 用途: 查看所有服務運行狀態

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
echo -e "${BLUE}║          HKJC 服務狀態                                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 檢查 Docker 是否運行
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}✗ Docker 未運行${NC}"
    exit 1
fi

# 顯示容器狀態
echo -e "${YELLOW}容器狀態:${NC}"
docker compose ps

echo ""

# 檢查各服務健康狀態
echo -e "${YELLOW}健康檢查:${NC}"

# 檢查 Web
curl -s http://localhost > /dev/null 2>&1 && echo -e "  🌐 Web:    ${GREEN}✓ 正常${NC}" || echo -e "  🌐 Web:    ${RED}✗ 無法訪問${NC}"

# 檢查 API
curl -s http://localhost:3001/health > /dev/null 2>&1 && echo -e "  🔌 API:    ${GREEN}✓ 正常${NC}" || echo -e "  🔌 API:    ${RED}✗ 無法訪問${NC}"

# 檢查 MongoDB
docker compose exec -T mongodb mongosh --eval "db.adminCommand('ping')" > /dev/null 2>&1 && echo -e "  🗄️  MongoDB: ${GREEN}✓ 正常${NC}" || echo -e "  🗄️  MongoDB: ${RED}✗ 無法連接${NC}"

echo ""

# 顯示資源使用情況
echo -e "${YELLOW}資源使用:${NC}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.Status}}" 2>/dev/null | grep -E "(NAME|hkjc)" || echo "  暫無數據"

echo ""
echo -e "${BLUE}提示: 使用 ./docker/logs.sh 查看詳細日誌${NC}"