import React, { useState, useEffect, useRef, useMemo } from 'react';
import axios from 'axios';
import './index.css';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import UnifiedRaceTable from './components/UnifiedRaceTable';
import { useOddsSocket } from './hooks/useOddsSocket';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement);

// Fallback colors when no jersey_url
const JERSEY_COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
  '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
  '#F8B500', '#82E0AA', '#F1948A', '#7DCEA0'
];

function App() {
  const [fixtures, setFixtures] = useState([]);
  const [selectedFixture, setSelectedFixture] = useState(null);
  const [racecardData, setRacecardData] = useState(null);
  const [selectedRaceNo, setSelectedRaceNo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [predictions, setPredictions] = useState([]);
  const [predicting, setPredicting] = useState(false);
  const [raceConfidence, setRaceConfidence] = useState(null);
  const [showBoost, setShowBoost] = useState(false);
  
  // Feature boosting factors (0.0 = off, 1.0 = normal, 3.0 = 3x boost)
  const [boosting, setBoosting] = useState({
    distance: 1.0,
    jockey: 1.0,
    recent: 1.0,
    track: 1.0,
    draw: 1.0,
    career: 1.0,
    trainer: 1.0,
    best_time: 1.0,
    pace: 1.0,
  });
  
  // Debounced re-predict when boosting sliders change
  const predictControllerRef = useRef(null);
  const lastPredictRef = useRef(0);

  const cancelPendingPredict = () => {
    if (predictControllerRef.current) {
      predictControllerRef.current.abort();
      predictControllerRef.current = null;
    }
  };

  useEffect(() => {
    fetchFixtures();
  }, []);

  // Restore selected race from localStorage when fixtures load
  useEffect(() => {
    if (fixtures.length > 0 && !selectedFixture) {
      const stored = localStorage.getItem('hkjc_selectedRaceNo');
      const storedDate = localStorage.getItem('hkjc_selectedDate');
      const storedVenue = localStorage.getItem('hkjc_selectedVenue');
      const fixture = fixtures[0];

      if (stored && storedDate === fixture.date && storedVenue === fixture.venue) {
        // Restore to stored race if date/venue match
        setSelectedFixture(fixture);
        setSelectedRaceNo(parseInt(stored));
      } else {
        setSelectedFixture(fixtures[0]);
      }
    }
  }, [fixtures]);

  useEffect(() => {
    cancelPendingPredict();
    if (selectedFixture) {
      setSelectedRaceNo(null);
      fetchRacecards();
    }
  }, [selectedFixture]);

  // Persist selected race to localStorage on change
  useEffect(() => {
    if (selectedRaceNo && selectedFixture) {
      localStorage.setItem('hkjc_selectedRaceNo', String(selectedRaceNo));
      localStorage.setItem('hkjc_selectedDate', selectedFixture.date);
      localStorage.setItem('hkjc_selectedVenue', selectedFixture.venue);
    }
  }, [selectedRaceNo, selectedFixture]);

  // Compute race ID for WebSocket subscription
  const raceId = selectedFixture && selectedRaceNo
    ? `${selectedFixture.date}_${selectedFixture.venue}_R${selectedRaceNo}`
    : null;

  // FEAT-010: clear predictions + racecard on race change
  useEffect(() => {
    if (!raceId) return;
    setPredictions([]);
    setRaceConfidence(null);
  }, [raceId]);

  // WebSocket for real-time odds
  const { oddsData, oddsHistory, connected, error: oddsError } = useOddsSocket(raceId);

  const fetchFixtures = async () => {
    try {
      const res = await axios.get('/api/fixtures');
      if (!res.data || res.data.length === 0) { setLoading(false); return; }
      // Parallel check dates to find one with racecards
      const datesToTry = [...new Set([
        ...res.data.slice(0, 5).map(f => f.date)
      ])].slice(0, 8);
      const results = await Promise.all(
        datesToTry.map(d => axios.get(`/api/racecards?date=${d}`).then(r => ({
          date: d, hasData: !!(r.data?.racecards?.length > 0)
        })).catch(() => ({ date: d, hasData: false })))
      );
      const match = results.find(r => r.hasData);
      const pick = match
        ? res.data.find(f => f.date === match.date) || { date: match.date, venue: 'ST' }
        : res.data[0];
      setFixtures([pick]);
      setSelectedFixture(pick);
      setLoading(false);
    } catch (error) {
      console.log('Error fetching fixtures:', error);
      setLoading(false);
    }
  };

  const fetchRacecards = async () => {
    if (!selectedFixture) return;
    try {
      const res = await axios.get(`/api/racecards?date=${selectedFixture.date}`);
      setRacecardData(res.data);
      if (res.data.racecards && res.data.racecards.length > 0) {
        setSelectedRaceNo(res.data.racecards[0].race_no);
      }
    } catch (error) {
      console.log('Error fetching racecards:', error);
      setRacecardData(null);
    }
  };

  // Calculate predictions when race changes
  useEffect(() => {
    if (racecardData && selectedRaceNo) {
      lastPredictRef.current = 0;
      setRaceConfidence(null);
      calculatePredictions();
    }
  }, [selectedRaceNo]);

  // Auto-save prediction to MongoDB when predictions change (debounced)
  const saveTimerRef = useRef(null);
  useEffect(() => {
    if (predictions.length > 0 && selectedFixture && selectedRaceNo) {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => savePrediction(), 2000);
    }
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); };
  }, [predictions]);

  const fetchHorseDetails = async () => {
    // Jersey URLs are now included in racecard API response
    // No additional fetch needed
  };

  const handleBoostChange = (key, val) => {
    setBoosting(b => ({...b, [key]: val}));
    calculatePredictions();
  };

  const THROTTLE_MS = 600;

  const calculatePredictions = () => {
    if (!selectedFixture || !selectedRaceNo) return;
    const now = Date.now();
    if (now - lastPredictRef.current < THROTTLE_MS) return;
    lastPredictRef.current = now;
    
    cancelPendingPredict();
    const controller = new AbortController();
    predictControllerRef.current = controller;
    
    const activeBoost = {};
    Object.entries(boosting).forEach(([group, val]) => {
      if (val !== 1.0) activeBoost[group] = val;
    });
    const boostArg = Object.keys(activeBoost).length > 0 ? encodeURIComponent(JSON.stringify(activeBoost)) : '';
    const url = `/api/predict?race_date=${selectedFixture.date}&race_no=${selectedRaceNo}&venue=${selectedFixture.venue}${boostArg ? '&boosting=' + boostArg : ''}`;
    
    setPredicting(true);
    fetch(url, { signal: controller.signal }).then(res => res.json())
      .then(data => {
        setPredicting(false);
        if (data && data.predictions) {
          setRaceConfidence(data.race_confidence != null ? data.race_confidence : null);
          // Add jersey_url, horse_no from racecard data
          const entries = racecardData.entries?.filter(e => e.race_no === selectedRaceNo) || [];
          const results = data.predictions.map(pred => {
            const entry = entries.find(e => e.horse_name === pred.horse_name);
            return {
              ...pred,
              jockey_name: pred.jockey || entry?.jockey_name || '',
              trainer_name: pred.trainer || entry?.trainer_name || '',
              horse_no: entry?.horse_no || 0,
              jersey_url: entry?.jersey_url || null,
              rating_change: entry?.rating_change || null,
              recent_form: entry?.recent_form || null
            };
          });
          
          // Sort by horse_no for display in table
          results.sort((a, b) => a.horse_no - b.horse_no);
          setPredictions(results);
        }
      })
      .catch(err => {
        console.error('Prediction error:', err);
      });
  };

  const handleRaceTabClick = (raceNo) => {
    setSelectedRaceNo(raceNo);
  };

  const savePrediction = async () => {
    if (!selectedFixture || !selectedRaceNo || predictions.length === 0) return;
    
    // Get current racecard data
    const currentRace = racecardData?.racecards?.find(rc => rc.race_no === selectedRaceNo);
    const currentEntries = racecardData?.entries?.filter(e => e.race_no === selectedRaceNo) || [];
    
    try {
      await axios.post('/api/predictions', {
        race_date: selectedFixture.date,
        race_no: selectedRaceNo,
        venue: selectedFixture.venue,
        predictions: predictions,
        boosting: {...boosting},
        racecard: currentRace ? {...currentRace} : null,
        entries: currentEntries.map(e => ({ horse_no: e.horse_no, horse_name: e.horse_name, draw: e.draw })),
        model_version: 'xgb_v1',
        created_at: new Date().toISOString()
      });
    } catch (error) {
      console.error('Error saving prediction:', error);
    }
  };

  // 獲取馬匹 Icon - use jersey_url from predictions directly
  // Inline sparkline for desktop table
  function DtSparkline({ history, color }) {
    const data = useMemo(() => {
      if (!history || history.length < 2) return null;
      const maxPts = 15;
      const step = Math.max(1, Math.floor(history.length / maxPts));
      const pts = history.filter((_, i) => i % step === 0);
      return {
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
    }, [history, color]);
    if (!data) return <div style={{ height: 20 }} />;
    return (
      <div className="dt-spark-wrap">
        <div style={{ width: 32, height: 20 }}>
          <Line data={data} options={{
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 0 },
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { x: { display: false }, y: { display: false } },
          }} />
        </div>
      </div>
    );
  }

  const getJerseyInfo = (horseNo, horseName) => {
    // Find prediction entry for this horse
    const pred = predictions.find(p => p.horse_no === horseNo && p.horse_name === horseName);
    if (pred?.jersey_url) {
      return { type: 'image', url: pred.jersey_url };
    }
    // Fallback to color
    return { type: 'color', value: JERSEY_COLORS[(horseNo - 1) % JERSEY_COLORS.length] };
  };

  if (loading) {
    return (
      <div className="app">
        <div className="loading">載入中...</div>
      </div>
    );
  }

  const currentRaceCards = racecardData?.racecards?.find(rc => rc.race_no === selectedRaceNo);
  const currentEntries = racecardData?.entries?.filter(e => e.race_no === selectedRaceNo) || [];

  return (
    <div className="app">
      <header className="header">
        <h1>🏇 HKJC AI 預測</h1>
        {selectedFixture && (
          <span className="date">
            {selectedFixture.date} - {selectedFixture.venue === 'ST' ? '沙田' : '跑馬地'}
          </span>
        )}
      </header>

      <div className="main-layout">
        {/* 中間：排位表 */}
        <div className="race-card">
          {selectedFixture && racecardData && selectedRaceNo && (
            <>
              <div className="race-header">
                <div className="race-header-top">
                  <h2>{selectedFixture.date} - {selectedFixture.venue === 'ST' ? '沙田' : '跑馬地'}</h2>
                  {raceConfidence != null && (
                    <span className={`conf-badge ${raceConfidence > 65 ? 'high' : raceConfidence >= 55 ? 'medium' : 'low'}`}>
                      {raceConfidence}
                    </span>
                  )}
                </div>
                <div className="race-info">
                  <span>第 {selectedRaceNo} 場</span>
                  <span>{currentRaceCards?.distance || '-'}m</span>
                  <span>{currentRaceCards?.class || '-'}</span>
                </div>
              </div>
              
              <div className="race-tabs-wrapper">
                <div className="race-tabs">
                  {racecardData.racecards?.map(rc => (
                  <button 
                    key={rc.race_no} 
                    className={`race-tab ${selectedRaceNo === rc.race_no ? 'active' : ''}`}
                    onClick={() => handleRaceTabClick(rc.race_no)}
                  >
                    R{rc.race_no}
                  </button>
                ))}
                </div>
                {raceConfidence != null && (
                  <div className={`conf-tab-badge ${raceConfidence > 65 ? 'high' : raceConfidence >= 55 ? 'medium' : 'low'}`}>
                    信心 {raceConfidence}
                  </div>
                )}
              </div>
              
              <table className="race-table">
                <thead>
                  <tr>
                    <th className="mobile-only">馬號</th>
                    <th className="mobile-only">馬匹</th>
                    <th className="mobile-only">騎師</th>
                    <th className="mobile-only">練馬師</th>
                    <th className="mobile-only">檔位</th>
                    <th className="desktop-only">預測</th>
                    <th className="desktop-only">馬號</th>
                    <th className="desktop-only">馬匹</th>
                    <th className="desktop-only">騎師</th>
                    <th className="desktop-only">練馬師</th>
                    <th className="desktop-only">檔位</th>
                    <th className="desktop-only dt-odds-th dt-win-th">
                      WIN<span className="dt-odds-sub">走·值</span>
                    </th>
                    <th className="desktop-only dt-odds-th dt-pla-th">
                      PLA<span className="dt-odds-sub">走·值</span>
                    </th>
                    <th className="desktop-only">評分</th>
                    <th className="desktop-only">近績</th>
                  </tr>
                </thead>
                <tbody>
                  {predictions
                    .slice()
                    .sort((a, b) => a.horse_no - b.horse_no)
                    .map((pred) => {
                    const entry = currentEntries.find(e => e.horse_no === pred.horse_no);
                    const jersey = getJerseyInfo(pred.horse_no, pred.horse_name);
                    return (
                      <tr key={pred.horse_no}>
                        {/* Mobile: 馬號, 馬匹 */}
                        <td className="mobile-only">
                          <div 
                            className="horse-number"
                            style={{ backgroundColor: jersey.type === 'color' ? jersey.value : '#888' }}
                          >
                            {pred.horse_no}
                          </div>
                        </td>
                        <td className="mobile-only">
                          <div className="horse-name-cell">
                            {jersey.type === 'image' ? (
                              <img src={jersey.url} alt={pred.horse_no} className="jersey-icon" />
                            ) : (
                              <div className="jersey-placeholder" style={{ backgroundColor: jersey.value }}>
                                {pred.horse_no}
                              </div>
                            )}
                            <span>{pred.horse_name}</span>
                          </div>
                        </td>
                        <td className="mobile-only">{pred.jockey_name}</td>
                        <td className="mobile-only">{pred.trainer_name}</td>
                        <td className="mobile-only">{pred.draw}</td>
                        
                        {/* Desktop: 預測, 馬號, 馬匹, 騎師, 練馬師, 檔位, 評分, 近績 */}
                        <td className="desktop-only">
                          <div className={`predicted-rank rank-${pred.predicted_rank}`}>
                            {pred.predicted_rank}
                          </div>
                        </td>
                        <td className="desktop-only">
                          <div 
                            className="horse-number"
                            style={{ backgroundColor: jersey.type === 'color' ? jersey.value : '#888' }}
                          >
                            {pred.horse_no}
                          </div>
                        </td>
                        <td className="desktop-only">
                          <div className="horse-name-cell">
                            {jersey.type === 'image' ? (
                              <img src={jersey.url} alt={pred.horse_no} className="jersey-icon" />
                            ) : (
                              <div className="jersey-placeholder" style={{ backgroundColor: jersey.value }}>
                                {pred.horse_no}
                              </div>
                            )}
                            <span>{pred.horse_name}</span>
                          </div>
                        </td>
                        <td className="desktop-only">{pred.jockey_name}</td>
                        <td className="desktop-only">{pred.trainer_name}</td>
                        <td className="desktop-only">{pred.draw}</td>
                        <td className="desktop-only dt-odds-cell">
                          <DtSparkline
                            history={oddsHistory[String(pred.horse_no)] || []}
                            color="#fbbf24"
                          />
                          <div className="dt-odds-val dt-win-val">
                            {oddsData[String(pred.horse_no)]?.win != null
                              ? parseFloat(oddsData[String(pred.horse_no)].win).toFixed(2)
                              : '-'}
                          </div>
                        </td>
                        <td className="desktop-only dt-odds-cell">
                          <DtSparkline
                            history={oddsHistory[String(pred.horse_no)] || []}
                            color="#60a5fa"
                          />
                          <div className="dt-odds-val dt-pla-val">
                            {oddsData[String(pred.horse_no)]?.place != null
                              ? parseFloat(oddsData[String(pred.horse_no)].place).toFixed(2)
                              : '-'}
                          </div>
                        </td>
                        <td className="desktop-only">{entry?.rating_change || '-'}</td>
                        <td className="desktop-only">{entry?.recent_form || '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
          {selectedFixture && !racecardData && (
            <div className="loading">載入排位表中...</div>
          )}
        </div>

        {/* 右側：AI 預測控制面板（2-column layout，不再需要 odds-panel 列） */}
        <div className="prediction-panel">
          <h3>📊 AI 預測 {predicting && <span className="predicting-spinner">⟳</span>}</h3>
          {raceConfidence != null && (
            <div className="confidence-badge">
              <span className="confidence-label">信心指數</span>
              <span className={`confidence-value ${raceConfidence > 65 ? 'high' : raceConfidence >= 55 ? 'medium' : 'low'}`}>
                {raceConfidence}
              </span>
            </div>
          )}
          
          <button className="boost-toggle" onClick={() => setShowBoost(!showBoost)}>
            {showBoost ? '🔼 隱藏' : '🔽 因子調整'}
          </button>
          
          {showBoost && (
            <div className="boost-panel">
              <div className="boost-title">因子調整（0=關閉，1=正常，3=3倍）</div>
              {[
                {key: 'distance', label: '🏇 路程成績'},
                {key: 'jockey', label: '🧑‍✈️ 騎師/組合'},
                {key: 'recent', label: '📊 近績'},
                {key: 'track', label: '🌱 跑道/狀況'},
                {key: 'draw', label: '📍 檔位'},
                {key: 'career', label: '🏆 歷史戰績'},
                {key: 'trainer', label: '👤 練馬師'},
                {key: 'best_time', label: '⏱ 最快時間'},
                {key: 'pace', label: '⚡ 前中後段速'},
              ].map(({key, label}) => (
                <div className="boost-row" key={key}>
                  <span className="boost-label">{label}</span>
                  <input
                    type="range"
                    min="0" max="3" step="0.1"
                    value={boosting[key]}
                    onChange={e => handleBoostChange(key, parseFloat(e.target.value))}
                  />
                  <span className="boost-val">{boosting[key].toFixed(1)}x</span>
                  <button className="boost-reset" onClick={() => handleBoostChange(key, 1.0)}>↺</button>
                </div>
              ))}
              <button className="boost-reset-all" onClick={() => {
                const reset = Object.fromEntries(Object.keys(boosting).map(k => [k, 1.0]));
                setBoosting(reset);
                setTimeout(() => calculatePredictions(), 50);
              }}>
                ↺ 重置全部
              </button>
            </div>
          )}
          
          <div className="prediction-list">
            {predictions
              .sort((a,b) => a.predicted_rank - b.predicted_rank)
              .map((pred, idx) => {
              const jersey = getJerseyInfo(pred.horse_no, pred.horse_name);
              return (
                <div key={idx} className="prediction-item top-4">
                  <div className={`predicted-rank rank-${pred.predicted_rank}`}>
                    {pred.predicted_rank}
                  </div>
                  <div 
                    className="horse-number"
                    style={{ backgroundColor: jersey.type === 'color' ? jersey.value : '#888' }}
                  >
                    {pred.horse_no}
                  </div>
                  <div className="prediction-details">
                    <div className="horse-name-cell">
                      {jersey.type === 'image' ? (
                        <img src={jersey.url} alt={pred.horse_no} className="jersey-icon" />
                      ) : null}
                      {pred.horse_name}
                    </div>
                    <div className="prediction-jockey">{pred.jockey_name}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

      </div>

      {/* Mobile unified table (outside main-layout, controlled by CSS */}
      <div className="unified-table-wrap">
        <div className="ut-race-tabs">
          {racecardData?.racecards?.map(rc => (
            <button
              key={rc.race_no}
              className={`ut-race-tab ${selectedRaceNo === rc.race_no ? 'active' : ''}`}
              onClick={() => setSelectedRaceNo(rc.race_no)}
            >
              R{rc.race_no}
            </button>
          ))}
        </div>
        <div className="ut-mobile-header">
          <span>第 {selectedRaceNo || '-'} 場</span>
          <span>{currentRaceCards?.distance ? `${currentRaceCards.distance}m` : ''}</span>
          {raceConfidence != null && (
            <span className={`conf-dot ${raceConfidence > 65 ? 'high' : raceConfidence >= 55 ? 'medium' : 'low'}`}>
              信心 {raceConfidence}
            </span>
          )}
        </div>
        <UnifiedRaceTable
          predictions={predictions}
          currentEntries={currentEntries}
          oddsData={oddsData}
          oddsHistory={oddsHistory}
          connected={connected}
        />

        {/* Mobile: AI factor adjustment */}
        <div className="mob-boost">
          <button className="mob-boost-toggle" onClick={() => setShowBoost(!showBoost)}>
            {showBoost ? '🔼 隱藏因子' : '🔽 因子調整'}
          </button>
          {showBoost && (
            <div className="mob-boost-panel">
              {[
                {key: 'distance', label: '🏇 路程'},
                {key: 'jockey', label: '🧑‍✈️ 騎師'},
                {key: 'recent', label: '📊 近績'},
                {key: 'track', label: '🌱 跑道'},
                {key: 'draw', label: '📍 檔位'},
                {key: 'career', label: '🏆 歷史'},
                {key: 'trainer', label: '👤 練馬師'},
                {key: 'best_time', label: '⏱ 最快'},
                {key: 'pace', label: '⚡ 段速'},
              ].map(({key, label}) => (
                <div key={key} className="mob-boost-row">
                  <span className="mob-boost-label">{label}</span>
                  <input
                    type="range"
                    min="0" max="3" step="0.1"
                    value={boosting[key]}
                    onChange={e => handleBoostChange(key, parseFloat(e.target.value))}
                  />
                  <span className="mob-boost-val">{boosting[key].toFixed(1)}</span>
                </div>
              ))}
              <button className="mob-boost-reset" onClick={() => {
                const reset = Object.fromEntries(Object.keys(boosting).map(k => [k, 1.0]));
                setBoosting(reset);
              }}>重置</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
