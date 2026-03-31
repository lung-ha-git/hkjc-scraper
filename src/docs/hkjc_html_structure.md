# HKJC Horse Page HTML Structure

## Table Selectors (Updated 2026-03-08)

### 1. 往績紀錄 (Race History)
- **Table Class**: `bigborder`
- **Note**: 忽略 "往績賽事 XX/XX 馬季" 嘅 row
- **Expected Rows**: 祝願應有 17 場 (唔係 22)

### 2. 馬匹評分/體重/名次 (Rating/Weight/Position)
- **Table Class**: `bigborder`
- **Note**: 可能同往績紀錄相同 table，只係顯示唔同 columns

### 3. 所跑途程賽績紀錄 (Distance Performance)
- **Table Class**: `horseperformance`

### 4. 晨操紀錄 (Workouts)
- **Table Class**: `table_bd f_tal f_fs13 f_ffChinese`

### 5. 傷患紀錄 (Medical)
- **Table Class**: `table_bd`
- **XPath**: `/html/body/div[1]/div[3]/div[2]/div[2]/div[2]/div[2]/table`
- **Note**: 冇 table = 冇資料 (祝願應為 0)

### 6. 搬遷紀錄 (Movements)
- **Table ID**: `MovementRecord`

### 7. 血統簡評 (Pedigree)
- **Table Class**: `blood`
- **Note**: 有兩個 table，資料都要存

## 重要規則
- 冇 table = 冇資料 (唔係錯誤)
- 往績紀錄要忽略季節分隔 row
- 祝願實際應有 17 場往績 (唔係 22)

## Usage in Scraper
```python
# Race history
table = page.locator("table.bigborder").first

# Distance performance  
table = page.locator("table.horseperformance").first

# Workouts
table = page.locator("table.table_bd").filter(has_text="晨操").first

# Medical
table = page.locator("table.table_bd").nth(1)  # or by xpath

# Movements
table = page.locator("table#MovementRecord")

# Pedigree
tables = page.locator("table.blood").all()
```
