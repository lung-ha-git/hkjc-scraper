# HKJC URL Patterns

## Horse Detail Pages

Each tab has its own dedicated URL:

| Tab | URL Pattern | Example |
|-----|-------------|---------|
| 主頁/往績 | `/horse?horseid={id}` | `/horse?horseid=HK_2023_J256` |
| **傷患紀錄** | **`/ovehorse?horseid={id}`** | `/ovehorse?horseid=HK_2023_J256` |
| 評分/體重 | `/ratingresultweight?horseid={id}` | `/ratingresultweight?horseid=HK_2023_J256` |
| 途程統計 | `/performance?horseid={id}` | `/performance?horseid=HK_2023_J256` |
| 晨操紀錄 | `/trackworkresult?horseid={id}` | `/trackworkresult?horseid=HK_2023_J256` |
| 搬遷紀錄 | `/movementrecords?horseid={id}` | `/movementrecords?horseid=HK_2023_J256` |

## Important Notes

- **ovehorse** = Overview Horse (傷患紀錄)
- Each tab has **dedicated URL** - no need to click tabs!
- Can scrape directly from specific URL

## 祝願 (HK_2023_J256) Status

| Tab | URL | Records |
|-----|-----|---------|
| 往績 | `/horse` | 17 |
| 傷患 | `/ovehorse` | **0 (沒有)** ✅ |
| 晨操 | `/trackworkresult` | 1427 ✅ |
| 搬遷 | `/movementrecords` | 1 ✅ |
