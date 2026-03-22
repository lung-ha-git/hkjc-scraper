import React, { useEffect, useState, useMemo, useCallback } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Bar } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

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

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

// Fetch full history from MongoDB
async function fetchOddsHistory(raceId) {
  const res = await fetch(`${API_BASE}/api/odds/history/${raceId}`);
  if (!res.ok) return null;
  return res.json();
}

export default function OddsPanel({ oddsData, oddsHistory, entries, connected, error, raceId }) {
  const [expanded, setExpanded] = useState(false);
  const [historyData, setHistoryData] = useState(null); // { times, horses }
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedHorses, setSelectedHorses] = useState(new Set()); // which horses to show on chart
  const [chartType, setChartType] = useState('win'); // 'win' or 'place'

  // Load history from MongoDB when raceId changes
  useEffect(() => {
    if (!raceId) return;
    setHistoryData(null);
    setHistoryLoading(true);
    setSelectedHorses(new Set());
    fetchOddsHistory(raceId)
      .then(data => {
        setHistoryData(data);
        setHistoryLoading(false);
      })
      .catch(() => setHistoryLoading(false));
  }, [raceId]);

  // Toggle horse selection for chart
  const toggleHorse = useCallback((horseNo) => {
    setSelectedHorses(prev => {
      const next = new Set(prev);
      if (next.has(horseNo)) next.delete(horseNo);
      else next.add(horseNo);
      return next;
    });
  }, []);

  // Select all / clear all
  const selectAll = () => {
    if (!entries) return;
    setSelectedHorses(new Set(entries.map(e => String(e.horse_no))));
  };

  const clearAll = () => setSelectedHorses(new Set());

  // Build chart data from MongoDB history
  const chartData = useMemo(() => {
    if (!historyData || !historyData.times.length) return null;

    const { times, horses } = historyData;
    const selected = selectedHorses.size > 0 ? Array.from(selectedHorses) : Object.keys(horses).slice(0, 6);
    const oddsKey = chartType; // 'win' or 'place'

    // Sample times: aim for ~60 labels
    const maxBars = 60;
    const step = Math.max(1, Math.floor(times.length / maxBars));
    const sampledIndices = [];
    for (let i = 0; i < times.length; i += step) sampledIndices.push(i);

    const labels = sampledIndices.map(i => formatTime(times[i]));

    // One dataset per selected horse
    const datasets = selected.map((h, i) => {
      const color = HORSE_COLORS[Number(h) % HORSE_COLORS.length];
      const values = sampledIndices.map(idx => {
        const arr = horses[h]?.[oddsKey] || [];
        return arr[idx] ?? null;
      });
      return {
        label: `No.${h}`,
        data: values,
        backgroundColor: color + 'CC',
        borderColor: color,
        borderWidth: 1,
        borderRadius: 2,
      };
    });

    return { labels, datasets };
  }, [historyData, selectedHorses, chartType]);

  const chartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 0 },
    plugins: {
      legend: {
        display: true,
        position: 'bottom',
        labels: {
          boxWidth: 12,
          font: { size: 10 },
          color: '#ccc',
        },
      },
      tooltip: {
        callbacks: {
          title: (items) => {
            const idx = items[0]?.dataIndex;
            if (idx == null || !historyData) return '';
            return new Date(historyData.times[idx]).toLocaleString();
          },
          label: (ctx) => `${ctx.dataset.label} ${chartType.toUpperCase()}: ${formatOdds(ctx.raw)}`,
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#888',
          font: { size: 9 },
          maxRotation: 45,
          autoSkip: true,
          maxTicksLimit: 20,
        },
        grid: { color: '#333' },
      },
      y: {
        ticks: {
          color: '#888',
          font: { size: 10 },
          callback: v => formatOdds(v),
        },
        grid: { color: '#333' },
        title: {
          display: true,
          text: chartType === 'win' ? 'WIN 賠率' : 'PLACE 賠率',
          color: '#888',
          font: { size: 11 },
        },
      },
    },
  }), [chartType, historyData]);

  // Sorted entries
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
        {raceId && <div className="race-id-label">{raceId}</div>}
      </div>

      {!connected && !error && (
        <div className="odds-connecting">正在連接即時數據...</div>
      )}

      {error && (
        <div className="connection-error">連接錯誤: {error}</div>
      )}

      {/* Full-width bar chart */}
      {expanded && (
        <div className="odds-fullchart">
          <div className="odds-chart-controls">
            <div className="chart-type-toggle">
              <button
                className={chartType === 'win' ? 'active' : ''}
                onClick={() => setChartType('win')}
              >WIN</button>
              <button
                className={chartType === 'place' ? 'active' : ''}
                onClick={() => setChartType('place')}
              >PLACE</button>
            </div>
            <div className="chart-horse-controls">
              <button onClick={selectAll} className="btn-sm">全選</button>
              <button onClick={clearAll} className="btn-sm">清除</button>
            </div>
            {historyData && (
              <span className="chart-info">
                {historyData.times.length} 筆 / {selectedHorses.size || '全部'} 匹馬
              </span>
            )}
          </div>

          <div className="odds-chart-container" style={{ height: 280 }}>
            {historyLoading && <div className="odds-chart-empty">載入歷史數據中...</div>}
            {!historyLoading && !chartData && <div className="odds-chart-empty">暫無歷史數據</div>}
            {!historyLoading && chartData && (
              <Bar data={chartData} options={chartOptions} />
            )}
          </div>

          {/* Horse toggles */}
          {!historyLoading && historyData && (
            <div className="odds-horse-toggles">
              {sortedEntries.map(entry => {
                const hk = String(entry.horse_no);
                const isSelected = selectedHorses.has(hk);
                const color = HORSE_COLORS[entry.horse_no % HORSE_COLORS.length];
                return (
                  <button
                    key={hk}
                    className={`horse-toggle ${isSelected ? 'selected' : ''}`}
                    style={{
                      backgroundColor: isSelected ? color : 'transparent',
                      borderColor: color,
                      color: isSelected ? '#fff' : color,
                    }}
                    onClick={() => toggleHorse(hk)}
                  >
                    {entry.horse_no}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Odds table */}
      <div className="odds-table">
        <div className="odds-table-header">
          <div className="odds-col-no">#</div>
          <div className="odds-col-name">馬匹</div>
          <div className="odds-col-win">WIN</div>
          <div className="odds-col-place">PLACE</div>
          <div className="odds-col-toggle">
            <button
              className="expand-btn"
              onClick={() => setExpanded(e => !e)}
              title={expanded ? '收合' : '展開圖表'}
            >
              {expanded ? '▲ 圖表' : '📊 圖表'}
            </button>
          </div>
        </div>

        {sortedEntries.map((entry, idx) => {
          const hk = String(entry.horse_no);
          const odds = oddsData[hk];
          const isSelected = selectedHorses.has(hk);
          const color = HORSE_COLORS[entry.horse_no % HORSE_COLORS.length];

          return (
            <div
              key={hk}
              className={`odds-row ${isSelected ? 'highlighted' : ''}`}
              style={isSelected ? { borderLeftColor: color } : {}}
            >
              <div className="odds-row-main">
                <div className="odds-horse-no" style={{ backgroundColor: color }}>
                  {entry.horse_no}
                </div>
                <div className="odds-horse-name">{entry.horse_name}</div>
                <div className="odds-value win">
                  <span className="odds-num">{formatOdds(odds?.win)}</span>
                </div>
                <div className="odds-value place">
                  <span className="odds-num">{formatOdds(odds?.place)}</span>
                </div>
                <button
                  className={`odds-select-btn ${isSelected ? 'selected' : ''}`}
                  style={{ borderColor: color, color: isSelected ? '#fff' : color }}
                  onClick={() => toggleHorse(hk)}
                  title={isSelected ? '移除圖表' : '加入圖表'}
                >
                  {isSelected ? '✓' : '+'}
                </button>
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
