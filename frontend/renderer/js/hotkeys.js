// ═══════════════════════════════════════════════════════════
// hotkeys.js — Global Keyboard Shortcut Registration
// ═══════════════════════════════════════════════════════════

const MAYAHotkeys = (() => {
  // ─── Initialize ────────────────────────────────────────
  function init() {
    document.addEventListener('keydown', handleKeydown);
  }

  // ─── Key Handler ──────────────────────────────────────
  function handleKeydown(e) {
    // Ctrl+Space → Toggle HUD (minimize/restore)
    if (e.ctrlKey && e.code === 'Space') {
      e.preventDefault();
      if (window.maya) {
        window.maya.minimize();
      }
      return;
    }

    // Alt+M → Toggle Push to Talk
    if (e.altKey && e.code === 'KeyM') {
      e.preventDefault();
      MAYAVoice.toggleVoice();
      return;
    }

    // Alt+N → New Conversation
    if (e.altKey && e.code === 'KeyN') {
      e.preventDefault();
      newConversation();
      return;
    }

    // Ctrl+, → Open Settings
    if (e.ctrlKey && e.code === 'Comma') {
      e.preventDefault();
      toggleSettings();
      return;
    }

    // Escape → Close overlays / blur input
    if (e.code === 'Escape') {
      e.preventDefault();
      closeOverlays();
      return;
    }
  }

  // ─── New Conversation ─────────────────────────────────
  function newConversation() {
    const newSessionId = generateUUID();
    MAYAState.sessionId = newSessionId;

    // Persist new session
    if (window.maya) {
      window.maya.setStore('sessionId', newSessionId);
    }

    // Clear chat
    MAYAChat.clearChat();

    // Clear agent state
    MAYAAgents.clearAllActive();
  }

  // ─── Toggle Settings ──────────────────────────────────
  function toggleSettings() {
    const overlay = document.getElementById('settings-overlay');
    if (!overlay) return;

    if (overlay.classList.contains('hidden')) {
      overlay.classList.remove('hidden');
      // Load current values into settings form
      loadSettingsValues();
    } else {
      overlay.classList.add('hidden');
    }
  }

  // ─── Close Overlays ───────────────────────────────────
  function closeOverlays() {
    const overlay = document.getElementById('settings-overlay');
    if (overlay && !overlay.classList.contains('hidden')) {
      overlay.classList.add('hidden');
      return;
    }

    // Blur input
    const input = document.getElementById('chat-input');
    if (input) input.blur();
  }

  // ─── Load Settings Values ─────────────────────────────
  async function loadSettingsValues() {
    if (!window.maya) return;

    try {
      const backendUrl = await window.maya.getStore('backendUrl') || 'http://localhost:8000';
      const model = await window.maya.getStore('ollamaModel') || 'qwen2.5:7b';
      const voice = await window.maya.getStore('voiceEnabled');
      const boot = await window.maya.getStore('startOnBoot');
      const accent = await window.maya.getStore('accentColor') || '#22d3ee';
      const fontSize = await window.maya.getStore('chatFontSize') || 10;

      const urlInput = document.getElementById('setting-backend-url');
      const modelInput = document.getElementById('setting-model');
      const voiceToggle = document.getElementById('setting-voice');
      const bootToggle = document.getElementById('setting-boot');
      const accentInput = document.getElementById('setting-accent');
      const fontInput = document.getElementById('setting-fontsize');
      const fontLabel = document.getElementById('fontsize-val');

      if (urlInput) urlInput.value = backendUrl;
      if (modelInput) modelInput.value = model;
      if (voiceToggle) voiceToggle.checked = voice !== false;
      if (bootToggle) bootToggle.checked = boot === true;
      if (accentInput) accentInput.value = accent;
      if (fontInput) fontInput.value = fontSize;
      if (fontLabel) fontLabel.textContent = `${fontSize}px`;
    } catch (err) {
      console.warn('[MAYA Hotkeys] Failed to load settings:', err);
    }
  }

  // ─── UUID Generator ──────────────────────────────────
  function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  return {
    init,
    toggleSettings,
    newConversation,
    generateUUID
  };
})();
