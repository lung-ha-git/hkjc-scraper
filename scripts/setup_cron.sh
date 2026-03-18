#!/bin/bash
# HKJC Daily Pipeline - Cron Setup
# =================================
# 安装方法:
#   1. Cron (Linux/macOS):
#      ./setup_cron.sh install
#
#   2. LaunchD (macOS 推荐):
#      ./setup_cron.sh install-launchd

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIPELINE_SCRIPT="$PROJECT_DIR/daily_pipeline.py"

echo "=============================================="
echo "HKJC Daily Pipeline - 安装脚本"
echo "=============================================="
echo ""

# Check if pipeline script exists
if [ ! -f "$PIPELINE_SCRIPT" ]; then
    echo "❌ 找不到 $PIPELINE_SCRIPT"
    exit 1
fi

# Function to install cron
install_cron() {
    echo "📝 安装 Cron Job..."
    
    # Create log directory
    mkdir -p "$PROJECT_DIR/logs/pipeline"
    
    # Create cron entry
    CRON_CMD="0 6 * * * cd $PROJECT_DIR && /usr/bin/python3 $PIONEER_SCRIPT >> $PROJECT_DIR/logs/pipeline/cron.log 2>&1"
    
    # Add to crontab
    (crontab -l 2>/dev/null | grep -v "$PIPELINE_SCRIPT"; echo "$CRON_CMD") | crontab -
    
    echo "✅ Cron 已安装"
    echo "   每天 6:00 AM 运行"
    echo "   日志: $PROJECT_DIR/logs/pipeline/cron.log"
}

# Function to install launchd
install_launchd() {
    echo "📝 安装 LaunchD..."
    
    # Create log directory
    mkdir -p "$PROJECT_DIR/logs/pipeline"
    
    # Copy plist
    PLIST_SOURCE="$SCRIPT_DIR/com.hkjc.dailypipeline.plist"
    PLIST_DEST="$HOME/Library/LaunchAgents/com.hkjc.dailypipeline.plist"
    
    if [ ! -f "$PLIST_SOURCE" ]; then
        echo "❌ 找不到 $PLIST_SOURCE"
        exit 1
    fi
    
    cp "$PLIST_SOURCE" "$PLIST_DEST"
    
    # Load
    launchctl load "$PLIST_DEST"
    
    echo "✅ LaunchD 已安装"
    echo "   每天 6:00 AM 运行"
    echo "   日志: $PROJECT_DIR/logs/pipeline/stdout.log"
}

# Function to uninstall
uninstall() {
    echo "📝 卸载..."
    
    # Cron
    crontab -l 2>/dev/null | grep -v "$PIPELINE_SCRIPT" | crontab - 2>/dev/null || true
    echo "   ✅ Cron 已移除"
    
    # LaunchD
    PLIST_DEST="$HOME/Library/LaunchAgents/com.hkjc.dailypipeline.plist"
    if [ -f "$PLIST_DEST" ]; then
        launchctl unload "$PLIST_DEST" 2>/dev/null || true
        rm -f "$PLIST_DEST"
        echo "   ✅ LaunchD 已移除"
    fi
}

# Function to show status
status() {
    echo "📊 状态:"
    echo ""
    
    # Check cron
    if crontab -l 2>/dev/null | grep -q "$PIPELINE_SCRIPT"; then
        echo "   ✅ Cron: 已安装"
    else
        echo "   ❌ Cron: 未安装"
    fi
    
    # Check launchd
    PLIST_DEST="$HOME/Library/LaunchAgents/com.hkjc.dailypipeline.plist"
    if [ -f "$PLIST_DEST" ]; then
        echo "   ✅ LaunchD: 已安装"
        launchctl list | grep -q "com.hkjc.dailypipeline" && echo "     (运行中)" || echo "     (未运行)"
    else
        echo "   ❌ LaunchD: 未安装"
    fi
    
    echo ""
    echo "📁 日志位置:"
    echo "   $PROJECT_DIR/logs/pipeline/"
}

# Main
case "${1:-}" in
    install)
        install_cron
        ;;
    install-launchd)
        install_launchd
        ;;
    uninstall)
        uninstall
        ;;
    status)
        status
        ;;
    *)
        echo "用法: $0 {install|install-launchd|uninstall|status}"
        echo ""
        echo "示例:"
        echo "  $0 install           # 安装 Cron (每天 6:00 AM)"
        echo "  $0 install-launchd  # 安装 LaunchD (macOS)"
        echo "  $0 uninstall        # 卸载"
        echo "  $0 status           # 查看状态"
        ;;
esac
