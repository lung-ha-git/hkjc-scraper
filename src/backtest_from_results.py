#!/usr/bin/env python3
"""
HKJC 赔率回测 - 使用 races.results 数据，不需要 racecard_entries
按模型预测 Top4 模拟投注，回测 ROI
"""

import sys, json
from collections import defaultdict
from datetime import datetime
sys.path.insert(0, '.')

def main():
    from src.database.connection import DatabaseConnection
    from predict_xgb import load_model
    
    db = DatabaseConnection()
    db.connect()
    
    print("Loading model...")
    model, model_features = load_model()
    
    print("Loading historical races...")
    all_races = list(db.db['races'].find({
        'results': {'$exists': True, '$ne': []},
        'payout': {'$exists': True, '$ne': {}}
    }).sort('race_date', 1))
    
    print(f"Total races: {len(all_races)}")
    
    # === 预计算骑师/练马师历史战绩 ===
    print("Computing jockey/trainer historical stats...")
    
    # 收集所有过往战绩
    jockey_stats = defaultdict(lambda: {'wins': 0, 'places': 0, 'runs': 0})
    trainer_stats = defaultdict(lambda: {'wins': 0, 'places': 0, 'runs': 0})
    
    for race in all_races:
        for r in race.get('results', []):
            j = r.get('jockey', '')
            t = r.get('trainer', '')
            rank = r.get('rank', 0)
            
            if j:
                jockey_stats[j]['runs'] += 1
                if rank == 1:
                    jockey_stats[j]['wins'] += 1
                if rank in (1, 2, 3):
                    jockey_stats[j]['places'] += 1
            
            if t:
                trainer_stats[t]['runs'] += 1
                if rank == 1:
                    trainer_stats[t]['wins'] += 1
                if rank in (1, 2, 3):
                    trainer_stats[t]['places'] += 1
    
    def get_jockey_stats(name):
        s = jockey_stats.get(name, {'wins': 0, 'places': 0, 'runs': 0})
        runs = max(s['runs'], 1)
        return {
            'jockey_win_rate': s['wins'] / runs,
            'jockey_place_rate': s['places'] / runs,
        }
    
    def get_trainer_stats(name):
        s = trainer_stats.get(name, {'wins': 0, 'places': 0, 'runs': 0})
        runs = max(s['runs'], 1)
        return {
            'trainer_win_rate': s['wins'] / runs,
            'trainer_place_rate': s['places'] / runs,
        }
    
    # === 简化特征构建（只用 results 数据）===
    def build_features_from_results(race, horse_result, all_entries):
        """只用当前race的results数据构建特征"""
        venue = race.get('venue', '')
        distance = race.get('distance', 1200)
        track_cond = race.get('track_condition', '')
        race_class = race.get('race_class', '')
        
        # 计算同场对手的平均评分
        all_odds = [float(r.get('win_odds', 10) or 10) for r in all_entries]
        avg_odds = sum(all_odds) / len(all_odds) if all_odds else 10
        
        # Draw advantage
        draw = horse_result.get('draw', 0) or 0
        
        # 草地/泥地
        is_hv = 1 if venue == 'HV' else 0
        
        # 评分代理：用 win_odds 的倒数（odds 越低 = 实力越强）
        win_odds = float(horse_result.get('win_odds', 0) or 0)
        rating_proxy = (1 / win_odds * 10) if win_odds > 0 else 0
        
        # 相对评分
        rel_rating = rating_proxy - (1 / avg_odds * 10) if avg_odds > 0 else 0
        
        # 档位评级
        draw_rating = max(0, 10 - abs(draw - 5)) if draw > 0 else 5
        
        # 前中后段速（从 running_position 解析）
        running_pos = horse_result.get('running_position', '')
        early_pace = 5.0
        try:
            parts = running_pos.split()
            if parts:
                first_pos = int(parts[0])
                early_pace = min(first_pos, 14)
        except:
            pass
        
        # weight diff
        actual_w = horse_result.get('actual_weight', 0) or 0
        declared_w = horse_result.get('declared_weight', 0) or 0
        weight_diff = actual_w - declared_w if actual_w and declared_w else 0
        
        jname = horse_result.get('jockey', '')
        tname = horse_result.get('trainer', '')
        js = get_jockey_stats(jname)
        ts = get_trainer_stats(tname)
        
        return {
            'draw': draw,
            'distance': distance,
            'venue': is_hv,
            'current_rating': rating_proxy,
            'relative_rating': rel_rating,
            'career_starts': 0,
            'career_wins': 0,
            'career_place_rate': 0,
            'season_prize': 0,
            'dist_wins': 0,
            'dist_runs': 0,
            'dist_win_rate': 0,
            'track_wins': 0,
            'track_runs': 0,
            'track_win_rate': 0,
            'jockey_win_rate': js['jockey_win_rate'],
            'jockey_place_rate': js['jockey_place_rate'],
            'trainer_win_rate': ts['trainer_win_rate'],
            'trainer_place_rate': ts['trainer_place_rate'],
            'recent3_avg_rank': 0,
            'recent3_wins': 0,
            'draw_advantage': max(0, 10 - abs(draw - 5)) if draw > 0 else 0,
            'draw_dist': 0,
            'draw_rating': draw_rating,
            'jt_place_rate': 0,
            'jt_races': 0,
            'track_cond_winrate': 0,
            'track_cond_runs': 0,
            'early_pace_score': early_pace,
            'best_dist_time': 0,
            'best_venue_dist_time': 0,
            'best_finish_time': 0,
            'finish_time_diff': 0,
        }
    
    # === 赔率解析 ===
    def parse_place_payout(race, horse_number):
        for p in race.get('payout', {}).get('place', []):
            if int(p.get('combination', 0)) == horse_number:
                return float(p.get('payout', 0))
        return 0
    
    def parse_qin_payout(race, h1, h2):
        key = tuple(sorted([h1, h2]))
        for q in race.get('payout', {}).get('quinella', []):
            parts = [int(x.strip()) for x in str(q.get('combination', '')).split(',')]
            if len(parts) == 2 and tuple(sorted(parts)) == key:
                return float(q.get('payout', 0))
        return 0
    
    def parse_qp_payout(race, h1, h2):
        key = tuple(sorted([h1, h2]))
        for q in race.get('payout', {}).get('quinella_place', []):
            parts = [int(x.strip()) for x in str(q.get('combination', '')).split(',')]
            if len(parts) == 2 and tuple(sorted(parts)) == key:
                return float(q.get('payout', 0))
        return 0
    
    def parse_f4_payout(race, combo):
        for f in race.get('payout', {}).get('first_4', []):
            parts = [int(x.strip()) for x in str(f.get('combination', '')).split(',')]
            if len(parts) == 4 and tuple(parts) == combo:
                return float(f.get('payout', 0))
        return 0
    
    # === 回测统计 ===
    stats = {
        'win': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'place': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'quinella': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'quinella_place': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'first4': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
    }
    
    meeting_stats = defaultdict(lambda: {k: {'cost':0,'payout':0,'profit':0,'hits':0,'races':0} for k in stats})
    
    print("Running backtest...")
    processed = 0
    
    # 需要有 draw 数据的场次
    usable_races = [r for r in all_races if r.get('results') and any(r.get('draw', 0) or 0 for r in r.get('results', []))]
    print(f"Usable races (with draw): {len(usable_races)}")
    
    for race in all_races:
        date = race.get('race_date', '')
        venue = race.get('venue', '')
        race_no = race.get('race_no', 0)
        results_list = race.get('results', [])
        
        if not results_list:
            continue
        
        # 检查是否有 draw 数据
        if not any(r.get('draw', 0) or 0 for r in results_list):
            continue
        
        try:
            # 构建特征
            all_features = []
            for r in results_list:
                feat = build_features_from_results(race, r, results_list)
                all_features.append((r, feat))
            
            # 提取特征矩阵
            import numpy as np
            feat_names = list(all_features[0][1].keys())
            X = np.array([[f.get(fn, 0) or 0 for fn in feat_names] for _, f in all_features])
            
            # 预测
            preds = model.predict(X)
            
            # 按 score 排序（XGBoost lower = better）
            scored = sorted(zip(results_list, preds), key=lambda x: x[1])
            top4 = [r.get('draw', 0) or r.get('horse_number', 0) for r, _ in scored[:4]]
            
        except Exception as e:
            processed += 1
            continue
        
        # 赢家信息
        winner_hn = None
        top3_hns = set()
        for r in results_list:
            rank = r.get('rank', 0)
            hn = r.get('draw', 0) or r.get('horse_number', 0)
            if rank == 1:
                winner_hn = hn
            if rank in (1, 2, 3):
                top3_hns.add(hn)
        
        # 计算投注回报
        bet = 25
        
        # 獨贏
        wc = bet * 4
        wp = bet * float(next((r.get('win_odds', 0) or 0 for r in results_list if (r.get('draw', 0) or r.get('horse_number', 0)) == winner_hn), 0)) if winner_hn in top4 else 0
        wh = 1 if winner_hn in top4 else 0
        wpr = wp - wc
        
        stats['win']['cost'] += wc; stats['win']['payout'] += wp; stats['win']['profit'] += wpr; stats['win']['hits'] += wh; stats['win']['races'] += 1
        
        # 位置
        pp = sum(bet / 10 * parse_place_payout(race, hn) for hn in top4 if hn in top3_hns)
        ph = 1 if any(hn in top3_hns for hn in top4) else 0
        ppr = pp - wc
        stats['place']['cost'] += wc; stats['place']['payout'] += pp; stats['place']['profit'] += ppr; stats['place']['hits'] += ph; stats['place']['races'] += 1
        
        # QIN
        from itertools import combinations, permutations
        qin_cs = list(combinations(top4, 2))
        qc = len(qin_cs) * 10
        qpt = sum(10 / 10 * parse_qin_payout(race, c[0], c[1]) for c in qin_cs)
        qh = 1 if any(parse_qin_payout(race, c[0], c[1]) > 0 for c in qin_cs) else 0
        stats['quinella']['cost'] += qc; stats['quinella']['payout'] += qpt; stats['quinella']['profit'] += qpt - qc; stats['quinella']['hits'] += qh; stats['quinella']['races'] += 1
        
        # QP
        qpp = sum(10 / 10 * parse_qp_payout(race, c[0], c[1]) for c in qin_cs)
        qph = 1 if any(parse_qp_payout(race, c[0], c[1]) > 0 for c in qin_cs) else 0
        stats['quinella_place']['cost'] += qc; stats['quinella_place']['payout'] += qpp; stats['quinella_place']['profit'] += qpp - qc; stats['quinella_place']['hits'] += qph; stats['quinella_place']['races'] += 1
        
        # First4
        f4_cs = list(permutations(top4, 4))
        fc = len(f4_cs) * 5
        fpt = sum(5 / 10 * parse_f4_payout(race, c) for c in f4_cs)
        fh = 1 if any(parse_f4_payout(race, c) > 0 for c in f4_cs) else 0
        stats['first4']['cost'] += fc; stats['first4']['payout'] += fpt; stats['first4']['profit'] += fpt - fc; stats['first4']['hits'] += fh; stats['first4']['races'] += 1
        
        # 赛马日统计
        mk = (date, venue)
        meeting_stats[mk]['win']['cost'] += wc; meeting_stats[mk]['win']['payout'] += wp; meeting_stats[mk]['win']['profit'] += wpr; meeting_stats[mk]['win']['hits'] += wh; meeting_stats[mk]['win']['races'] += 1
        meeting_stats[mk]['place']['cost'] += wc; meeting_stats[mk]['place']['payout'] += pp; meeting_stats[mk]['place']['profit'] += ppr; meeting_stats[mk]['place']['hits'] += ph; meeting_stats[mk]['place']['races'] += 1
        meeting_stats[mk]['quinella']['cost'] += qc; meeting_stats[mk]['quinella']['payout'] += qpt; meeting_stats[mk]['quinella']['profit'] += qpt - qc; meeting_stats[mk]['quinella']['hits'] += qh; meeting_stats[mk]['quinella']['races'] += 1
        meeting_stats[mk]['quinella_place']['cost'] += qc; meeting_stats[mk]['quinella_place']['payout'] += qpp; meeting_stats[mk]['quinella_place']['profit'] += qpp - qc; meeting_stats[mk]['quinella_place']['hits'] += qph; meeting_stats[mk]['quinella_place']['races'] += 1
        meeting_stats[mk]['first4']['cost'] += fc; meeting_stats[mk]['first4']['payout'] += fpt; meeting_stats[mk]['first4']['profit'] += fpt - fc; meeting_stats[mk]['first4']['hits'] += fh; meeting_stats[mk]['first4']['races'] += 1
        
        processed += 1
        if processed % 300 == 0:
            print(f"  Processed {processed}/{len(all_races)} races...")
    
    db.disconnect()
    
    # === 输出报告 ===
    print(f"\n完成！处理 {processed} 场\n")
    
    print("=" * 68)
    print("HKJC 赔率回测报告 (模型预测 Top4 投注策略)")
    print("=" * 68)
    print(f"回测场次: {stats['win']['races']} 场")
    print(f"回测区间: {all_races[0].get('race_date')} ~ {all_races[-1].get('race_date')}")
    print()
    
    names = {
        'win': '獨贏 (Top4均注 $25/匹)',
        'place': '位置 (Top4均注 $25/匹)',
        'quinella': 'QIN (6注×$10/注)',
        'quinella_place': 'QP (6注×$10/注)',
        'first4': 'First4 (24注×$5/注)',
    }
    
    print(f"{'玩法':<25} {'总成本':>10} {'总回报':>10} {'净利润':>10} {'ROI%':>8} {'命中率':>8}")
    print("-" * 71)
    
    for bt, name in names.items():
        st = stats[bt]
        if st['races'] == 0:
            continue
        roi = st['profit'] / st['cost'] * 100 if st['cost'] > 0 else 0
        hit = st['hits'] / st['races'] * 100 if st['races'] > 0 else 0
        print(f"{name:<25} ${st['cost']:>9,.0f} ${st['payout']:>9,.0f} ${st['profit']:>9,.0f} {roi:>7.1f}% {hit:>7.1f}%")
    
    # 总成本和净利润
    total_cost = sum(stats[k]['cost'] for k in stats)
    total_profit = sum(stats[k]['profit'] for k in stats)
    total_roi = total_profit / total_cost * 100 if total_cost > 0 else 0
    print("-" * 71)
    print(f"{'合计':<25} ${total_cost:>9,.0f} ${total_cost+total_profit:>9,.0f} ${total_profit:>9,.0f} {total_roi:>7.1f}%")
    
    # 赛马日明细
    print("\n" + "=" * 68)
    print("按赛马日明细 (最近20个)")
    print("=" * 68)
    
    sorted_meetings = sorted(meeting_stats.items(), key=lambda x: x[0][0], reverse=True)
    
    for (date, venue), mst in sorted_meetings[:20]:
        races_count = mst['win']['races']
        if races_count == 0:
            continue
        venue_name = '沙田' if venue == 'ST' else '跑馬地'
        
        # 總净利润
        total_m_profit = sum(mst[k]['profit'] for k in mst)
        total_m_cost = sum(mst[k]['cost'] for k in mst)
        m_roi = total_m_profit / total_m_cost * 100 if total_m_cost > 0 else 0
        
        win_roi = mst['win']['profit'] / mst['win']['cost'] * 100 if mst['win']['cost'] > 0 else 0
        place_roi = mst['place']['profit'] / mst['place']['cost'] * 100 if mst['place']['cost'] > 0 else 0
        qin_roi = mst['quinella']['profit'] / mst['quinella']['cost'] * 100 if mst['quinella']['cost'] > 0 else 0
        f4_roi = mst['first4']['profit'] / mst['first4']['cost'] * 100 if mst['first4']['cost'] > 0 else 0
        
        marker = "✅" if total_m_profit > 0 else "❌"
        print(f"\n{marker} {date} ({venue_name}) | {races_count}場 | 總净利润: ${total_m_profit:,.0f} | ROI: {m_roi:.1f}%")
        print(f"   獨贏:{win_roi:>6.1f}%  位置:{place_roi:>6.1f}%  QIN:{qin_roi:>6.1f}%  First4:{f4_roi:>6.1f}%")
    
    # 保存JSON
    report = {
        'overall': {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in stats.items()},
        'meetings': [{'date': d, 'venue': v, **{k: {kk: round(vv,2) for kk,vv in vs.items()} for k,vs in m.items()}} for (d,v),m in sorted_meetings if m['win']['races'] > 0]
    }
    with open('backtest_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n完整报告已保存: backtest_report.json")

if __name__ == '__main__':
    main()
