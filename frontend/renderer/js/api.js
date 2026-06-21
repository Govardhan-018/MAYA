// ═══════════════════════════════════════════════════════════
// api.js — All HTTP + WebSocket calls to backend
// ═══════════════════════════════════════════════════════════

const MAYAAPI = (() => {
  let baseUrl = 'http://localhost:8000';
  let ws = null;
  let wsReconnectDelay = 2000;
  let wsReconnectTimer = null;
  let onTokenCallback = null;
  let onDoneCallback = null;
  let onWsStatusChange = null;

  // ─── Configuration ─────────────────────────────────────
  function setBaseUrl(url) {
    baseUrl = url.replace(/\/+$/, '');
  }

  function getBaseUrl() {
    return baseUrl;
  }

  // ─── HTTP Helpers ──────────────────────────────────────
  async function fetchJSON(endpoint, options = {}) {
    try {
      const url = `${baseUrl}${endpoint}`;
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (err) {
      console.warn(`[MAYA API] ${endpoint} failed:`, err.message);
      throw err;
    }
  }

  // ─── Chat ──────────────────────────────────────────────
  async function sendChat(message, sessionId) {
    return fetchJSON('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId })
    });
  }

  // ─── System Stats ──────────────────────────────────────
  async function getSystemStats() {
    return fetchJSON('/api/system/stats');
  }

  // ─── Memory Stats ─────────────────────────────────────
  async function getMemoryStats() {
    return fetchJSON('/api/memory/stats');
  }

  // ─── Context Usage ────────────────────────────────────
  async function getContextUsage() {
    return fetchJSON('/api/chat/context_usage');
  }

  // ─── Backend Status ───────────────────────────────────
  async function getStatus() {
    return fetchJSON('/api/status');
  }

  // ─── Voice Transcribe ─────────────────────────────────
  async function transcribeVoice(audioBlob) {
    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');
      const response = await fetch(`${baseUrl}/api/voice/transcribe`, {
        method: 'POST',
        body: formData
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (err) {
      console.warn('[MAYA API] Voice transcribe failed:', err.message);
      throw err;
    }
  }

  // ─── WebSocket ─────────────────────────────────────────
  function connectWebSocket(callbacks = {}) {
    onTokenCallback = callbacks.onToken || null;
    onDoneCallback = callbacks.onDone || null;
    onWsStatusChange = callbacks.onStatusChange || null;

    _wsConnect();
  }

  function _wsConnect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const wsUrl = baseUrl.replace(/^http/, 'ws') + '/ws/chat';
    console.log('[MAYA WS] Connecting to', wsUrl);

    try {
      ws = new WebSocket(wsUrl);
    } catch (err) {
      console.warn('[MAYA WS] Connection error:', err.message);
      _scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      console.log('[MAYA WS] Connected');
      wsReconnectDelay = 2000; // Reset backoff
      if (onWsStatusChange) onWsStatusChange(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.done) {
          if (onDoneCallback) onDoneCallback(data);
        } else if (data.token !== undefined) {
          if (onTokenCallback) onTokenCallback(data.token);
        }
      } catch (err) {
        console.warn('[MAYA WS] Parse error:', err.message);
      }
    };

    ws.onclose = () => {
      console.log('[MAYA WS] Disconnected');
      if (onWsStatusChange) onWsStatusChange(false);
      _scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.warn('[MAYA WS] Error');
      ws.close();
    };
  }

  function _scheduleReconnect() {
    if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
    console.log(`[MAYA WS] Reconnecting in ${wsReconnectDelay / 1000}s...`);
    wsReconnectTimer = setTimeout(() => {
      _wsConnect();
    }, wsReconnectDelay);
    // Exponential backoff: 2s → 4s → 8s → 16s → 30s cap
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
  }

  function sendWsMessage(message, sessionId) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ message, session_id: sessionId }));
      return true;
    }
    return false;
  }

  function isWsConnected() {
    return ws && ws.readyState === WebSocket.OPEN;
  }

  function disconnectWebSocket() {
    if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
    if (ws) {
      ws.onclose = null; // Prevent reconnect
      ws.close();
      ws = null;
    }
  }

  // ─── Public API ────────────────────────────────────────
  return {
    setBaseUrl,
    getBaseUrl,
    fetchJSON,
    sendChat,
    getSystemStats,
    getMemoryStats,
    getContextUsage,
    getStatus,
    transcribeVoice,
    connectWebSocket,
    sendWsMessage,
    isWsConnected,
    disconnectWebSocket
  };
})();
