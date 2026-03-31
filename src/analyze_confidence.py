import sys
from collections import defaultdict
sys.path.insert(0, '.')
from src.database.connection import DatabaseConnection

db = DatabaseConnection()
db.connect()
all_races = list(db.db['races'].find({
    'results': {'$exists': True, '$ne': []},
    'payout': {'$exists': True, '$ne': {}}
}).sort('race_date', 1))

j_stats = defaultdict(lambda: {'wins': 0, 'runs': 0})

def update_stats(race):
    for r in race.get('results', []):
        j = r.get('jockey', '').strip()
        rank = r.get('rank', 0)
        if j:
            j_stats[j]['runs'] += 1
            if rank == 1:
                j_stats[j]['wins'] += 1

def parse_payout(race, hn, bt):
    for item in race.get('payout', {}).get(bt, []):
        if int(item.get('combination', 0) or 0) == hn:
            return float(item.get('payout', 0))
    return 0

race_data = []
for race in all_races:
    rl = race.get('results', [])
    if not rl:
        continue
    if not any(r.get('draw', 0) or 0 for r in rl):
        continue
    
    scored = []
    for r in rl:
        odds = float(r.get('win_odds', 0) or 0)
        j = r.get('jockey', '').strip()
        js = j_stats.get(j, {'wins': 0, 'runs': 0})
        score = (10 / odds if odds > 0 else 0) * 0.8 + (js['wins'] / max(js['runs'], 1)) * 10 * 0.2
        scored.append((r, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    
    top1_r, top1_score = scored[0]
    top2_score = scored[1][1] if len(scored) > 1 else 0
    top1_hn = top1_r.get('draw', 0) or top1_r.get('horse_number', 0)
    top1_odds = float(top1_r.get('win_odds', 0) or 0)
    
    # find actual winner
    winner_hn = None
    winner_odds = 0
    for r in rl:
        if r.get('rank', 0) == 1:
            winner_hn = r.get('draw', 0) or r.get('horse_number', 0)
            winner_odds = float(r.get('win_odds', 0) or 0)
            break
    
    winner_hit = 1 if top1_hn == winner_hn else 0
    profit = (25 / 10 * parse_payout(race, winner_hn, 'win') - 25) if winner_hit else -25
    
    race_data.append({
        'score_gap': top1_score - top2_score,
        'top1_odds': top1_odds,
        'winner_hit': winner_hit,
        'actual_profit': profit,
        'winner_odds': winner_odds,
    })
    update_stats(race)

db.disconnect()

def analyze(label, races):
    if len(races) < 10:
        return
    hits = sum(r['winner_hit'] for r in races)
    profit = sum(r['actual_profit'] for r in races)
    roi = profit / (len(races) * 25) * 100
    m = "✅" if profit > 0 else "❌"
    print(f"{m} {label:<38} {len(races):>4}場 {hits/len(races)*100:>5.1f}% ${profit:>8,.0f} {roi:>6.1f}%")

print("=" * 72)
print("高信心篩選分析 (top1 獨贏 $25)")
print("=" * 72)
analyze("所有場次 (基準)", race_data)

print("\n--- 按 Score Gap 分組 ---")
for lo, hi in [(0, 1), (1, 2), (2, 3), (3, 5), (5, 999)]:
    g = [r for r in race_data if lo <= r['score_gap'] < hi]
    analyze(f"score_gap {lo}-{hi}", g)

print("\n--- 按 Top1 Odds 分組 ---")
for lo, hi in [(0, 3), (3, 6), (6, 10), (10, 20), (20, 999)]:
    g = [r for r in race_data if lo <= r['top1_odds'] < hi]
    analyze(f"top1_odds {lo}-{hi}", g)

print("\n--- 交叉篩選 ---")
for gt in [1, 2, 3]:
    for ol, oh in [(0, 5), (5, 10), (10, 999)]:
        g = [r for r in race_data if r['score_gap'] > gt and ol <= r['top1_odds'] < oh]
        if g:
            analyze(f"gap>{gt} & odds {ol}-{oh}", g)

print("\n--- 最佳ROI篩選 (至少30場) ---")
best = []
for gl, gh in [(0, 2), (1, 3), (2, 5), (3, 999)]:
    for ol, oh in [(0, 5), (3, 8), (5, 10), (8, 999)]:
        g = [r for r in race_data if gl <= r['score_gap'] < gh and ol <= r['top1_odds'] < oh]
        if len(g) >= 30:
            profit = sum(r['actual_profit'] for r in g)
            roi = profit / (len(g) * 25) * 100
            best.append((roi, len(g), profit, f"gap{gl}-{gh} odds{ol}-{oh}"))

best.sort(reverse=True)
for roi, n, profit, label in best[:15]:
    m = "✅" if profit > 0 else "❌"
    print(f"{m} {label:<30} {n:>4}場 ROI={roi:>6.1f}% ${profit:>8,.0f}")
