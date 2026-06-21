// ═══════════════════════════════════════════════════════════
// telemetry.js — CPU/RAM Polling, Live Updates, Hex Grid
// ═══════════════════════════════════════════════════════════

const MAYATelemetry = (() => {
  let systemStatsInterval = null;
  let statusInterval = null;
  let memoryStatsInterval = null;
  let hexGridInterval = null;
  let clockInterval = null;
  let uptimeInterval = null;
  let uptimeStart = Date.now();

  // ─── Initialize ────────────────────────────────────────
  function init() {
    // Generate hex grid cells
    generateHexGrid();

    // Start clock
    updateClock();
    clockInterval = setInterval(updateClock, 1000);

    // Start uptime counter
    uptimeStart = Date.now();
    uptimeInterval = setInterval(updateUptime, 1000);

    // Start hex grid animation
    hexGridInterval = setInterval(animateHexGrid, 1200);

    // Start polling
    startPolling();
  }

  // ─── Start Polling ────────────────────────────────────
  function startPolling() {
    // System stats every 2s
    pollSystemStats();
    systemStatsInterval = setInterval(pollSystemStats, 2000);

    // Backend status every 5s
    pollStatus();
    statusInterval = setInterval(pollStatus, 5000);

    // Memory stats every 10s
    pollMemoryStats();
    memoryStatsInterval = setInterval(pollMemoryStats, 10000);
  }

  // ─── System Stats ─────────────────────────────────────
  async function pollSystemStats() {
    try {
      const stats = await MAYAAPI.getSystemStats();
      MAYAApp.updateState({
        cpuPercent: stats.cpu_percent || 0,
        ramPercent: stats.ram_percent || 0,
        ramUsedGb: stats.ram_used_gb || 0,
        ramTotalGb: stats.ram_total_gb || 0
      });
      updateCpuMeter(stats.cpu_percent || 0);
      updateRamMeter(stats.ram_percent || 0, stats.ram_used_gb || 0, stats.ram_total_gb || 0);
    } catch (err) {
      // Backend might be offline
    }
  }

  // ─── Backend Status ───────────────────────────────────
  async function pollStatus() {
    try {
      const status = await MAYAAPI.getStatus();
      const backendOnline = status.backend === 'ok';
      const ollamaOnline = status.ollama === 'ok';
      const voiceReady = status.voice === 'ready';
      const modelName = status.model || MAYAState.modelName;

      MAYAApp.updateState({
        backendOnline,
        ollamaOnline,
        voiceReady,
        modelName
      });

      updateStatusBar(backendOnline, ollamaOnline, voiceReady);
      updateModelName(modelName);

      // Enable/disable chat based on backend status
      MAYAChat.setInputEnabled(backendOnline);
    } catch (err) {
      MAYAApp.updateState({
        backendOnline: false,
        ollamaOnline: false
      });
      updateStatusBar(false, false, MAYAState.voiceReady);
      MAYAChat.setInputEnabled(false);
    }
  }

  // ─── Memory Stats ────────────────────────────────────
  async function pollMemoryStats() {
    try {
      const memStats = await MAYAAPI.getMemoryStats();
      MAYAApp.updateState({ vectorCount: memStats.vector_count || 0 });
      updateVectorCount(memStats.vector_count || 0);
      updateLTMSparkline(memStats.ltm_similarities || []);

      // Also poll context usage
      try {
        const ctx = await MAYAAPI.getContextUsage();
        updateSTMBuffer(ctx.turns_loaded || 0, ctx.max_turns || 20);
      } catch (e) {
        // Ignore
      }
    } catch (err) {
      // Backend might be offline
    }
  }

  // ─── CPU Arc Meter Update ─────────────────────────────
  function updateCpuMeter(percent) {
    const arc = document.getElementById('cpu-arc');
    const valueText = document.getElementById('cpu-value');
    if (!arc || !valueText) return;

    // The arc total length is ~157 (π * r for semicircle with r=50)
    const totalLength = 157;
    const fillLength = (percent / 100) * totalLength;
    arc.setAttribute('stroke-dasharray', `${fillLength}, ${totalLength}`);
    valueText.textContent = `${Math.round(percent)}%`;
  }

  // ─── RAM Meter Update ─────────────────────────────────
  function updateRamMeter(percent, usedGb, totalGb) {
    const bar = document.getElementById('ram-bar');
    const valueEl = document.getElementById('ram-value');
    const detailEl = document.getElementById('ram-detail');
    if (!bar) return;

    bar.style.width = `${Math.min(percent, 100)}%`;
    if (valueEl) valueEl.textContent = `${Math.round(percent)}%`;
    if (detailEl) detailEl.textContent = `${usedGb.toFixed(1)} / ${totalGb.toFixed(1)} GB`;
  }

  // ─── Vector Count ─────────────────────────────────────
  function updateVectorCount(count) {
    const el = document.getElementById('vector-count');
    const bar = document.getElementById('vector-bar');
    const sbVectors = document.getElementById('sb-vectors');
    if (el) el.textContent = count.toLocaleString();
    if (sbVectors) sbVectors.textContent = count.toLocaleString();
    // Bar shows relative to 10000 max as reference
    if (bar) bar.style.width = `${Math.min((count / 10000) * 100, 100)}%`;
  }

  // ─── Status Bar Updates ───────────────────────────────
  function updateStatusBar(backendOnline, ollamaOnline, voiceReady) {
    const sbBackend = document.getElementById('sb-backend');
    const sbBackendText = document.getElementById('sb-backend-text');
    const sbOllama = document.getElementById('sb-ollama');
    const sbOllamaText = document.getElementById('sb-ollama-text');
    const sbVoice = document.getElementById('sb-voice');
    const sbVoiceText = document.getElementById('sb-voice-text');

    if (sbBackend) {
      sbBackend.className = `status-indicator ${backendOnline ? 'online' : 'offline'}`;
      sbBackend.textContent = '●';
    }
    if (sbBackendText) {
      sbBackendText.textContent = backendOnline ? 'BACKEND ONLINE' : 'BACKEND OFFLINE';
    }

    if (sbOllama) {
      sbOllama.className = `status-indicator ${ollamaOnline ? 'online' : 'offline'}`;
      sbOllama.textContent = '●';
    }
    if (sbOllamaText) {
      sbOllamaText.textContent = ollamaOnline ? 'OLLAMA HEALTHY' : 'OLLAMA UNREACHABLE';
    }

    if (sbVoice) {
      sbVoice.className = `status-indicator ${voiceReady ? 'online' : 'offline'}`;
      sbVoice.textContent = voiceReady ? '●' : '○';
    }
    if (sbVoiceText) {
      sbVoiceText.textContent = voiceReady ? 'VOICE READY' : 'VOICE DISABLED';
    }
  }

  // ─── Model Name ───────────────────────────────────────
  function updateModelName(name) {
    const el = document.getElementById('model-name');
    if (el) el.textContent = name;
  }

  // ─── LTM Sparkline ───────────────────────────────────
  function updateLTMSparkline(similarities) {
    const line = document.getElementById('ltm-line');
    const dot = document.getElementById('ltm-peak-dot');
    const label = document.getElementById('ltm-peak-label');
    if (!line || !similarities || similarities.length === 0) return;

    // Take last 13 values
    const data = similarities.slice(-13);
    const maxVal = Math.max(...data);
    const minVal = Math.min(...data);
    const range = maxVal - minVal || 1;
    const width = 160;
    const height = 36;
    const paddingY = 4;

    const points = data.map((val, i) => {
      const x = (i / (data.length - 1 || 1)) * width;
      const y = paddingY + (1 - (val - minVal) / range) * (height - paddingY * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    line.setAttribute('points', points);

    // Show peak dot
    const peakIdx = data.indexOf(maxVal);
    if (peakIdx >= 0) {
      const px = (peakIdx / (data.length - 1 || 1)) * width;
      const py = paddingY + (1 - (maxVal - minVal) / range) * (height - paddingY * 2);
      dot.setAttribute('cx', px.toFixed(1));
      dot.setAttribute('cy', py.toFixed(1));
      dot.style.display = 'block';

      label.setAttribute('x', (px + 5).toFixed(1));
      label.setAttribute('y', (py - 3).toFixed(1));
      label.textContent = maxVal.toFixed(2);
      label.style.display = 'block';
    }
  }

  // ─── STM Buffer ───────────────────────────────────────
  function updateSTMBuffer(loaded, max) {
    const info = document.getElementById('stm-info');
    const bar = document.getElementById('stm-bar');
    if (info) info.textContent = `TURNS LOADED ${loaded}/${max}`;
    if (bar) bar.style.width = `${(loaded / max) * 100}%`;
  }

  // ─── Hex Grid ─────────────────────────────────────────
  function generateHexGrid() {
    const grid = document.getElementById('hex-grid');
    if (!grid) return;
    grid.innerHTML = '';
    for (let i = 0; i < 25; i++) {
      const cell = document.createElement('div');
      cell.className = 'hex-cell';
      cell.dataset.index = i;
      grid.appendChild(cell);
    }
  }

  function animateHexGrid() {
    const cells = document.querySelectorAll('.hex-cell');
    if (cells.length === 0) return;

    // Activate 2-4 random cells
    const count = 2 + Math.floor(Math.random() * 3);
    for (let i = 0; i < count; i++) {
      const idx = Math.floor(Math.random() * cells.length);
      const cell = cells[idx];
      cell.classList.remove('active', 'hot');

      // Force reflow for re-animation
      void cell.offsetWidth;

      const isHot = Math.random() > 0.7;
      cell.classList.add(isHot ? 'hot' : 'active');

      // Remove class after animation
      setTimeout(() => {
        cell.classList.remove('active', 'hot');
      }, 1200);
    }
  }

  // ─── Clock ────────────────────────────────────────────
  function updateClock() {
    const el = document.getElementById('sb-clock');
    if (!el) return;
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const s = String(now.getSeconds()).padStart(2, '0');
    el.textContent = `${h}:${m}:${s} IST`;
  }

  // ─── Uptime Counter ──────────────────────────────────
  function updateUptime() {
    const el = document.getElementById('uptime-counter');
    if (!el) return;
    const elapsed = Math.floor((Date.now() - uptimeStart) / 1000);
    MAYAState.uptime = elapsed;
    const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
    const s = String(elapsed % 60).padStart(2, '0');
    el.textContent = `${h}:${m}:${s}`;
  }

  // ─── Cleanup ──────────────────────────────────────────
  function destroy() {
    if (systemStatsInterval) clearInterval(systemStatsInterval);
    if (statusInterval) clearInterval(statusInterval);
    if (memoryStatsInterval) clearInterval(memoryStatsInterval);
    if (hexGridInterval) clearInterval(hexGridInterval);
    if (clockInterval) clearInterval(clockInterval);
    if (uptimeInterval) clearInterval(uptimeInterval);
  }

  return {
    init,
    destroy,
    pollSystemStats,
    pollStatus,
    pollMemoryStats,
    updateCpuMeter,
    updateRamMeter,
    updateStatusBar,
    updateLTMSparkline,
    updateSTMBuffer
  };
})();
