# FEAT-006: Racecard vs Actual Entries Validation ✅ COMPLETE

## Summary
Completed implementation of FEAT-006 on 2026-03-23. This feature validates racecard entries against the actual entries shown on the HKJC odds page to detect changes like substitute horses.

## Status: ✅ ALL SUB-TASKS COMPLETE

## Files Created/Modified

| File | Description |
|------|-------------|
| `hkjc_project/scrapers/validate_entries.js` | Node.js validation script |
| `hkjc_project/src/pipeline/entry_validator.py` | Python integration module |
| `hkjc_project/web-app/server/index.cjs` | API endpoints for validation data |
| `hkjc_project/web-app/src/App.jsx` | Webapp warning badge display |

## Features

### Detection Types
- **Added**: Horses in odds page but not in racecard
- **Removed**: Horses in racecard but not in odds page
- **Substituted**: Horses with `standby_no` (替補馬匹)
- **Changed**: Same horse_no but different jockey/trainer/draw/weight

### Sample Output
```
🔍 FEAT-006: Validating Racecard vs Odds Page Entries
📅 2026-03-22 ST
🏃 Races: 1, 2

  Race 1... 🔄 -2 removed, 2 substituted, 12 changed
  Race 2... 🔄 -2 removed, 2 substituted, 12 changed

📊 Validation Summary:
   Races checked: 2
   Races with changes: 2
   Total added: 0
   Total removed: 4
   Total substituted: 4
   Total changed: 24
```

## API Endpoints

### Get validation for race day
```
GET /api/validations/:date/:venue
```

Response:
```json
{
  "has_changes": true,
  "validated_at": "2026-03-23T07:54:49.734Z",
  "summary": {
    "total_races": 1,
    "races_with_changes": 1,
    "total_added": 0,
    "total_removed": 2,
    "total_substituted": 2,
    "total_changed": 12
  },
  "races": [...]
}
```

### Get validation for specific race
```
GET /api/validations/:date/:venue/:raceNo
```

## Webapp Warning Badge

When validation data shows changes, a warning badge appears next to the race tabs:

```jsx
{validationData && (
  <div className="validation-warning-badge" title="馬匹資料有變動">
    ⚠️ 馬匹變動
  </div>
)}
```

## Usage

### Standalone (Node.js)
```bash
cd hkjc_project
node scrapers/validate_entries.js 2026-03-22 ST --races 1,2,3
```

### Python Integration
```bash
cd hkjc_project
python src/pipeline/entry_validator.py 2026-03-22 ST
```

### Daily Pipeline (Auto-runs on race day)
```bash
cd hkjc_project
python daily_pipeline.py --part 1
```

## Database Schema

Results stored in `racecard_validations` collection:
```javascript
{
  date: "2026-03-22",
  venue: "ST",
  validated_at: ISODate("2026-03-23T15:30:00Z"),
  races: [...],
  summary: {
    total_races: 2,
    races_with_changes: 2,
    total_added: 0,
    total_removed: 4,
    total_substituted: 4,
    total_changed: 24
  }
}
```

## Integration with Daily Pipeline

Added to `FutureRacePipeline` as Step 5:
- Only runs on race day (when entries are finalized)
- Logs summary to pipeline results
- Webapp fetches validation data via API

## Implementation Notes

1. **Substitute horses** have `standby_no` but no regular `horse_no` (shown as `null`)
2. **Validation timing**: Only meaningful on race day when odds page entries are finalized
3. **Performance**: ~5-10s for 10 races (fresh browser per cycle)
4. **Storage**: One document per validation run with embedded race details
