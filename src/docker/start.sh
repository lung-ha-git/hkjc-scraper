#!/bin/bash
# HKJC Docker 一鍵啟動腳本
# 用途: 快速啟動所有 HKJC 服務

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
echo -e "${BLUE}║          HKJC Docker 服務啟動腳本                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 檢查 Docker 是否運行
echo -e "${YELLOW}▶ 檢查 Docker 狀態...${NC}"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}✗ Docker 未運行${NC}"
    echo "正在啟動 Docker Desktop..."
    open -a Docker
    
    # 等待 Docker 啟動
    echo -n "等待 Docker 啟動"
    for i in {1..30}; do
        if docker info > /dev/null 2>&1; then
            echo -e "\n${GREEN}✓ Docker 已就緒${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
    
    if ! docker info > /dev/null 2>&1; then
        echo -e "\n${RED}✗ Docker 啟動超時，請手動啟動 Docker Desktop${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Docker 運行中${NC}"
fi

# 檢查 .env 文件
echo -e "${YELLOW}▶ 檢查環境配置...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}✗ .env 文件不存在${NC}"
    echo "正在從模板創建..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}⚠ 請編輯 .env 文件設置密碼後重新運行${NC}"
        echo "命令: nano .env"
        exit 1
    else
        echo -e "${RED}✗ .env.example 也不存在，請檢查項目完整性${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ 環境配置已就緒${NC}"
fi

# 檢查是否需要構建
echo -e "${YELLOW}▶ 檢查鏡像狀態...${NC}"
NEED_BUILD=false

if ! docker image inspect hkjc-web:latest > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Web 鏡像不存在，需要構建${NC}"
    NEED_BUILD=true
fi

if ! docker image inspect hkjc-api:latest > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ API 鏡像不存在，需要構建${NC}"
    NEED_BUILD=true
fi

if [ "$NEED_BUILD" = true ]; then
    echo -e "${YELLOW}▶ 構建 Docker 鏡像...${NC}"
    echo "這可能需要 5-10 分鐘，請耐心等待..."
    docker compose build --no-cache
    echo -e "${GREEN}✓ 鏡像構建完成${NC}"
else
    echo -e "${GREEN}✓ 所有鏡像已就緒${NC}"
fi

# 啟動服務
echo -e "${YELLOW}▶ 啟動服務...${NC}"
docker compose up -d mongodb api web

# 等待服務就緒
echo -n "等待服務啟動"
for i in {1..30}; do
    if curl -s http://localhost:3001/health > /dev/null 2>&1; then
        echo -e "\n${GREEN}✓ API 服務已就緒${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ✓ 所有服務已成功啟動!                      ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}訪問地址:${NC}"
echo -e "  🌐 Web 應用:  ${GREEN}http://localhost${NC}"
echo -e "  🔌 API 端點:  ${GREEN}http://localhost:3001${NC}"
echo -e "  💓 健康檢查:  ${GREEN}http://localhost:3001/health${NC}"
echo ""
echo -e "${BLUE}常用命令:${NC}"
echo -e "  停止服務:     ${YELLOW}./docker/stop.sh${NC}"
echo -e "  查看狀態:     ${YELLOW}./docker/status.sh${NC}"
echo -e "  查看日誌:     ${YELLOW}./docker/logs.sh${NC}"
echo ""

# 顯示服務狀態
echo -e "${BLUE}當前服務狀態:${NC}"
docker compose ps