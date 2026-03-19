# Deployment Plan - HKJC Racing Prediction System

## Status: Ready for Deployment

## Completed Items ✅

### System Services
| Service | Status | Auto-start |
|---------|--------|-----------|
| `com.fatlung.hkjc-pipeline` | ✅ Configured | Daily 7:00 AM |
| `com.fatlung.hkjc-api` | ✅ Running | On boot |
| `com.fatlung.hkjc-webapp` | ✅ Running | On boot |

### Recent Code Changes (2026-03-19)

#### 1. Model Improvements
- [x] Removed `hj_win_rate` (overfitting - too few samples)
- [x] Added `best_dist_time` (路程最佳時間)
- [x] Added `best_venue_dist_time` (場地+路程最佳時間)
- [x] Added `track_cond_winrate` (場地適應勝率)
- [x] Added `early_pace_score` (前領/後上型)
- [x] Added `weight_advantage` (負磅優勢)

#### 2. Pipeline Fixes
- [x] Part 1: Racecards update daily for upcoming races (not just first scrape)
- [x] Part 3: Fixed to queue horses missing `name` field (display fields)
- [x] Part 4: Added queue worker to daily pipeline
- [x] Fixed `get_actual_race_count()` to use `RaceNo=` pattern
- [x] Fixed `PROJECT_ROOT` path for launchd git operations
- [x] Fixed MongoDB date format migration (slash → dash)
- [x] Fixed fixture venue/race_count from actual race data

#### 3. Infrastructure
- [x] Git config for launchd environment
- [x] Service plist files for API and Webapp
- [x] Learnings documentation

## Tomorrow Verification Checklist

### Morning (7:00 AM - 7:30 AM)
- [ ] Pipeline ran at 7:00 AM
- [ ] Check logs: `tail -100 logs/launchd-stderr.log`
- [ ] Verify Part 1: Future race cards updated
- [ ] Verify Part 3: Horse names populated (no more missing jerseys)
- [ ] Verify Part 4: Queue worker processed items

### Model Verification
- [ ] Load model and check feature importances:
  ```bash
  cd hkjc_project && python3 -c "
  import pickle
  with open('xgb_model.pkl','rb') as f: d=pickle.load(f)
  print('Features:', len(d['features']))
  for f,i in sorted(zip(d['features'],d['model'].feature_importances_),key=lambda x:-x[1])[:10]:
      print(f'  {i:.4f} {f}')
  "
  ```

### Webapp Verification
- [ ] Check http://localhost:3000 displays correctly
- [ ] Horse jerseys show for race entries
- [ ] Predictions work for upcoming race

### Git Push Verification
- [ ] Model trained and committed to git
- [ ] Check git log:
  ```bash
  cd hkjc_project && git log --oneline -5
  ```

## Post-Deployment Monitoring

### Key Metrics
- Pipeline success/failure in logs
- Horse jersey display on webapp
- Prediction accuracy (Top3 hit rate)

### Common Issues
1. **Service not running**: `launchctl kickstart -kp gui/$(id -u)/com.fatlung.hkjc-pipeline`
2. **Webapp down**: Restart with service plist
3. **MongoDB connection**: Check `brew services status mongodb-community`

## Rollback Plan

If issues found:
1. Revert to previous model: `git checkout HEAD~1 -- hkjc_project/xgb_model.pkl`
2. Or use backup model files in git history
