# 模型下載指南

Pipeline 完成模型訓練後，手動下載模型的方法。

## 模型位置

在 Docker container 內：
```
/app/models/
├── xgb_model.pkl          # XGBoost 主模型
├── ensemble_v1_config.json # 模型配置
└── ensemble_v1_stats.json # 模型統計（如有）
```

## 下載方法

### 方法 1: 直接複製（推薦）

```bash
# 下載完整 models 目錄
docker cp hkjc-pipeline:/app/models/ ./downloaded_models/

# 或指定時間戳
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker cp hkjc-pipeline:/app/models/ ./downloaded_models_${TIMESTAMP}/
```

### 方法 2: 查看模型訓練時間

```bash
docker exec hkjc-pipeline ls -la /app/models/
```

### 方法 3: 使用腳本自動下載

```bash
cd /Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC
bash scripts/download_latest_model.sh
```

## 自動化腳本

參見 `scripts/download_latest_model.sh`

## 更新 Pipeline 後

Pipeline 現在會輸出：
```
📥 模型已更新，請使用：docker cp hkjc-pipeline:/app/models/ ./downloaded_models/
```

---

最後更新：2026-03-27
