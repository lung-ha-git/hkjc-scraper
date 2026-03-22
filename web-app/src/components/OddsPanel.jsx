import React, { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

// Color palette for horses
const HORSE_COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
  '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
  '#F8B500', '#82E0AA', '#F1948A', '#7DCEA0'
];

function formatOdds(val) {
  if (val == null || val === '') return '-';
  return parseFloat(val).toFixed(2);
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
}

// Mini line chart for a single horse
function HorseOddsChart({ history, color }) {
  const data = useMemo(() => {
    if (!history || history.length === 0) {
      return { labels: [], datasets: [] };
    }
    
    // Downsample to max 20 points for performance
    const points = history.length > 20
      ? history.filter((_, i) => i % Math.ceil(history.length / 20) === 0)
      : history;

    return {
      labels: points.map(p => formatTime(p.time)),
      datasets: [
        {
          label: 'WIN',
          data: points.map(p => p.win),
          borderColor: color,
          backgroundColor: color + '20',
          fill: true,
          tension: 0.3,
          pointRadius: 2,
          borderWidth: 1.5,
        },
        {
          label: 'PLACE',
          data: points.map(p => p.place),
          borderColor: color + '99',
          backgroundColor: 'transparent',
          fill: false,
          tension: 0.3,
          pointRadius: 2,
          borderWidth: 1.5,
          borderDash: [4, 4],
        },
      ],
    };
  }, [history, color]);

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 0 },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => `${ctx.dataset.label}: ${formatOdds(ctx.raw)}`,
        },
      },
    },
    scales: {
      x: {
        display: false,
      },
      y: {
        display: true,
        ticks: {
          font: { size: 9 },
          color: '#888',
          callback: (v) => formatOdds(v),
        },
        grid: { color: '#eee' },
      },
    },
  }), []);

  if (!history || history.length === 0) {
    return <div className="odds-chart-empty">等待數據...</div>;
  }

  return (
    <div style={{ height: '70px', width: '100%' }}>
      <Line data={data} options={options} />
    </div>
  );
}

// Single horse row with odds + mini chart
function HorseOddsRow({ horse, odds, history, colorIndex, isExpanded, onToggle }) {
  const color = HORSE_COLORS[colorIndex % HORSE_COLORS.length];
  
  return (
    <div className={`odds-row ${isExpanded ? 'expanded' : ''}`}>
      <div className="odds-row-main" onClick={onToggle}>
        <div className="odds-horse-no" style={{ backgroundColor: color }}>
          {horse.horse_no}
        </div>
        <div className="odds-horse-name">{horse.horse_name}</div>
        <div className="odds-value win">
          <span className="odds-label">W</span>
          <span className="odds-num">{formatOdds(odds?.win)}</span>
        </div>
        <div className="odds-value place">
          <span className="odds-label">P</span>
          <span className="odds-num">{formatOdds(odds?.place)}</span>
        </div>
        <div className="odds-toggle">{isExpanded ? '▲' : '▼'}</div>
      </div>
      
      {isExpanded && (
        <div className="odds-row-chart">
          <HorseOddsChart history={history} color={color} />
        </div>
      )}
    </div>
  );
}

export default function OddsPanel({ oddsData, oddsHistory, entries, connected, error, raceId }) {
  const [expandedHorses, setExpandedHorses] = React.useState({});

  const toggleHorse = (horseNo) => {
    setExpandedHorses(prev => ({
      ...prev,
      [horseNo]: !prev[horseNo]
    }));
  };

  // Get entries sorted by horse_no
  const sortedEntries = useMemo(() => {
    if (!entries) return [];
    return [...entries].sort((a, b) => a.horse_no - b.horse_no);
  }, [entries]);

  if (error) {
    return (
      <div className="odds-panel">
        <div className="odds-panel-header">
          <h3>📈 即時賠率</h3>
          <span className="connection-error">連接錯誤: {error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="odds-panel">
      <div className="odds-panel-header">
        <h3>📈 即時賠率</h3>
        <div className="connection-status">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          {connected ? '已連接' : '連接中...'}
        </div>
        {raceId && <div className="race-id-label">{raceId}</div>}
      </div>

      {!connected && !error && (
        <div className="odds-connecting">正在連接即時數據...</div>
      )}

      <div className="odds-table">
        <div className="odds-table-header">
          <div className="odds-col-no">#</div>
          <div className="odds-col-name">馬匹</div>
          <div className="odds-col-win">WIN</div>
          <div className="odds-col-place">PLACE</div>
          <div className="odds-col-toggle"></div>
        </div>

        {sortedEntries.map((entry, idx) => {
          // Normalize horse_no to string key (JSON always converts numeric object keys to strings)
          const horseNoKey = String(entry.horse_no);
          const odds = oddsData[horseNoKey];
          const history = oddsHistory[horseNoKey] || [];
          const isExpanded = expandedHorses[horseNoKey] || false;

          return (
            <HorseOddsRow
              key={horseNoKey}
              horse={entry}
              odds={odds}
              history={history}
              colorIndex={idx}
              isExpanded={isExpanded}
              onToggle={() => toggleHorse(horseNoKey)}
            />
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
