import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './index.css';

const DEFAULT_WEIGHTS = {
  hj_win_rate: 10,
  career_place_rate: 5,
  jockey_win_rate: 3,
  trainer_win_rate: 2,
  dist_win_rate: 2,
  recent3_avg_rank: 2,
  current_rating: 1,
  dist_wins: 1,
  jt_win_rate: 1,
  draw: -1,
  randomness: 3
};

// Fallback colors when no jersey_url
const JERSEY_COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A',
  '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2',
  '#F8B500', '#82E0AA', '#F1948A', '#7DCEA0'
];

function App() {
  const [races, setRaces] = useState([]);
  const [selectedRace, setSelectedRace] = useState(null);
  const [predictions, setPredictions] = useState([]);
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [horseDetails, setHorseDetails] = useState({});
  const [bestTimes, setBestTimes] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRaces();
  }, []);

  useEffect(() => {
    if (selectedRace && selectedRace.results) {
      fetchHorseDetails();
      fetchBestTimes();
      calculatePredictions();
    }
  }, [selectedRace, weights]);

  const fetchRaces = async () => {
    try {
      // First try to get from API
      const res = await axios.get('/api/races?date=2026/03/15');
      if (res.data.length > 0) {
        setRaces(res.data);
        setSelectedRace(res.data[0]);
      }
      setLoading(false);
    } catch (error) {
      console.log('Using mock data');
      // Use mock data as fallback
      setRaces(MOCK_RACE_DATA);
      setSelectedRace(MOCK_RACE_DATA[0]);
      setLoading(false);
    }
  };

  const fetchHorseDetails = async () => {
    if (!selectedRace || !selectedRace.results) return;
    
    const details = {};
    for (const horse of selectedRace.results) {
      try {
        const res = await axios.get(`/api/horses/by-name/${encodeURIComponent(horse.horse_name)}`);
        if (res.data) {
          details[horse.horse_name] = res.data;
        }
      } catch (e) {
        // Horse not found in DB
      }
    }
    setHorseDetails(details);
  };

  const fetchBestTimes = async () => {
    if (!selectedRace || !selectedRace.race_date || !selectedRace.race_no) return;
    
    try {
      const res = await axios.get(`/api/horses/best-times?date=${selectedRace.race_date}&raceNo=${selectedRace.race_no}`);
      setBestTimes(res.data || {});
    } catch (e) {
      console.error('Error fetching best times:', e);
    }
  };

  const calculatePredictions = () => {
    if (!selectedRace || !selectedRace.results) {
      setPredictions([]);
      return;
    }

    const results = selectedRace.results.map((horse, idx) => {
      let score = 50 + Math.random() * 50;
      score += (Math.random() - 0.5) * weights.randomness * 10;

      return {
        ...horse,
        score,
        predicted_rank: idx + 1
      };
    });

    results.sort((a, b) => b.score - a.score);
    setPredictions(results);
  };

  const handleWeightChange = (key, value) => {
    setWeights(prev => ({
      ...prev,
      [key]: parseFloat(value)
    }));
  };

  // Get jersey URL or fallback color
  const getJerseyInfo = (horseNo, horseName) => {
    const detail = horseDetails[horseName];
    if (detail && detail.jersey_url) {
      return { type: 'image', url: detail.jersey_url };
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

  return (
    <div className="app">
      <header className="header">
        <h1>🏇 HKJC AI 預測系統</h1>
        <span className="date">{selectedRace?.race_date || '2026/03/22'} - {selectedRace?.venue || 'ST'}</span>
      </header>

      <div className="race-tabs">
        {races.map(race => (
          <button
            key={`${race.race_date}-${race.race_no}`}
            className={`race-tab ${selectedRace?.race_no === race.race_no ? 'active' : ''}`}
            onClick={() => setSelectedRace(race)}
          >
            R{race.race_no}
          </button>
        ))}
      </div>

      <div className="main-layout">
        <div className="race-card">
          {selectedRace && (
            <>
              <div className="race-header">
                <h2>第{selectedRace.race_no}場 - {selectedRace.distance || '1400m'}</h2>
                <div className="race-info">
                  <span>評分: {selectedRace.race_class || 'N/A'}</span>
                  <span>獎金: {selectedRace.prize || selectedRace.prize_money || '$1,170,000'}</span>
                </div>
              </div>

              <table className="race-table">
                <thead>
                  <tr>
                    <th>馬號</th>
                    <th>馬匹</th>
                    <th>騎師</th>
                    <th>練馬師</th>
                    <th>檔位</th>
                    <th>最佳時間</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedRace.results?.map((horse, idx) => {
                    const pred = predictions.find(p => p.horse_no === horse.horse_no);
                    const rank = pred ? predictions.indexOf(pred) + 1 : null;
                    const jersey = getJerseyInfo(horse.horse_no, horse.horse_name);
                    return (
                      <tr key={idx}>
                        <td>
                          <div 
                            className="horse-number"
                            style={{ backgroundColor: jersey.type === 'color' ? jersey.value : '#888' }}
                          >
                            {horse.horse_no}
                          </div>
                        </td>
                        <td>
                          <div className="horse-name-cell">
                            {jersey.type === 'image' ? (
                              <img 
                                src={jersey.url} 
                                alt={horse.horse_no}
                                className="jersey-image-large"
                              />
                            ) : (
                              <div 
                                className="jersey-icon"
                                style={{ backgroundColor: jersey.value }}
                              >
                                {horse.horse_no}
                              </div>
                            )}
                            <span>{horse.horse_name}</span>
                          </div>
                        </td>
                        <td>{horse.jockey}</td>
                        <td>{horse.trainer}</td>
                        <td>{horse.distance || '-'}</td>
                        <td>{bestTimes[horse.horse_name] || '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>

        <div className="prediction-panel">
          <h3>📊 AI 預測排名</h3>
          
          <div className="prediction-list">
            {predictions.slice(0, 4).map((pred, idx) => {
              const jersey = getJerseyInfo(pred.horse_no, pred.horse_name);
              return (
                <div key={idx} className="prediction-item top-4">
                  {jersey.type === 'image' ? (
                    <div className="pred-with-number">
                      <div 
                        className={`prediction-rank rank-${idx + 1}`}
                        style={{ backgroundColor: jersey.value, marginRight: '4px' }}
                      >
                        {pred.horse_no}
                      </div>
                      <img 
                        src={jersey.url} 
                        alt={pred.horse_no}
                        className="jersey-image-large"
                      />
                    </div>
                  ) : (
                    <div 
                      className={`prediction-rank rank-${idx + 1}`}
                      style={{ backgroundColor: jersey.value }}
                    >
                      {pred.horse_no}
                    </div>
                  )}
                  <div className="prediction-details">
                    <div className="prediction-name">{pred.horse_name}</div>
                    <div className="prediction-jockey">{pred.jockey}</div>
                  </div>
                  <div className="prediction-prob">
                    {Math.max(5, 40 - idx * 10)}%
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
                  <span>{key.replace(/_/g, ' ')}</span>
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

// Mock data
const MOCK_RACE_DATA = [
  {
    race_date: "2026/03/22",
    race_no: 1,
    venue: "ST",
    distance: "1400m",
    race_class: "3YO+",
    prize: "$1,670,000",
    results: [
      { horse_no: 1, horse_name: "榮耀之星", jockey: "潘頓", trainer: "蔡約翰", draw: 3 },
      { horse_no: 2, horse_name: "極速突擊", jockey: "布文", trainer: "方嘉柏", draw: 5 },
      { horse_no: 3, horse_name: "金童", jockey: "周俊樂", trainer: "丁冠豪", draw: 1 },
      { horse_no: 4, horse_name: "風火輪", jockey: "艾兆禮", trainer: "沈集成", draw: 7 },
      { horse_no: 5, horse_name: "連戰連勝", jockey: "希威森", trainer: "巫偉傑", draw: 2 },
      { horse_no: 6, horse_name: "熱血青年的", jockey: "霍宏聲", trainer: "桂福特", draw: 4 },
      { horse_no: 7, horse_name: "翡翠之光", jockey: "楊明綸", trainer: "蘇偉賢", draw: 6 },
      { horse_no: 8, horse_name: "銀河艦隊", jockey: "田泰安", trainer: "韋達", draw: 8 },
      { horse_no: 9, horse_name: "狂野之狼", jockey: "鍾易禮", trainer: "文家良", draw: 9 },
      { horse_no: 10, horse_name: "藍寶石", jockey: "巴度", trainer: "黎昭昇", draw: 10 },
      { horse_no: 11, horse_name: "閃電俠", jockey: "金誠剛", trainer: "游達榮", draw: 11 },
      { horse_no: 12, horse_name: "王子", jockey: "麥文堅", trainer: "葉楚航", draw: 12 },
    ]
  },
  {
    race_date: "2026/03/22",
    race_no: 2,
    venue: "ST",
    distance: "1200m",
    race_class: "4YO+",
    prize: "$1,170,000",
    results: [
      { horse_no: 1, horse_name: "電光火石", jockey: "潘頓", trainer: "告東尼", draw: 2 },
      { horse_no: 2, horse_name: "幸運之星", jockey: "布文", trainer: "蔡約翰", draw: 4 },
      { horse_no: 3, horse_name: "黑旋風", jockey: "周俊樂", trainer: "丁冠豪", draw: 1 },
      { horse_no: 4, horse_name: "勝利者", jockey: "艾兆禮", trainer: "沈集成", draw: 6 },
      { horse_no: 5, horse_name: "極品", jockey: "希威森", trainer: "巫偉傑", draw: 3 },
      { horse_no: 6, horse_name: "跑得快", jockey: "霍宏聲", trainer: "桂福特", draw: 5 },
      { horse_no: 7, horse_name: "乖乖", jockey: "楊明綸", trainer: "蘇偉賢", draw: 7 },
      { horse_no: 8, horse_name: "衝刺王", jockey: "田泰安", trainer: "韋達", draw: 8 },
      { horse_no: 9, horse_name: "大勇", jockey: "鍾易禮", trainer: "文家良", draw: 9 },
      { horse_no: 10, horse_name: "小明星", jockey: "巴度", trainer: "黎昭昇", draw: 10 },
    ]
  },
  {
    race_date: "2026/03/22",
    race_no: 3,
    venue: "ST",
    distance: "1800m",
    race_class: "3YO+",
    prize: "$2,240,000",
    results: [
      { horse_no: 1, horse_name: "長青樹", jockey: "潘頓", trainer: "告東尼", draw: 1 },
      { horse_no: 2, horse_name: "耐力王", jockey: "布文", trainer: "方嘉柏", draw: 3 },
      { horse_no: 3, horse_name: "穩陣馬", jockey: "周俊樂", trainer: "丁冠豪", draw: 5 },
      { horse_no: 4, horse_name: "後勁強", jockey: "艾兆禮", trainer: "沈集成", draw: 2 },
      { horse_no: 5, horse_name: "鬥志高", jockey: "希威森", trainer: "巫偉傑", draw: 4 },
      { horse_no: 6, horse_name: "老手", jockey: "霍宏聲", trainer: "桂福特", draw: 6 },
      { horse_no: 7, horse_name: "常勝", jockey: "楊明綸", trainer: "蘇偉賢", draw: 7 },
      { horse_no: 8, horse_name: "千里馬", jockey: "田泰安", trainer: "韋達", draw: 8 },
      { horse_no: 9, horse_name: "好馬", jockey: "鍾易禮", trainer: "文家良", draw: 9 },
      { horse_no: 10, horse_name: "靚仔", jockey: "巴度", trainer: "黎昭昇", draw: 10 },
    ]
  },
  {
    race_date: "2026/03/22",
    race_no: 4,
    venue: "ST",
    distance: "1000m",
    race_class: "4YO+",
    prize: "$1,170,000",
    results: [
      { horse_no: 1, horse_name: "閃電", jockey: "潘頓", trainer: "蔡約翰", draw: 1 },
      { horse_no: 2, horse_name: "炮彈", jockey: "布文", trainer: "方嘉柏", draw: 2 },
      { horse_no: 3, horse_name: "快馬", jockey: "周俊樂", trainer: "丁冠豪", draw: 3 },
      { horse_no: 4, horse_name: "衝刺", jockey: "艾兆禮", trainer: "沈集成", draw: 4 },
      { horse_no: 5, horse_name: "飛毛腿", jockey: "希威森", trainer: "巫偉傑", draw: 5 },
      { horse_no: 6, horse_name: "神風", jockey: "霍宏聲", trainer: "桂福特", draw: 6 },
      { horse_no: 7, horse_name: "火箭", jockey: "楊明綸", trainer: "蘇偉賢", draw: 7 },
      { horse_no: 8, horse_name: "奔馬", jockey: "田泰安", trainer: "韋達", draw: 8 },
    ]
  },
  {
    race_date: "2026/03/22",
    race_no: 5,
    venue: "ST",
    distance: "1650m",
    race_class: "3YO+",
    prize: "$1,670,000",
    results: [
      { horse_no: 1, horse_name: "長途王", jockey: "潘頓", trainer: "告東尼", draw: 2 },
      { horse_no: 2, horse_name: "穩健", jockey: "布文", trainer: "方嘉柏", draw: 1 },
      { horse_no: 3, horse_name: "耐力", jockey: "周俊樂", trainer: "丁冠豪", draw: 4 },
      { horse_no: 4, horse_name: "後上", jockey: "艾兆禮", trainer: "沈集成", draw: 3 },
      { horse_no: 5, horse_name: "均速", jockey: "希威森", trainer: "巫偉傑", draw: 5 },
      { horse_no: 6, horse_name: "步步高", jockey: "霍宏聲", trainer: "桂福特", draw: 6 },
      { horse_no: 7, horse_name: "穩操勝券", jockey: "楊明綸", trainer: "蘇偉賢", draw: 7 },
      { horse_no: 8, horse_name: "大力", jockey: "田泰安", trainer: "韋達", draw: 8 },
      { horse_no: 9, horse_name: "馬到成功", jockey: "鍾易禮", trainer: "文家良", draw: 9 },
      { horse_no: 10, horse_name: "如意", jockey: "巴度", trainer: "黎昭昇", draw: 10 },
      { horse_no: 11, horse_name: "吉祥", jockey: "金誠剛", trainer: "游達榮", draw: 11 },
      { horse_no: 12, horse_name: "福星", jockey: "麥文堅", trainer: "葉楚航", draw: 12 },
    ]
  },
];

export default App;
