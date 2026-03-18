import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './index.css';

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
  const [loading, setLoading] = useState(true);

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
      fetchRacecards();
    }
  }, [selectedFixture]);

  const fetchFixtures = async () => {
    try {
      const res = await axios.get('/api/fixtures?mode=upcoming');
      setFixtures(res.data || []);
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
    } catch (error) {
      console.log('Error fetching racecards:', error);
      setRacecardData(null);
    }
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
        <h1>🏇 HKJC 賽程</h1>
      </header>

      <div className="fixtures-view">
        <div className="fixtures-list">
          <h2>下一個賽日</h2>
          {fixtures.length === 0 ? (
            <div className="no-data">暫無賽程數據</div>
          ) : (
            <div 
              className="fixture-item active"
              onClick={() => setSelectedFixture(fixtures[0])}
            >
              <div className="fixture-date">{fixtures[0].date}</div>
              <div className="fixture-venue">{fixtures[0].venue === 'ST' ? '沙田' : '跑馬地'}</div>
              <div className="fixture-races">{fixtures[0].race_count || 8} 場</div>
            </div>
          )}
        </div>
        
        <div className="fixture-detail">
          {selectedFixture && racecardData && (
            <>
              <h2>{selectedFixture.date} - {selectedFixture.venue === 'ST' ? '沙田' : '跑馬地'}</h2>
              <div className="fixture-info">
                <span>場次: {racecardData.racecards?.length || 0}</span>
              </div>
              
              <div className="race-tabs">
                {racecardData.racecards?.map(rc => (
                  <button key={rc.race_no} className="race-tab">
                    R{rc.race_no}
                  </button>
                ))}
              </div>
              
              {racecardData.entries && racecardData.entries.length > 0 && (
                <table className="race-table">
                  <thead>
                    <tr>
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
                    {racecardData.entries.slice(0, 12).map((entry, idx) => (
                      <tr key={idx}>
                        <td><div className="horse-number">{entry.horse_no}</div></td>
                        <td>{entry.horse_name}</td>
                        <td>{entry.jockey_name}</td>
                        <td>{entry.trainer_name}</td>
                        <td>{entry.draw}</td>
                        <td>{entry.rating_change > 0 ? `+${entry.rating_change}` : entry.rating_change}</td>
                        <td>{entry.recent_form}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
          {selectedFixture && !racecardData && (
            <>
              <h2>{selectedFixture.date} - {selectedFixture.venue === 'ST' ? '沙田' : '跑馬地'}</h2>
              <div className="fixture-info">
                <span>場次: {selectedFixture.race_count || 8}</span>
              </div>
              <p className="fixture-note">
                正在載入排位表...
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
