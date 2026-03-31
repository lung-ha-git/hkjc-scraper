#!/bin/bash
# 下載最新訓練的模型
# 用法: bash scripts/download_latest_model.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="./downloaded_models_${TIMESTAMP}"

echo "📥 下載模型..."
echo "   時間戳: $TIMESTAMP"
echo "   輸出: $OUTPUT_DIR"

mkdir -p "$OUTPUT_DIR"

# 從 Docker container 複製 models 目錄
docker cp hkjc-pipeline:/app/models/. "$OUTPUT_DIR/"

if [ $? -eq 0 ]; then
    echo "✅ 模型下載完成！"
    echo "📁 位置: $OUTPUT_DIR"
    echo ""
    echo "📋 模型文件:"
    ls -la "$OUTPUT_DIR/"
else
    echo "❌ 下載失敗"
    exit 1
fi
