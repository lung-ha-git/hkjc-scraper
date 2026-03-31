#!/bin/bash
# MongoDB 初始化腳本生成器
# 從環境變量生成 init.js

set -e

# 生成 init.js
cat > /docker-entrypoint-initdb.d/init-generated.js << 'EOF'
// MongoDB 初始化腳本 (自動生成)
// 創建數據庫和集合

db = db.getSiblingDB('horse_racing');

// 創建應用用戶 (密碼從環境變量讀取)
const appUser = 'hkjc_app';
const appPassword = process.env.MONGODB_APP_PASSWORD || 'changeme_default_app_password';

db.createUser({
  user: appUser,
  pwd: appPassword,
  roles: [
    { role: 'readWrite', db: 'horse_racing' },
    { role: 'dbAdmin', db: 'horse_racing' }
  ]
});

// 創建集合
db.createCollection('races');
db.createCollection('horses');
db.createCollection('odds');
db.createCollection('predictions');
db.createCollection('results');
db.createCollection('backtests');

// 創建索引
db.races.createIndex({ "race_date": 1, "venue": 1 });
db.races.createIndex({ "race_id": 1 }, { unique: true });
db.horses.createIndex({ "horse_id": 1 }, { unique: true });
db.horses.createIndex({ "horse_name": 1 });
db.odds.createIndex({ "race_id": 1, "horse_id": 1 });
db.odds.createIndex({ "updated_at": 1 });
db.predictions.createIndex({ "race_id": 1 });
db.predictions.createIndex({ "created_at": -1 });
db.results.createIndex({ "race_id": 1 });

print('Database initialized successfully');
EOF

chmod +x /docker-entrypoint-initdb.d/init-generated.js
echo "Generated init-generated.js successfully"
