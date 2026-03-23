# FEAT-006: Racecard vs Actual Entries Validation

## Summary
Completed implementation of FEAT-006 on 2026-03-23. This feature validates racecard entries against the actual entries shown on the HKJC odds page to detect changes like substitute horses.

## Files Created

| File | Description |
|------|-------------|
| `hkjc_project/scrapers/validate_entries.js` | Node.js validation script |
| `hkjc_project/src/pipeline/entry_validator.py` | Python integration module |

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
- Stored in MongoDB for Webapp consumption (FEAT-007 dependent)

## Pending: FEAT-006.5

Webapp display of "馬匹有變動" warning:
- Depends on FEAT-007 (HKJC Odds Page Racecard API)
- Will add API endpoint `/api/validations/:date/:venue`
- Mobile + Desktop warning badge
