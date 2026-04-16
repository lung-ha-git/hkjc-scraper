#!/bin/bash
# HKJC Docker 日誌查看腳本
# 用途: 查看服務日誌

# 顏色定義
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 腳本所在目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 顯示幫助
show_help() {
    echo "用法: $0 [服務名]"
    echo ""
    echo "服務名:"
    echo "  web       - Web 前端日誌"
    echo "  api       - API 後端日誌"
    echo "  mongodb   - MongoDB 日誌"
    echo "  all       - 所有服務日誌 (默認)"
    echo ""
    echo "示例:"
    echo "  $0          # 查看所有日誌"
    echo "  $0 api      # 只查看 API 日誌"
    echo "  $0 web      # 只查看 Web 日誌"
}

# 檢查 Docker 是否運行
if ! docker info > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Docker 未運行${NC}"
    exit 1
fi

SERVICE="${1:-all}"

echo -e "${BLUE}查看日誌 - 按 Ctrl+C 退出${NC}"
echo ""

case "$SERVICE" in
    web|api|mongodb)
        docker compose logs -f "$SERVICE"
        ;;
    all|*)
        docker compose logs -f
        ;;
esac