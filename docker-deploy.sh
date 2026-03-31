#!/bin/bash
# HKJC Docker 部署腳本

set -e

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== HKJC Docker 部署腳本 ===${NC}"

# 檢查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker 未安裝${NC}"
    echo "請訪問 https://docs.docker.com/desktop/install/mac-install/ 安裝 Docker Desktop"
    exit 1
fi

# 檢查 docker-compose
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

# 顯示用法
usage() {
    echo "用法: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  setup       - 首次設置 (創建 .env 文件)"
    echo "  build       - 構建所有鏡像"
    echo "  start       - 啟動所有服務"
    echo "  stop        - 停止所有服務"
    echo "  restart     - 重啟所有服務"
    echo "  logs        - 查看日誌"
    echo "  status      - 查看服務狀態"
    echo "  collect     - 運行 Odds Collector (賽事日使用)"
    echo "  shell-api   - 進入 API 容器"
    echo "  shell-db    - 進入 MongoDB 容器"
    echo "  clean       - 清理所有數據 (警告: 會刪除數據庫!)"
    echo ""
}

# 設置環境
setup() {
    echo -e "${YELLOW}設置環境...${NC}"
    if [ ! -f .env ]; then
        cp .env.example .env
        echo -e "${GREEN}已創建 .env 文件，請編輯配置${NC}"
    else
        echo -e "${YELLOW}.env 文件已存在${NC}"
    fi
}

# 構建鏡像
build() {
    echo -e "${YELLOW}構建 Docker 鏡像...${NC}"
    $COMPOSE_CMD build --no-cache
    echo -e "${GREEN}構建完成!${NC}"
}

# 啟動服務
start() {
    echo -e "${YELLOW}啟動服務...${NC}"
    $COMPOSE_CMD up -d mongodb api web
    echo -e "${GREEN}服務已啟動!${NC}"
    echo ""
    echo "訪問地址:"
    echo "  - Web App: http://localhost"
    echo "  - API: http://localhost:3001"
    echo "  - MongoDB: mongodb://localhost:27017"
}

# 停止服務
stop() {
    echo -e "${YELLOW}停止服務...${NC}"
    $COMPOSE_CMD down
    echo -e "${GREEN}服務已停止!${NC}"
}

# 重啟服務
restart() {
    stop
    start
}

# 查看日誌
logs() {
    $COMPOSE_CMD logs -f
}

# 查看狀態
status() {
    $COMPOSE_CMD ps
}

# 運行 Odds Collector
collect() {
    if [ -z "$1" ] || [ -z "$2" ]; then
        echo -e "${RED}Error: 需要提供賽事日期和場地${NC}"
        echo "用法: $0 collect YYYY-MM-DD <ST|HV>"
        exit 1
    fi
    
    export RACE_DATE=$1
    export VENUE=$2
    
    echo -e "${YELLOW}運行 Odds Collector: $RACE_DATE @ $VENUE${NC}"
    $COMPOSE_CMD --profile race-day run --rm odds-collector
}

# 進入容器
shell_api() {
    $COMPOSE_CMD exec api /bin/bash
}

shell_db() {
    $COMPOSE_CMD exec mongodb mongosh -u admin -p hkjc_password_2024 --authenticationDatabase admin
}

# 清理
clean() {
    echo -e "${RED}警告: 這將刪除所有 Docker 數據和卷!${NC}"
    read -p "確定要繼續嗎? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        $COMPOSE_CMD down -v --remove-orphans
        docker system prune -f
        echo -e "${GREEN}清理完成!${NC}"
    else
        echo "已取消"
    fi
}

# 主命令
case "${1:-}" in
    setup)
        setup
        ;;
    build)
        build
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    status)
        status
        ;;
    collect)
        collect $2 $3
        ;;
    shell-api)
        shell_api
        ;;
    shell-db)
        shell_db
        ;;
    clean)
        clean
        ;;
    *)
        usage
        exit 1
        ;;
esac
