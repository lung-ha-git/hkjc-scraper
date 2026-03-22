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
    if (!predictions || !currentEntries) return [];
    return predictions.slice().sort((a, b) => a.horse_no - b.horse_no).map(p => {
      const entry = currentEntries.find(e => e.horse_no === p.horse_no);
      const odds = oddsData[String(p.horse_no)] || {};
      const hist = oddsHistory[String(p.horse_no)] || [];
      const color = COLORS[p.horse_no % COLORS.length];
      return { p, entry, odds, hist, color };
    });
  }, [predictions, currentEntries, oddsData, oddsHistory]);

  if (!rows.length) {
    return (
      <div className="ut-empty">
        {connected ? '載入中...' : '等待連接...'}
      </div>
    );
  }

  return (
    <div className="ut-wrap">
      <table className="ut-table">
        <thead>
          <tr>
            <th>#</th>
            <th>WIN</th>
            <th>PLA</th>
            <th className="ut-name-col">馬匹 / 騎師 / 練馬師</th>
            <th>檔</th>
            <th>評</th>
            <th>近</th>
            <th>預</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ p, entry, odds, hist, color }) => (
            <tr key={p.horse_no}>
              <td className="ut-no">
                <div className="badge" style={{ background: color }}>{p.horse_no}</div>
              </td>
              <td className="ut-win">
                <div className="ut-odds">{fmt(odds.win)}</div>
                <TinySparkline hist={hist} color="#fbbf24" />
              </td>
              <td className="ut-pla">
                <div className="ut-odds">{fmt(odds.place)}</div>
                <TinySparkline hist={hist} color="#60a5fa" />
              </td>
              <td className="ut-name">
                <div className="ut-horse">{p.horse_name}</div>
                <div className="ut-jk">{p.jockey_name}</div>
                <div className="ut-tr">{p.trainer_name}</div>
              </td>
              <td className="ut-draw">{entry?.draw ?? '-'}</td>
              <td className="ut-rating">{entry?.rating_change || '-'}</td>
              <td className="ut-recent">{entry?.recent_form || '-'}</td>
              <td className="ut-pred">
                <div className={`rank rank-${p.predicted_rank}`}>{p.predicted_rank}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
