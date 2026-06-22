// ═══════════════════════════════════════════════════════════
// app.js — Bootstrap + State Manager
// ═══════════════════════════════════════════════════════════

// ─── Global State ────────────────────────────────────────
const MAYAState = {
  sessionId: '',
  isThinking: false,
  isRecording: false,
  backendOnline: false,
  ollamaOnline: false,
  voiceReady: false,
  activeAgent: null,
  vectorCount: 0,
  cpuPercent: 0,
  ramPercent: 0,
  ramUsedGb: 0,
  ramTotalGb: 0,
  modelName: 'qwen2.5:7b',
  uptime: 0,
  messageHistory: [],
  inputHistory: [],
  inputHistoryIndex: 0,
  settings: {}
};

// ─── App Module ─────────────────────────────────────────
const MAYAApp = (() => {

  // ─── Initialize ──────────────────────────────────────
  async function init() {
    console.log('[MAYA] Initializing MAYA OS...');

    // Load settings from electron-store
    await loadSettings();

    // Apply settings
    applySettings();

    // Initialize session
    await initSession();

    // Initialize modules
    MAYAAgents.init();
    MAYAChat.init();
    MAYAVoice.init();
    MAYATelemetry.init();
    MAYAHotkeys.init();
    MAYACodePanel.init();

    // Connect WebSocket
    MAYAAPI.connectWebSocket({
      onToken: (token) => MAYAChat.appendStreamToken(token),
      onDone: (data) => MAYAChat.finalizeStream(data),
      onStatusChange: (connected) => {
        console.log(`[MAYA WS] Status: ${connected ? 'connected' : 'disconnected'}`);
      }
    });

    // Setup settings panel event listeners
    setupSettingsPanel();

    // Setup window controls
    setupWindowControls();

    // Focus chat input
    setTimeout(() => {
      const input = document.getElementById('chat-input');
      if (input) input.focus();
    }, 500);

    console.log('[MAYA] Initialization complete.');
  }

  // ─── Load Settings ────────────────────────────────────
  async function loadSettings() {
    if (!window.maya) return;

    try {
      MAYAState.settings = {
        backendUrl: await window.maya.getStore('backendUrl') || 'http://localhost:8000',
        ollamaModel: await window.maya.getStore('ollamaModel') || 'qwen2.5:7b',
        voiceEnabled: await window.maya.getStore('voiceEnabled') !== false,
        startOnBoot: await window.maya.getStore('startOnBoot') === true,
        accentColor: await window.maya.getStore('accentColor') || '#22d3ee',
        chatFontSize: await window.maya.getStore('chatFontSize') || 10
      };
    } catch (err) {
      console.warn('[MAYA] Failed to load settings:', err);
      MAYAState.settings = {
        backendUrl: 'http://localhost:8000',
        ollamaModel: 'qwen2.5:7b',
        voiceEnabled: true,
        startOnBoot: false,
        accentColor: '#22d3ee',
        chatFontSize: 10
      };
    }
  }

  // ─── Apply Settings ───────────────────────────────────
  function applySettings() {
    const s = MAYAState.settings;

    // Set API base URL
    MAYAAPI.setBaseUrl(s.backendUrl || 'http://localhost:8000');

    // Set model name
    MAYAState.modelName = s.ollamaModel || 'qwen2.5:7b';

    // Apply accent color
    if (s.accentColor) {
      document.documentElement.style.setProperty('--accent-cyan', s.accentColor);
    }

    // Apply chat font size
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');
    if (chatInput) chatInput.style.fontSize = `${s.chatFontSize || 10}px`;
    if (chatMessages) chatMessages.style.fontSize = `${s.chatFontSize || 10}px`;
  }

  // ─── Initialize Session ───────────────────────────────
  async function initSession() {
    if (window.maya) {
      try {
        const storedSessionId = await window.maya.getStore('sessionId');
        if (storedSessionId) {
          MAYAState.sessionId = storedSessionId;
        } else {
          MAYAState.sessionId = MAYAHotkeys.generateUUID();
          await window.maya.setStore('sessionId', MAYAState.sessionId);
        }
      } catch (err) {
        MAYAState.sessionId = MAYAHotkeys.generateUUID();
      }
    } else {
      MAYAState.sessionId = MAYAHotkeys.generateUUID();
    }
    console.log('[MAYA] Session:', MAYAState.sessionId);
  }

  // ─── Update State ─────────────────────────────────────
  function updateState(changes) {
    let orbChanged = false;

    for (const key of Object.keys(changes)) {
      if (MAYAState[key] !== changes[key]) {
        MAYAState[key] = changes[key];

        // Track orb-affecting state changes
        if (key === 'isThinking' || key === 'isRecording') {
          orbChanged = true;
        }
        if (key === 'activeAgent') {
          MAYAAgents.setActive(changes[key]);
        }
      }
    }

    // Update orb state
    if (orbChanged) {
      updateOrbState();
    }
  }

  // ─── Orb State Updates ────────────────────────────────
  function updateOrbState() {
    const orbCore = document.getElementById('orb-core');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('orb-status-text');
    if (!orbCore) return;

    // Remove all state classes
    orbCore.classList.remove('orb-idle', 'orb-thinking', 'orb-speaking', 'orb-error');
    if (statusDot) statusDot.classList.remove('idle', 'thinking', 'speaking', 'error');
    if (statusText) statusText.classList.remove('status-idle', 'status-thinking', 'status-speaking', 'status-error');

    if (MAYAState.isRecording) {
      orbCore.classList.add('orb-speaking');
      if (statusDot) statusDot.classList.add('speaking');
      if (statusText) {
        statusText.textContent = 'SPEAKING';
        statusText.classList.add('status-speaking');
      }
    } else if (MAYAState.isThinking) {
      orbCore.classList.add('orb-thinking');
      if (statusDot) statusDot.classList.add('thinking');
      if (statusText) {
        statusText.textContent = 'THINKING';
        statusText.classList.add('status-thinking');
      }
    } else {
      orbCore.classList.add('orb-idle');
      if (statusDot) statusDot.classList.add('idle');
      if (statusText) {
        statusText.textContent = 'IDLE';
        statusText.classList.add('status-idle');
      }
    }
  }

  // ─── Window Controls ──────────────────────────────────
  function setupWindowControls() {
    const btnMin = document.getElementById('btn-minimize');
    const btnMax = document.getElementById('btn-maximize');
    const btnClose = document.getElementById('btn-close');

    if (btnMin && window.maya) {
      btnMin.addEventListener('click', () => window.maya.minimize());
    }
    if (btnMax && window.maya) {
      btnMax.addEventListener('click', () => window.maya.maximize());
    }
    if (btnClose && window.maya) {
      btnClose.addEventListener('click', () => window.maya.close());
    }
  }

  // ─── Settings Panel ──────────────────────────────────
  function setupSettingsPanel() {
    // Close button
    const closeBtn = document.getElementById('settings-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        const overlay = document.getElementById('settings-overlay');
        if (overlay) overlay.classList.add('hidden');
      });
    }

    // Backdrop click to close
    const backdrop = document.querySelector('.settings-backdrop');
    if (backdrop) {
      backdrop.addEventListener('click', () => {
        const overlay = document.getElementById('settings-overlay');
        if (overlay) overlay.classList.add('hidden');
      });
    }

    // Font size slider live preview
    const fontSlider = document.getElementById('setting-fontsize');
    const fontLabel = document.getElementById('fontsize-val');
    if (fontSlider && fontLabel) {
      fontSlider.addEventListener('input', () => {
        fontLabel.textContent = `${fontSlider.value}px`;
      });
    }

    // Accent color live preview
    const accentPicker = document.getElementById('setting-accent');
    if (accentPicker) {
      accentPicker.addEventListener('input', () => {
        document.documentElement.style.setProperty('--accent-cyan', accentPicker.value);
      });
    }

    // Save button
    const saveBtn = document.getElementById('settings-save');
    if (saveBtn) {
      saveBtn.addEventListener('click', saveSettings);
    }
  }

  // ─── Save Settings ───────────────────────────────────
  async function saveSettings() {
    if (!window.maya) return;

    const backendUrl = document.getElementById('setting-backend-url')?.value || 'http://localhost:8000';
    const model = document.getElementById('setting-model')?.value || 'qwen2.5:7b';
    const voice = document.getElementById('setting-voice')?.checked ?? true;
    const boot = document.getElementById('setting-boot')?.checked ?? false;
    const accent = document.getElementById('setting-accent')?.value || '#22d3ee';
    const fontSize = parseInt(document.getElementById('setting-fontsize')?.value) || 10;

    try {
      await window.maya.setStore('backendUrl', backendUrl);
      await window.maya.setStore('ollamaModel', model);
      await window.maya.setStore('voiceEnabled', voice);
      await window.maya.setStore('startOnBoot', boot);
      await window.maya.setStore('accentColor', accent);
      await window.maya.setStore('chatFontSize', fontSize);

      // Update state
      MAYAState.settings = { backendUrl, ollamaModel: model, voiceEnabled: voice, startOnBoot: boot, accentColor: accent, chatFontSize: fontSize };

      // Apply
      applySettings();

      // Close settings
      const overlay = document.getElementById('settings-overlay');
      if (overlay) overlay.classList.add('hidden');

      // Flash save button to confirm
      const saveBtn = document.getElementById('settings-save');
      if (saveBtn) {
        saveBtn.textContent = '✓ SAVED';
        saveBtn.style.borderColor = 'var(--accent-green)';
        saveBtn.style.color = 'var(--accent-green)';
        setTimeout(() => {
          saveBtn.textContent = 'SAVE CONFIGURATION';
          saveBtn.style.borderColor = '';
          saveBtn.style.color = '';
        }, 1500);
      }

      console.log('[MAYA] Settings saved.');
    } catch (err) {
      console.error('[MAYA] Failed to save settings:', err);
    }
  }

  return {
    init,
    updateState,
    updateOrbState,
    loadSettings,
    applySettings
  };
})();

// ─── Boot ───────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  MAYAApp.init();
});
