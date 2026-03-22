import React, { useEffect, useState, useMemo } from 'react';
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

const API_BASE = window.location.origin;

const HORSE_COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
  '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
  '#F8B500', '#82E0AA', '#F1948A', '#7DCEA0',
  '#AED6F1', '#D7BDE2'
];

function formatOdds(v) {
  if (v == null || v === '') return '-';
  return parseFloat(v).toFixed(2);
}

// Inline sparkline for one horse — renders in the table row
function HorseSparkline({ history, color, type }) {
  const data = useMemo(() => {
    if (!history || history.length < 2) return null;
    // Downsample to max 20 points for performance
    const maxPts = 20;
    const step = Math.max(1, Math.floor(history.length / maxPts));
    const pts = history.filter((_, i) => i % step === 0);
    return {
      labels: pts.map(() => ''),
      datasets: [{
        data: pts.map(p => type === 'win' ? p.win : p.place),
        borderColor: color,
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: false,
      }]
    };
  }, [history, color, type]);

  if (!data) return <div className="sparkline-empty">-</div>;

  return (
    <div className="sparkline-wrap">
      <Line
        data={data}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 0 },
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: {
            x: { display: false },
            y: { display: false },
          },
          elements: { line: { borderCapStyle: 'round' } },
        }}
      />
    </div>
  );
}

export default function OddsPanel({ oddsData, oddsHistory, entries, connected, error, raceId }) {
  const [historyData, setHistoryData] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Fetch full history from MongoDB
  useEffect(() => {
    if (!raceId) return;
    setHistoryLoading(true);
    fetch(`${API_BASE}/api/odds/history/${raceId}`)
      .then(r => r.json())
      .then(data => {
        setHistoryData(data);
        setHistoryLoading(false);
      })
      .catch(() => setHistoryLoading(false));
  }, [raceId]);

  const sortedEntries = useMemo(() => {
    if (!entries) return [];
    return [...entries].sort((a, b) => a.horse_no - b.horse_no);
  }, [entries]);

  return (
    <div className="odds-panel">
      <div className="odds-panel-header">
        <h3>📈 即時賠率</h3>
        <div className="connection-status">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          {connected ? '已連接' : '連接中...'}
        </div>
        {historyLoading && <span className="history-loading">載入歷史...</span>}
        {raceId && <div className="race-id-label">{raceId}</div>}
      </div>

      {error && <div className="connection-error">連接錯誤: {error}</div>}

      <div className="odds-table">
        {/* Header row */}
        <div className="odds-table-header">
          <div className="odds-col-no">#</div>
          <div className="odds-col-name">馬匹</div>
          <div className="odds-col-spark">WIN趨勢</div>
          <div className="odds-col-win">WIN</div>
          <div className="odds-col-spark">PLACE趨勢</div>
          <div className="odds-col-place">PLACE</div>
        </div>

        {sortedEntries.map((entry) => {
          const hk = String(entry.horse_no);
          const odds = oddsData[hk];
          const color = HORSE_COLORS[entry.horse_no % HORSE_COLORS.length];
          // Get this horse's history from MongoDB data
          const horseHistory = historyData?.horses?.[hk] || [];

          return (
            <div key={hk} className="odds-row">
              <div className="odds-row-main">
                <div className="odds-horse-no" style={{ backgroundColor: color }}>
                  {entry.horse_no}
                </div>
                <div className="odds-horse-name">{entry.horse_name}</div>
                <div className="odds-col-spark">
                  <HorseSparkline
                    history={horseHistory}
                    color={color}
                    type="win"
                  />
                </div>
                <div className="odds-value win">
                  <span className="odds-num">{formatOdds(odds?.win)}</span>
                </div>
                <div className="odds-col-spark">
                  <HorseSparkline
                    history={horseHistory}
                    color={color}
                    type="place"
                  />
                </div>
                <div className="odds-value place">
                  <span className="odds-num">{formatOdds(odds?.place)}</span>
                </div>
              </div>
            </div>
          );
        })}

        {sortedEntries.length === 0 && connected && (
          <div className="odds-empty">暫無馬匹數據</div>
        )}
        {sortedEntries.length === 0 && !connected && (
          <div className="odds-empty">等待連接...</div>
        )}
      </div>
    </div>
  );
}
