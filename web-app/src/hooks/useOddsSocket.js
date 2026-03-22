import { useEffect, useRef, useState, useCallback } from 'react';
import { io } from 'socket.io-client';

// Use origin-only URL + explicit path to avoid Socket.IO double-path bug
// (io("https://host/socket.io") makes Engine.IO requests to /socket.io/socket.io/)
const SOCKET_ORIGIN = window.location.origin;
const SOCKET_PATH = '/socket.io/';

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

    const socket = io(SOCKET_ORIGIN, {
      path: SOCKET_PATH,
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
      // Normalize horse_no to string (Object.keys/JSON always stringify numeric keys)
      const hk = String(horse_no);
      
      setOddsData(prev => ({
        ...prev,
        [hk]: { win, place, updated_at: timestamp }
      }));

      // Append to history
      const point = { time: timestamp, win, place };
      setOddsHistory(prev => {
        const existing = prev[hk] || [];
        // Keep last 300 points (~50 minutes at 10s scrape interval)
        const updated = [...existing, point].slice(-300);
        return { ...prev, [hk]: updated };
      });
      historyRef.current = { ...historyRef.current, [hk]: [...(historyRef.current[hk] || []), point].slice(-60) };
    });

    // Receive full snapshot: { odds: { [horse_no]: { win, place } } }
    // Only seed horses that don't have history yet (preserve accumulated history on reconnect)
    socket.on('odds_snapshot', (data) => {
      const { odds } = data;
      const now = Date.now();
      Object.entries(odds).forEach(([horse_no, odds_val]) => {
        const hk = String(horse_no);
        // Seed history ONLY for horses we haven't seen before
        if (!historyRef.current[hk]) {
          historyRef.current[hk] = [{ time: now, win: odds_val.win, place: odds_val.place }];
        }
        // Always update oddsData (snapshot is the freshest)
        setOddsData(prev => ({ ...prev, [hk]: { win: odds_val.win, place: odds_val.place, updated_at: now } }));
      });
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
