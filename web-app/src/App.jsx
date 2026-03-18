import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './index.css';

// Fallback colors when no jersey_url
const JERSEY_COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
  '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
  '#F8B500', '#82E0AA', '#F1948A', '#7DCEA0'
];

// AI 預測因子 - 繁體中文
const DEFAULT_WEIGHTS = {
  hj_win_rate: 10,
  career_place_rate: 5,
  jockey_win_rate: 3,
  trainer_win_rate: 2,
  dist_win_rate: 2,
  recent3_avg_rank: 3,
  current_rating: 1,
  dist_wins: 1,
  jt_win_rate: 1,
  draw: -1
};

const MODEL_VERSION = "v1.0.0";

const WEIGHT_LABELS = {
  hj_win_rate: '馬騎師組合勝率',
  jockey_win_rate: '騎師勝率',
  trainer_win_rate: '練馬師勝率',
  career_place_rate: '生涯位置率',
  dist_win_rate: '途程勝率',
  recent3_avg_rank: '近3場平均排名',
  current_rating: '評分',
  dist_wins: '途程勝利次數',
  jt_win_rate: '騎師練馬師組合勝率',
  draw: '檔位'
};

function App() {
  const [fixtures, setFixtures] = useState([]);
  const [selectedFixture, setSelectedFixture] = useState(null);
  const [racecardData, setRacecardData] = useState(null);
  const [selectedRaceNo, setSelectedRaceNo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [predictions, setPredictions] = useState([]);
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);

  useEffect(() => {
    fetchFixtures();
  }, []);

  useEffect(() => {
    if (fixtures.length > 0 && !selectedFixture) {
      setSelectedFixture(fixtures[0]);
    }
  }, [fixtures]);

  useEffect(() => {
    if (selectedFixture) {
      setSelectedRaceNo(null);
      fetchRacecards();
    }
  }, [selectedFixture]);

  const fetchFixtures = async () => {
    try {
      const res = await axios.get('/api/fixtures?mode=upcoming');
      // Get first upcoming race
      if (res.data && res.data.length > 0) {
        setFixtures([res.data[0]]);
        setSelectedFixture(res.data[0]);
      }
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

  // Calculate predictions when weights or race changes
  useEffect(() => {
    if (racecardData && selectedRaceNo) {
      calculatePredictions();
    }
  }, [racecardData, selectedRaceNo, weights]);

  // Auto-save prediction to MongoDB when predictions change
  useEffect(() => {
    if (predictions.length > 0 && selectedFixture && selectedRaceNo) {
      savePrediction();
    }
  }, [predictions]);

  const fetchHorseDetails = async () => {
    // Jersey URLs are now included in racecard API response
    // No additional fetch needed
  };

  const calculatePredictions = () => {
    if (!selectedFixture || !selectedRaceNo) return;
    
    // Call ML prediction API
    fetch(`/api/predict?race_date=${selectedFixture.date}&race_no=${selectedRaceNo}&venue=${selectedFixture.venue}`)
      .then(res => res.json())
      .then(data => {
        if (data && data.predictions) {
          // Add jersey_url, horse_no from racecard data
          const entries = racecardData.entries?.filter(e => e.race_no === selectedRaceNo) || [];
          const results = data.predictions.map(pred => {
            const entry = entries.find(e => e.horse_name === pred.horse_name);
            return {
              ...pred,
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
        // Fallback to simple calculation
        calculateLocalPredictions();
      });
  };

  // Fallback simple calculation
  const calculateLocalPredictions = () => {
    if (!racecardData || !selectedRaceNo) return;
    
    const entries = racecardData.entries?.filter(e => e.race_no === selectedRaceNo) || [];
    entries.sort((a, b) => a.horse_no - b.horse_no);
    
    const results = entries.map((entry) => {
      let score = 50;
      if (entry.draw) {
        score += (entry.draw - 8) * weights.draw * 2;
      }
      return {
        horse_no: entry.horse_no,
        horse_name: entry.horse_name,
        jockey_name: entry.jockey_name,
        trainer_name: entry.trainer_name,
        draw: entry.draw,
        jersey_url: entry.jersey_url || null,
        rating_change: entry.rating_change || null,
        recent_form: entry.recent_form || null,
        score,
        predicted_rank: 0
      };
    });

    // Sort by score and assign ranks
    const sortedResults = [...results].sort((a, b) => b.score - a.score);
    sortedResults.forEach((r, i) => r.predicted_rank = i + 1);
    
    // Keep sorted by horse_no but add rank info
    setPredictions(results);
  };

  const handleWeightChange = (key, value) => {
    setWeights(prev => ({
      ...prev,
      [key]: parseFloat(value)
    }));
  };

  const handleRaceTabClick = (raceNo) => {
    setSelectedRaceNo(raceNo);
  };

  const savePrediction = async () => {
    if (!selectedFixture || !selectedRaceNo || predictions.length === 0) return;
    
    try {
      await axios.post('/api/predictions', {
        race_date: selectedFixture.date,
        race_no: selectedRaceNo,
        venue: selectedFixture.venue,
        predictions: predictions,
        weights: weights,
        model_version: MODEL_VERSION,
        created_at: new Date().toISOString()
      });
    } catch (error) {
      console.error('Error saving prediction:', error);
    }
  };

  // 獲取馬匹 Icon - use jersey_url from predictions directly
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
                <h2>{selectedFixture.date} - {selectedFixture.venue === 'ST' ? '沙田' : '跑馬地'}</h2>
                <div className="race-info">
                  <span>第 {selectedRaceNo} 場</span>
                  <span>{currentRaceCards?.distance || '-'}m</span>
                  <span>{currentRaceCards?.class || '-'}</span>
                </div>
              </div>
              
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
              
              <table className="race-table">
                <thead>
                  <tr>
                    <th>預測</th>
                    <th>馬號</th>
                    <th>馬匹</th>
                    <th>騎師</th>
                    <th>練馬師</th>
                    <th>檔位</th>
                    <th>評分</th>
                    <th>近績</th>
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
                        <td>
                          <div className={`predicted-rank rank-${pred.predicted_rank}`}>
                            {pred.predicted_rank}
                          </div>
                        </td>
                        <td>
                          <div 
                            className="horse-number"
                            style={{ backgroundColor: jersey.type === 'color' ? jersey.value : '#888' }}
                          >
                            {pred.horse_no}
                          </div>
                        </td>
                        <td>
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
                        <td>{pred.jockey_name}</td>
                        <td>{pred.trainer_name}</td>
                        <td>{pred.draw}</td>
                        <td>{entry?.rating_change > 0 ? `+${entry.rating_change}` : entry?.rating_change || '-'}</td>
                        <td>{entry?.recent_form || '-'}</td>
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

        {/* 右側：AI 預測控制面板 */}
        <div className="prediction-panel">
          <h3>📊 AI 預測排名</h3>
          
          <div className="prediction-list">
            {predictions
              .sort((a,b) => a.predicted_rank - b.predicted_rank)
              .slice(0, 4)
              .map((pred, idx) => {
              const jersey = getJerseyInfo(pred.horse_no, pred.horse_name);
              return (
                <div key={idx} className="prediction-item top-4">
                  <div 
                    className={`prediction-rank rank-${pred.predicted_rank}`}
                    style={{ backgroundColor: jersey.type === 'color' ? jersey.value : '#888' }}
                  >
                    {pred.predicted_rank}
                  </div>
                  <div className="prediction-details">
                    <div className="prediction-name">
                      {jersey.type === 'image' ? (
                        <img src={jersey.url} alt={pred.horse_no} className="jersey-icon" />
                      ) : (
                        <div className="jersey-placeholder" style={{ backgroundColor: jersey.value }}>
                          {pred.horse_no}
                        </div>
                      )}
                      {pred.horse_name}
                    </div>
                    <div className="prediction-jockey">{pred.jockey_name}</div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="weights-panel">
            <h4>⚙️ 因子權重調整</h4>
            
            {Object.entries(weights).map(([key, value]) => (
              <div key={key} className="weight-slider">
                <label>
                  <span>{WEIGHT_LABELS[key] || key}</span>
                  <span>{value}</span>
                </label>
                <input
                  type="range"
                  min={-5}
                  max={20}
                  step={0.5}
                  value={value}
                  onChange={(e) => handleWeightChange(key, e.target.value)}
                />
              </div>
            ))}
            
            <button 
              className="btn"
              onClick={() => setWeights(DEFAULT_WEIGHTS)}
            >
              重置權重
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
