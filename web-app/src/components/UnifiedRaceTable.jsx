import React, { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip);

const COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
  '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
  '#F8B500', '#82E0AA', '#F1948A', '#7DCEA0', '#AED6F1', '#D7BDE2'
];

function fmt(v) {
  if (v == null || v === '') return '-';
  return parseFloat(v).toFixed(2);
}

function TinySparkline({ hist, color }) {
  if (!hist || hist.length < 2) return null;
  const max = 6;
  const step = Math.max(1, Math.floor(hist.length / max));
  const pts = hist.filter((_, i) => i % step === 0);
  const data = {
    labels: pts.map(() => ''),
    datasets: [{
      data: pts.map(p => p.win ?? p.place ?? 0),
      borderColor: color,
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.3,
      fill: false,
    }]
  };
  return (
    <div style={{ width: 24, height: 14 }}>
      <Line
        data={data}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 0 },
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { display: false }, y: { display: false } },
        }}
      />
    </div>
  );
}

export default function UnifiedRaceTable({ predictions, currentEntries, oddsData, oddsHistory, connected }) {
  const rows = useMemo(() => {
    if (!currentEntries || !Array.isArray(currentEntries)) return [];
    const result = [];
    const predictionsArr = Array.isArray(predictions) ? predictions : [];
    const entriesArr = Array.isArray(currentEntries) ? currentEntries : [];
    // Active horses: from predictions that have matching entries
    predictionsArr.slice().sort((a, b) => (a?.horse_no || 0) - (b?.horse_no || 0)).forEach(p => {
      if (!p?.horse_no) return;
      const entry = entriesArr.find(e => e && String(e.horse_no) === String(p.horse_no));
      const odds = (oddsData && typeof oddsData === 'object') ? (oddsData[String(p.horse_no)] || {}) : {};
      const hist = (oddsHistory && typeof oddsHistory === 'object') ? (oddsHistory[String(p.horse_no)] || []) : [];
      const color = COLORS[(p.horse_no || 0) % COLORS.length];
      result.push({ p, entry: entry || null, odds, hist, color });
    });
    // Scratched horses: from currentEntries but not in predictions
    entriesArr.forEach(entry => {
      if (!entry || !entry.horse_no) return;
      if (entry.status === 'Scratched' && !predictionsArr.find(p => p && String(p.horse_no) === String(entry.horse_no))) {
        const odds = (oddsData && typeof oddsData === 'object') ? (oddsData[String(entry.horse_no)] || {}) : {};
        const hist = (oddsHistory && typeof oddsHistory === 'object') ? (oddsHistory[String(entry.horse_no)] || []) : [];
        const color = COLORS[(entry.horse_no || 0) % COLORS.length];
        result.push({ p: null, entry, odds, hist, color, scratched: true });
      }
    });
    return result.sort((a, b) => (a?.entry?.horse_no || 0) - (b?.entry?.horse_no || 0));
  }, [predictions, currentEntries, oddsData, oddsHistory]);

  if (!rows.length) {
    return (
      <div className="ut-empty">
        {!connected ? '等待連接...' : '載入中...'}
      </div>
    );
  }

  return (
    <div className="ut-wrap">
      <table className="ut-table">
        <thead>
          <tr>
            <th>預</th>
            <th>#</th>
            <th>馬匹</th>
            <th>WIN<div className="ut-sub-h">走</div></th>
            <th>PLA<div className="ut-sub-h">走</div></th>
            <th>檔</th>
            <th>評</th>
            <th>近</th>
          </tr>
        </thead>
        <tbody>
          {rows.filter(r => r?.entry?.horse_no).map(({ p, entry, odds, hist, color, scratched }) => (
            <tr key={entry.horse_no} style={scratched ? {opacity: 0.4} : {}}>
              <td className="ut-pred">
                <div className={`rank rank-${p?.predicted_rank}`}>{p ? p.predicted_rank : '—'}</div>
              </td>
              <td className="ut-no">
                <div className="badge" style={{ background: color }}>{entry.horse_no}</div>
              </td>
              <td className="ut-name">
                <div className="ut-horse">{entry.horse_name}{scratched ? ' ✕' : ''}</div>
                <div className="ut-jk">
                  <span>{entry.jockey_name}</span>
                  <span className="ut-tr">{entry.trainer_name}</span>
                </div>
              </td>
              <td className="ut-odds-cell">
                <div className="ut-win-spark"><TinySparkline hist={hist} color="#fbbf24" /></div>
                <div className="ut-odds-val ut-win-val">{fmt(odds.win)}</div>
              </td>
              <td className="ut-odds-cell">
                <div className="ut-pla-spark"><TinySparkline hist={hist} color="#60a5fa" /></div>
                <div className="ut-odds-val ut-pla-val">{fmt(odds.place)}</div>
              </td>
              <td className="ut-draw">{entry?.draw ?? '-'}</td>
              <td className="ut-rating">{entry?.rating_change ?? '-'}</td>
              <td className="ut-recent">{entry?.recent_form ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
