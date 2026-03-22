import { useEffect, useRef, useState, useCallback } from 'react';
import { io } from 'socket.io-client';

const SOCKET_URL = window.location.hostname === 'localhost' 
  ? 'http://localhost:3001' 
  : `http://${window.location.hostname}:3001`;

/**
 * useOddsSocket - WebSocket hook for real-time odds updates
 * 
 * @param {string} raceId - e.g. "2026-03-22_ST_R7"
 * @returns {{ oddsData, oddsHistory, connected, error }}
 */
export function useOddsSocket(raceId) {
  const [oddsData, setOddsData] = useState({});       // { horse_no: { win, place, updated_at } }
  const [oddsHistory, setOddsHistory] = useState({}); // { horse_no: [{ time, win, place }] }
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  
  const socketRef = useRef(null);
  const historyRef = useRef({}); // Keep history in ref to avoid stale state in callbacks

  useEffect(() => {
    if (!raceId) return;

    // Reset state on race change
    setOddsData({});
    setOddsHistory({});
    historyRef.current = {};
    setConnected(false);
    setError(null);

    const socket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 10,
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      setConnected(true);
      setError(null);
      // Subscribe to race room
      socket.emit('subscribe', { race_id: raceId });
    });

    socket.on('disconnect', () => {
      setConnected(false);
    });

    socket.on('connect_error', (err) => {
      setError(err.message);
      setConnected(false);
    });

    // Receive odds update: { horse_no, win, place, timestamp }
    socket.on('odds_update', (data) => {
      const { horse_no, win, place, timestamp } = data;
      
      setOddsData(prev => ({
        ...prev,
        [horse_no]: { win, place, updated_at: timestamp }
      }));

      // Append to history
      const point = { time: timestamp, win, place };
      setOddsHistory(prev => {
        const existing = prev[horse_no] || [];
        // Keep last 60 points (~5 minutes at 5s intervals)
        const updated = [...existing, point].slice(-60);
        return { ...prev, [horse_no]: updated };
      });
      historyRef.current = { ...historyRef.current, [horse_no]: [...(historyRef.current[horse_no] || []), point].slice(-60) };
    });

    // Receive full snapshot: { odds: { [horse_no]: { win, place } } }
    socket.on('odds_snapshot', (data) => {
      const { odds } = data;
      const newData = {};
      const now = Date.now();
      Object.entries(odds).forEach(([horse_no, odds_val]) => {
        newData[horse_no] = { ...odds_val, updated_at: now };
        // Seed history with current value
        historyRef.current[horse_no] = [{ time: now, win: odds_val.win, place: odds_val.place }];
      });
      setOddsData(newData);
      setOddsHistory({ ...historyRef.current });
    });

    return () => {
      socket.emit('unsubscribe', { race_id: raceId });
      socket.disconnect();
      socketRef.current = null;
    };
  }, [raceId]);

  return { oddsData, oddsHistory, connected, error };
}
