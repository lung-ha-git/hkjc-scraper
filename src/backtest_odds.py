#!/usr/bin/env python3
"""
HKJC 赔率回测 - 使用 races.results 数据
用 win_odds + jockey/trainer stats 作为预测信号

回测策略：
- 策略A: 只看 win_odds（市場共識）
- 策略B: win_odds + jockey/trainer 统计
- 策略C: ML model (limited features)
"""

import sys, json
from collections import defaultdict
from itertools import combinations, permutations
sys.path.insert(0, '.')

def main():
    from src.database.connection import DatabaseConnection
    import numpy as np
    
    db = DatabaseConnection()
    db.connect()
    
    print("Loading races...")
    all_races = list(db.db['races'].find({
        'results': {'$exists': True, '$ne': []},
        'payout': {'$exists': True, '$ne': {}}
    }).sort('race_date', 1))
    
    print(f"Total races: {len(all_races)}")
    
    # === 预计算过往战绩（到每场比赛之前）===
    print("Computing historical stats...")
    
    # 按日期排序
    all_races_sorted = sorted(all_races, key=lambda r: r.get('race_date', ''))
    
    # 预先计算每个骑师/练马师的累计战绩
    j_stats = defaultdict(lambda: {'wins': 0, 'runs': 0, 'places': 0})
    t_stats = defaultdict(lambda: {'wins': 0, 'runs': 0, 'places': 0})
    
    # 预计算每对 jockey-trainer 的历史战绩
    jt_stats = defaultdict(lambda: {'wins': 0, 'places': 0, 'runs': 0})
    
    def get_stats_before_date(date):
        """获取指定日期之前的累计战绩（不包含该日期）"""
        return dict(j_stats), dict(t_stats), dict(jt_stats)
    
    def update_stats(race):
        """更新战绩统计"""
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
            if j and t:
                jt_key = (j, t)
                jt_stats[jt_key]['runs'] += 1
                if rank == 1: jt_stats[jt_key]['wins'] += 1
                if rank in (1,2,3): jt_stats[jt_key]['places'] += 1
    
    # === 预测策略 ===
    def predict_by_odds(race, entries):
        """策略A: 只看 win_odds（最低 = 最被看好）"""
        sorted_entries = sorted(entries, key=lambda r: float(r.get('win_odds', 999) or 999))
        return [r.get('draw', 0) or r.get('horse_number', 0) for r in sorted_entries[:4]]
    
    def predict_by_odds_adjusted(race, entries, j_stats, t_stats, jt_stats):
        """策略B: odds + 骑师/练马师加成"""
        results = []
        for r in entries:
            odds = float(r.get('win_odds', 0) or 0)
            j = r.get('jockey', '').strip()
            t = r.get('trainer', '').strip()
            
            # odds 越低越好，转为分数
            odds_score = 10 / odds if odds > 0 else 0
            
            # 骑师加成
            js = j_stats.get(j, {'wins': 0, 'runs': 0})
            j_rate = js['wins'] / max(js['runs'], 1)
            
            # 练马师加成
            ts = t_stats.get(t, {'wins': 0, 'runs': 0})
            t_rate = ts['wins'] / max(ts['runs'], 1)
            
            # jockey-trainer combo
            jts = jt_stats.get((j, t), {'wins': 0, 'runs': 0})
            jt_rate = jts['wins'] / max(jts['runs'], 1)
            
            # 综合评分（加权）
            combined = odds_score * 0.7 + j_rate * 10 * 0.15 + t_rate * 10 * 0.1 + jt_rate * 10 * 0.05
            
            results.append((r, combined))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return [r.get('draw', 0) or r.get('horse_number', 0) for r, _ in results[:4]]
    
    def predict_by_model(race, entries, j_stats, t_stats, jt_stats):
        """策略C: 用简化ML模型（只用可计算的features）"""
        import pickle
        try:
            model_data = pickle.load(open('xgb_model.pkl', 'rb'))
            model = model_data['model']
        except:
            return predict_by_odds(race, entries)
        
        model_features = ['draw_rating', 'draw_advantage', 'early_pace_score', 
                        'jockey_win_rate', 'jockey_place_rate', 'trainer_win_rate',
                        'weight_advantage', 'jt_win_rate', 'jt_place_rate',
                        'jockey_runs', 'trainer_runs']
        
        feat_values = []
        for r in entries:
            try: draw = int(float(r.get('draw', 0) or 0))
            except: draw = 0
            draw = max(0, draw)
            j = r.get('jockey', '').strip()
            t = r.get('trainer', '').strip()
            running_pos = r.get('running_position', '')
            
            # early pace
            early = 5.0
            try:
                parts = running_pos.split()
                if parts: early = min(int(parts[0]), 14)
            except: pass
            
            # weight advantage
            aw = r.get('actual_weight', 0) or 0
            dw = r.get('declared_weight', 0) or 0
            wadv = (aw - dw) / 10 if aw and dw else 0
            
            js = j_stats.get(j, {'wins': 0, 'runs': 0, 'places': 0})
            ts = t_stats.get(t, {'wins': 0, 'runs': 0, 'places': 0})
            jts = jt_stats.get((j, t), {'wins': 0, 'runs': 0, 'places': 0})
            
            feats = [
                max(0, 10 - abs(draw - 5)),  # draw_rating
                max(0, 10 - abs(draw - 5)),  # draw_advantage
                early,                         # early_pace_score
                js['wins'] / max(js['runs'], 1),  # jockey_win_rate
                js['places'] / max(js['runs'], 1),  # jockey_place_rate
                ts['wins'] / max(ts['runs'], 1),    # trainer_win_rate
                wadv,                          # weight_advantage
                jts['wins'] / max(jts['runs'], 1),  # jt_win_rate
                jts['places'] / max(jts['runs'], 1), # jt_place_rate
                js['runs'],                         # jockey_runs
                ts['runs'],                         # trainer_runs
            ]
            feat_values.append(feats)
        
        try:
            X = np.array(feat_values)
            preds = model.predict(X)
            scored = sorted(zip(entries, preds), key=lambda x: x[1])
            return [r.get('draw', 0) or r.get('horse_number', 0) for r, _ in scored[:4]]
        except:
            return predict_by_odds(race, entries)
    
    # === 派彩解析 ===
    def parse_place(race, hn):
        for p in race.get('payout', {}).get('place', []):
            if int(p.get('combination', 0) or 0) == hn:
                return float(p.get('payout', 0))
        return 0
    
    def parse_qin(race, h1, h2):
        key = tuple(sorted([h1, h2]))
        for q in race.get('payout', {}).get('quinella', []):
            parts = [int(x.strip()) for x in str(q.get('combination', '')).split(',')]
            if len(parts) == 2 and tuple(sorted(parts)) == key:
                return float(q.get('payout', 0))
        return 0
    
    def parse_qp(race, h1, h2):
        key = tuple(sorted([h1, h2]))
        for q in race.get('payout', {}).get('quinella_place', []):
            parts = [int(x.strip()) for x in str(q.get('combination', '')).split(',')]
            if len(parts) == 2 and tuple(sorted(parts)) == key:
                return float(q.get('payout', 0))
        return 0
    
    def parse_f4(race, combo):
        for f in race.get('payout', {}).get('first_4', []):
            parts = [int(x.strip()) for x in str(f.get('combination', '')).split(',')]
            if len(parts) == 4 and tuple(parts) == combo:
                return float(f.get('payout', 0))
        return 0
    
    # === 回测 ===
    strategies = {
        'A_odds_only': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'B_odds_jockey': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'C_ml_model': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
    }
    
    # 独立统计各玩法
    bet_types = {
        'win': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'place': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'quinella': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'quinella_place': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
        'first4': {'cost': 0, 'payout': 0, 'profit': 0, 'hits': 0, 'races': 0},
    }
    
    # Strategy A/B/C 共享同样投注，用不同预测
    meeting_stats = defaultdict(lambda: {
        'A_win': {'profit': 0, 'cost': 0}, 'B_win': {'profit': 0, 'cost': 0}, 'C_win': {'profit': 0, 'cost': 0}
    })
    
    processed = 0
    j_stats_clear = defaultdict(lambda: {'wins': 0, 'runs': 0, 'places': 0})
    t_stats_clear = defaultdict(lambda: {'wins': 0, 'runs': 0, 'places': 0})
    jt_stats_clear = defaultdict(lambda: {'wins': 0, 'runs': 0, 'places': 0})
    
    for race in all_races_sorted:
        date = race.get('race_date', '')
        venue = race.get('venue', '')
        results_list = race.get('results', [])
        
        if not results_list:
            continue
        
        # 跳过没有 draw 的场次
        if not any(r.get('draw', 0) or 0 for r in results_list):
            continue
        
        entries = results_list
        winner_hn = None
        top3_hns = set()
        for r in results_list:
            rank = r.get('rank', 0)
            hn = r.get('draw', 0) or r.get('horse_number', 0)
            if rank == 1: winner_hn = hn
            if rank in (1,2,3): top3_hns.add(hn)
        
        # 三种预测
        top4_odds = predict_by_odds(race, entries)
        top4_aj = predict_by_odds_adjusted(race, entries, j_stats, t_stats, jt_stats)
        top4_ml = predict_by_model(race, entries, j_stats, t_stats, jt_stats)
        
        all_top4 = {'A_odds_only': top4_odds, 'B_odds_jockey': top4_aj, 'C_ml_model': top4_ml}
        
        bet = 25
        qin_cs = list(combinations([hn for hn in top4_odds if hn], 2))
        qc = len(qin_cs) * 10 if qin_cs else 60
        f4_cs = list(permutations([hn for hn in top4_odds if hn], 4))
        fc = len(f4_cs) * 5 if f4_cs else 120
        
        for strat, top4 in all_top4.items():
            # 獨贏
            wc = bet * 4
            wp = bet * float(next((r.get('win_odds', 0) or 0 for r in results_list if (r.get('draw', 0) or r.get('horse_number', 0)) == winner_hn), 0)) if winner_hn in top4 else 0
            wh = 1 if winner_hn in top4 else 0
            bet_types['win']['cost'] += wc; bet_types['win']['payout'] += wp; bet_types['win']['profit'] += wp - wc; bet_types['win']['hits'] += wh; bet_types['win']['races'] += 1
            strategies[strat]['cost'] += wc; strategies[strat]['payout'] += wp; strategies[strat]['profit'] += wp - wc; strategies[strat]['hits'] += wh; strategies[strat]['races'] += 1
            
            # 位置
            pp = sum(bet / 10 * parse_place(race, hn) for hn in top4 if hn in top3_hns)
            ph = 1 if any(hn in top3_hns for hn in top4) else 0
            bet_types['place']['cost'] += wc; bet_types['place']['payout'] += pp; bet_types['place']['profit'] += pp - wc; bet_types['place']['hits'] += ph; bet_types['place']['races'] += 1
            
            # QIN (用策略A的组合，其他策略同码)
            qpt = sum(10/10*parse_qin(race, c[0], c[1]) for c in qin_cs)
            qh = 1 if any(parse_qin(race, c[0], c[1]) > 0 for c in qin_cs) else 0
            bet_types['quinella']['cost'] += qc; bet_types['quinella']['payout'] += qpt; bet_types['quinella']['profit'] += qpt - qc; bet_types['quinella']['hits'] += qh; bet_types['quinella']['races'] += 1
            
            # QP
            qpp = sum(10/10*parse_qp(race, c[0], c[1]) for c in qin_cs)
            qph = 1 if any(parse_qp(race, c[0], c[1]) > 0 for c in qin_cs) else 0
            bet_types['quinella_place']['cost'] += qc; bet_types['quinella_place']['payout'] += qpp; bet_types['quinella_place']['profit'] += qpp - qc; bet_types['quinella_place']['hits'] += qph; bet_types['quinella_place']['races'] += 1
            
            # First4
            fpt = sum(5/10*parse_f4(race, c) for c in f4_cs)
            fh = 1 if any(parse_f4(race, c) > 0 for c in f4_cs) else 0
            bet_types['first4']['cost'] += fc; bet_types['first4']['payout'] += fpt; bet_types['first4']['profit'] += fpt - fc; bet_types['first4']['hits'] += fh; bet_types['first4']['races'] += 1
            
            mk = (date, venue)
            meeting_stats[mk][f'{strat[:1]}_win']['cost'] += wc
            meeting_stats[mk][f'{strat[:1]}_win']['profit'] += wp - wc
        
        # 更新统计（用于下一场比赛）
        update_stats(race)
        
        # 更新统计（用于下一场比赛，避免look-ahead bias）
        update_stats(race)
        
        processed += 1
        if processed % 400 == 0:
            print(f"  {processed}/{len(all_races_sorted)} races...")
    
    db.disconnect()
    
    # === 输出报告 ===
    print(f"\n完成！处理 {processed} 场\n")
    
    print("=" * 72)
    print("HKJC 赔率回测报告")
    print(f"回测区间: {all_races_sorted[0].get('race_date')} ~ {all_races_sorted[-1].get('race_date')}")
    print("=" * 72)
    
    print(f"\n{'策略':<30} {'总成本':>10} {'净利润':>10} {'ROI%':>8} {'独赢命中率':>10}")
    print("-" * 70)
    
    strat_names = {
        'A_odds_only': 'A. 只看 win_odds (市场共识)',
        'B_odds_jockey': 'B. win_odds + 骑师/练马师加成',
        'C_ml_model': 'C. ML模型 (limited features)',
    }
    
    for st, name in strat_names.items():
        s = strategies[st]
        if s['races'] == 0: continue
        roi = s['profit'] / s['cost'] * 100 if s['cost'] > 0 else 0
        hit = s['hits'] / s['races'] * 100 if s['races'] > 0 else 0
        marker = "✅" if s['profit'] > 0 else "❌"
        print(f"{marker} {name:<28} ${s['cost']:>9,.0f} ${s['profit']:>9,.0f} {roi:>7.1f}% {hit:>9.1f}%")
    
    print("\n" + "=" * 72)
    print("各玩法详细 (以策略A - 市场共识预测)")
    print("=" * 72)
    
    bet_names = {
        'win': '獨贏 (Top4均注 $25)',
        'place': '位置 (Top4均注 $25)',
        'quinella': 'QIN (6注×$10)',
        'quinella_place': 'QP (6注×$10)',
        'first4': 'First4 (24注×$5)',
    }
    
    print(f"\n{'玩法':<22} {'成本':>10} {'回报':>10} {'净利润':>10} {'ROI%':>8} {'命中率':>8}")
    print("-" * 70)
    
    for bt, name in bet_names.items():
        st = bet_types[bt]
        if st['races'] == 0: continue
        roi = st['profit'] / st['cost'] * 100 if st['cost'] > 0 else 0
        hit = st['hits'] / st['races'] * 100 if st['races'] > 0 else 0
        marker = "✅" if st['profit'] > 0 else "❌"
        print(f"{marker} {name:<20} ${st['cost']:>9,.0f} ${st['payout']:>9,.0f} ${st['profit']:>9,.0f} {roi:>7.1f}% {hit:>7.1f}%")
    
    # 赛马日明细（按策略A）
    print("\n" + "=" * 72)
    print("赛马日明细 (策略A - 最近20个)")
    print("=" * 72)
    
    sorted_meet = sorted(meeting_stats.items(), key=lambda x: x[0][0], reverse=True)
    
    for (date, venue), mst in sorted_meet[:20]:
        vc = mst.get('A_win', {}).get('cost', 0)
        vp = mst.get('A_win', {}).get('profit', 0)
        if vc == 0: continue
        venue_name = '沙田' if venue == 'ST' else '跑馬地'
        roi = vp / vc * 100
        marker = "✅" if vp > 0 else "❌"
        print(f"{marker} {date} ({venue_name}) | 净利润: ${vp:>8,.0f} | ROI: {roi:>6.1f}%")
    
    # 保存JSON
    report = {
        'strategies': {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in strategies.items()},
        'bet_types': {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in bet_types.items()},
        'meetings': [{'date': d, 'venue': v, 'A_profit': mst.get('A_win',{}).get('profit',0), 'A_cost': mst.get('A_win',{}).get('cost',0)} for d,v,mst in sorted_meet if mst.get('A_win',{}).get('cost',0) > 0]
    }
    with open('backtest_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n完整报告已保存: backtest_report.json")

if __name__ == '__main__':
    main()
