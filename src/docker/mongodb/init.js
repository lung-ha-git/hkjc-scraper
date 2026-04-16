// MongoDB 初始化腳本
// 密碼從環境變量讀取或使用默認值

db = db.getSiblingDB('horse_racing');

// 嘗試讀取環境變量，如果失敗使用默認密碼
// 注意: MongoDB init scripts 在嚴格模式下運行，環境變量需要特殊處理
const appPassword = (typeof process !== 'undefined' && process.env && process.env.MONGODB_APP_PASSWORD) 
    ? process.env.MONGODB_APP_PASSWORD 
    : 'hkjc_app_2024';

try {
  // 創建應用用戶
  db.createUser({
    user: 'hkjc_app',
    pwd: appPassword,
    roles: [
      { role: 'readWrite', db: 'horse_racing' },
      { role: 'dbAdmin', db: 'horse_racing' }
    ]
  });
  print('User hkjc_app created successfully');
} catch (e) {
  // 用戶可能已存在
  print('User hkjc_app already exists or error: ' + e.message);
}

// 創建集合
try {
  db.createCollection('races');
  db.createCollection('horses');
  db.createCollection('odds');
  db.createCollection('predictions');
  db.createCollection('results');
  db.createCollection('backtests');
  print('Collections created successfully');
} catch (e) {
  print('Some collections already exist: ' + e.message);
}

// 創建索引
try {
  db.races.createIndex({ "race_date": 1, "venue": 1 });
  db.races.createIndex({ "race_id": 1 }, { unique: true });
  db.horses.createIndex({ "horse_id": 1 }, { unique: true });
  db.horses.createIndex({ "horse_name": 1 });
  db.odds.createIndex({ "race_id": 1, "horse_id": 1 });
  db.odds.createIndex({ "updated_at": 1 });
  db.predictions.createIndex({ "race_id": 1 });
  db.predictions.createIndex({ "created_at": -1 });
  db.results.createIndex({ "race_id": 1 });
  print('Indexes created successfully');
} catch (e) {
  print('Some indexes already exist: ' + e.message);
}

print('Database initialized successfully');
print('App password: ' + appPassword);
