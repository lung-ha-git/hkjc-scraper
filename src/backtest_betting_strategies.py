#!/usr/bin/env python3
"""
HKJC 回测 - 找出最佳投注策略组合
"""

import sys, json
from collections import defaultdict
from itertools import combinations
sys.path.insert(0, '.')

def main():
    from src.database.connection import DatabaseConnection
    import numpy as np
    
    db = DatabaseConnection()
    db.connect()
    
    print("Loading races...")
    all_races = sorted(
        list(db.db['races'].find({
            'results': {'$exists': True, '$ne': []},
            'payout': {'$exists': True, '$ne': {}}
        })),
        key=lambda r: r.get('race_date', '')
    )
    print(f"Total: {len(all_races)} races")
    
    # 预计算历史战绩
    j_stats = defaultdict(lambda: {'wins': 0, 'runs': 0, 'places': 0})
    t_stats = defaultdict(lambda: {'wins': 0, 'runs': 0, 'places': 0})
    
    def update_stats(race):
        for r in race.get('results', []):
            j = r.get('jockey', '').strip()
            t = r.get('trainer', '').strip()
            rank = r.get('rank', 0)
            if j:
                j_stats[j]['runs'] += 1
                if rank == 1: j_stats[j]['wins'] += 1
                if rank in (1,2,3): j_stats[j]['places'] += 1
            if t:
                t_stats[t]['runs'] += 1
                if rank == 1: t_stats[t]['wins'] += 1
                if rank in (1,2,3): t_stats[t]['places'] += 1
    
    def parse_payout(race, hn, bet_type):
        """返回派彩率（每 $1 派多少）"""
        p = race.get('payout', {})
        if bet_type == 'win':
            for item in p.get('win', []):
                if int(item.get('combination', 0) or 0) == hn:
                    return float(item.get('payout', 0))
        elif bet_type == 'place':
            for item in p.get('place', []):
                if int(item.get('combination', 0) or 0) == hn:
                    return float(item.get('payout', 0))
        return 0
    
    def get_top4_predictions(race, entries, j_stats, t_stats):
        """用预测模型排序"""
        results = []
        for r in entries:
            odds = float(r.get('win_odds', 0) or 0)
            j = r.get('jockey', '').strip()
            t = r.get('trainer', '').strip()
            
            js = j_stats.get(j, {'wins': 0, 'runs': 0})
            ts = t_stats.get(t, {'wins': 0, 'runs': 0})
            
            odds_score = 10 / odds if odds > 0 else 0
            j_rate = js['wins'] / max(js['runs'], 1)
            t_rate = ts['wins'] / max(ts['runs'], 1)
            
            combined = odds_score * 0.8 + j_rate * 10 * 0.2
            
            results.append((r, combined))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results  # list of (race_result, score)
    
    def run_strategy(race, top4_scored, strategy, bet_type, bet_amount_per_horse):
        """
        strategy: 'top1' | 'top2' | 'top3' | 'top4' | 'value'
        bet_type: 'win' | 'place'
        bet_amount_per_horse: 每匹投多少
        """
        top_horses = [r for r, _ in top4_scored[:4]]
        
        if strategy == 'value':
            # 只买赔率 > X 的马
            threshold = bet_amount_per_horse  # 用threshold值作为参数
            selected = []
            for r, score in top4_scored[:3]:
                odds = float(r.get('win_odds', 0) or 0)
                if odds >= threshold:
                    selected.append(r)
            if not selected:
                return {'cost': 0, 'payout': 0, 'profit': 0, 'hit': 0}
        else:
            n = {'top1': 1, 'top2': 2, 'top3': 3, 'top4': 4}.get(strategy, 4)
            selected = top_horses[:n]
        
        if not selected:
            return {'cost': 0, 'payout': 0, 'profit': 0, 'hit': 0}
        
        # 获取实际赢家
        results_list = race.get('results', [])
        winner_hn = None
        top3_hns = set()
        for r in results_list:
            hn = r.get('draw', 0) or r.get('horse_number', 0)
            rank = r.get('rank', 0)
            if rank == 1: winner_hn = hn
            if rank in (1,2,3): top3_hns.add(hn)
        
        cost = len(selected) * bet_amount_per_horse
        payout = 0
        hit = 0
        
        for r in selected:
            hn = r.get('draw', 0) or r.get('horse_number', 0)
            payout_rate = parse_payout(race, hn, bet_type)
            
            if payout_rate > 0:
                # 赢了！
                payout += bet_amount_per_horse / 10 * payout_rate
                if bet_type == 'win' and hn == winner_hn:
                    hit = 1
                elif bet_type == 'place' and hn in top3_hns:
                    hit = 1
        
        return {
            'cost': cost,
            'payout': payout,
            'profit': payout - cost,
            'hit': hit
        }
    
    # === 回测各种策略组合 ===
    all_strategies = {}
    
    for strategy in ['top1', 'top2', 'top3', 'top4']:
        for bet_type in ['win', 'place']:
            for bet_amount in [10, 25, 50, 100]:
                key = f"{strategy}_{bet_type}_${bet_amount}"
                all_strategies[key] = {
                    'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0, 'bets': 0
                }
    
    # 特殊策略：只买高赔率马
    for threshold in [3.0, 5.0, 7.0, 10.0]:
        for bet_type in ['win', 'place']:
            for bet_amount in [25, 50, 100]:
                key = f"value_{threshold}_{bet_type}_${bet_amount}"
                all_strategies[key] = {
                    'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0, 'bets': 0
                }
    
    # 策略：只买 predicted winner
    for odds_range in ['all', 'low', 'high']:
        for bet_type in ['win']:
            for bet_amount in [25, 50, 100]:
                key = f"winner_{odds_range}_{bet_type}_${bet_amount}"
                all_strategies[key] = {
                    'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0, 'bets': 0
                }
    
    meeting_stats = defaultdict(dict)
    processed = 0
    
    for race in all_races:
        date = race.get('race_date', '')
        venue = race.get('venue', '')
        results_list = race.get('results', [])
        
        if not results_list:
            continue
        
        if not any(r.get('draw', 0) or 0 for r in results_list):
            continue
        
        # 预测
        top4_scored = get_top4_predictions(race, results_list, j_stats, t_stats)
        if not top4_scored:
            update_stats(race)
            continue
        
        winner_hn = None
        top3_hns = set()
        for r in results_list:
            hn = r.get('draw', 0) or r.get('horse_number', 0)
            rank = r.get('rank', 0)
            if rank == 1: winner_hn = hn
            if rank in (1,2,3): top3_hns.add(hn)
        
        winner_odds = float(next((r.get('win_odds', 0) or 0 for r in results_list 
                                 if (r.get('draw', 0) or r.get('horse_number', 0)) == winner_hn), 0))
        
        # 运行标准策略
        for strategy in ['top1', 'top2', 'top3', 'top4']:
            for bet_type in ['win', 'place']:
                for bet_amount in [10, 25, 50, 100]:
                    key = f"{strategy}_{bet_type}_${bet_amount}"
                    result = run_strategy(race, top4_scored, strategy, bet_type, bet_amount)
                    if result['cost'] > 0:
                        s = all_strategies[key]
                        s['cost'] += result['cost']
                        s['payout'] += result['payout']
                        s['profit'] += result['profit']
                        s['hits'] += result['hit']
                        s['races'] += 1
                        s['bets'] += 1
        
        # Value 策略
        for threshold in [3.0, 5.0, 7.0, 10.0]:
            for bet_type in ['win', 'place']:
                for bet_amount in [25, 50, 100]:
                    key = f"value_{threshold}_{bet_type}_${bet_amount}"
                    result = run_strategy(race, top4_scored, 'value', bet_type, threshold)
                    if result['cost'] > 0:
                        s = all_strategies[key]
                        s['cost'] += result['cost']
                        s['payout'] += result['payout']
                        s['profit'] += result['profit']
                        s['hits'] += result['hit']
                        s['races'] += 1
                        s['bets'] += 1
        
        # Winner only 策略
        for odds_range, condition in [('all', True), ('low', winner_odds <= 5.0), ('high', winner_odds > 5.0)]:
            for bet_type in ['win']:
                for bet_amount in [25, 50, 100]:
                    key = f"winner_{odds_range}_{bet_type}_${bet_amount}"
                    if condition:
                        result = run_strategy(race, top4_scored, 'top1', bet_type, bet_amount)
                        if result['cost'] > 0:
                            s = all_strategies[key]
                            s['cost'] += result['cost']
                            s['payout'] += result['payout']
                            s['profit'] += result['profit']
                            s['hits'] += result['hit']
                            s['races'] += 1
                            s['bets'] += 1
                    else:
                        # 不符合条件，不投注
                        s = all_strategies[key]
                        s['races'] += 1
        
        # 赛马日记录
        mk = (date, venue)
        
        update_stats(race)
        processed += 1
        if processed % 400 == 0:
            print(f"  {processed}/{len(all_races)} races...")
    
    db.disconnect()
    
    # === 输出报告 ===
    print(f"\n完成！共 {processed} 场\n")
    
    # 过滤掉投注数太少的策略（至少要100场）
    valid = {k: v for k, v in all_strategies.items() if v['races'] >= 100}
    
    print("=" * 80)
    print("HKJC 投注策略回测报告")
    print("=" * 80)
    print(f"回测区间: {all_races[0].get('race_date')} ~ {all_races[-1].get('race_date')}")
    print()
    
    # 按ROI排序
    sorted_strats = sorted(valid.items(), key=lambda x: x[1]['profit'] / max(x[1]['cost'], 1), reverse=True)
    
    print(f"{'排名':>4} {'策略':<35} {'净利润':>12} {'ROI%':>8} {'命中率':>8} {'投注场次':>8} {'总成本':>12}")
    print("-" * 95)
    
    for i, (key, s) in enumerate(sorted_strats[:30]):
        roi = s['profit'] / s['cost'] * 100 if s['cost'] > 0 else 0
        hit = s['hits'] / s['bets'] * 100 if s['bets'] > 0 else 0
        marker = "✅" if s['profit'] > 0 else "❌"
        print(f"{marker}{i+1:>3} {key:<35} ${s['profit']:>11,.0f} {roi:>7.1f}% {hit:>7.1f}% {s['races']:>8} ${s['cost']:>11,.0f}")
    
    # 分 Bet Type 总结
    print("\n" + "=" * 80)
    print("按投注类型总结")
    print("=" * 80)
    
    by_type = {}
    for key, s in valid.items():
        parts = key.split('_')
        bet_type = parts[1] if len(parts) > 1 else parts[0]
        strategy_name = '_'.join(parts[:-2])
        
        if bet_type not in by_type:
            by_type[bet_type] = {'cost': 0, 'profit': 0, 'races': 0}
        
        by_type[bet_type]['cost'] += s['cost']
        by_type[bet_type]['profit'] += s['profit']
        by_type[bet_type]['races'] += s['races']
    
    print(f"\n{'投注类型':<15} {'总成本':>12} {'净利润':>12} {'ROI%':>8}")
    print("-" * 50)
    for bt, s in by_type.items():
        roi = s['profit'] / s['cost'] * 100 if s['cost'] > 0 else 0
        marker = "✅" if s['profit'] > 0 else "❌"
        print(f"{marker} {bt:<13} ${s['cost']:>11,.0f} ${s['profit']:>11,.0f} {roi:>7.1f}%")
    
    # 保存完整报告
    report = {
        'strategies': {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in valid.items()},
        'by_type': {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in by_type.items()},
        'total_races': processed
    }
    with open('strategy_backtest_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n完整报告: strategy_backtest_report.json")

if __name__ == '__main__':
    main()
