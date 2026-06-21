// ═══════════════════════════════════════════════════════════
// chat.js — Chat Logic, Message Rendering, Streaming
// ═══════════════════════════════════════════════════════════

const MAYAChat = (() => {
  let messagesContainer = null;
  let chatInput = null;
  let currentStreamEl = null;
  let streamBuffer = '';

  // ─── Initialize ────────────────────────────────────────
  function init() {
    messagesContainer = document.getElementById('chat-messages');
    chatInput = document.getElementById('chat-input');

    // Enter to send
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (text && !MAYAState.isThinking) {
          sendMessage(text);
        }
      }

      // Up arrow for history recall
      if (e.key === 'ArrowUp' && chatInput.value === '') {
        e.preventDefault();
        recallHistory();
      }
    });

    // Focus input on click anywhere in chat area
    messagesContainer.addEventListener('click', () => {
      chatInput.focus();
    });
  }

  // ─── Send Message ─────────────────────────────────────
  function sendMessage(text) {
    // Add to input history
    MAYAState.inputHistory.push(text);
    MAYAState.inputHistoryIndex = MAYAState.inputHistory.length;

    // Add user message to state
    MAYAState.messageHistory.push({ role: 'user', content: text });

    // Render user message
    appendMessage('user', text);

    // Clear input
    chatInput.value = '';

    // Set thinking state
    updateState({ isThinking: true, activeAgent: null });

    // Try WebSocket first, fallback to HTTP
    const sent = MAYAAPI.sendWsMessage(text, MAYAState.sessionId);
    if (sent) {
      // WebSocket will handle streaming via callbacks
      startStreamingMessage();
    } else {
      // Fallback to HTTP
      sendViaHTTP(text);
    }
  }

  // ─── HTTP Fallback ────────────────────────────────────
  async function sendViaHTTP(text) {
    try {
      const data = await MAYAAPI.sendChat(text, MAYAState.sessionId);

      if (data.agent_used) {
        appendMessage('agent', `[ → INVOKING ${data.agent_used.toUpperCase()} ]`);
        MAYAAgents.setActive(data.agent_used);
      }

      appendMessage('maya', data.response || 'No response received.');
      MAYAState.messageHistory.push({
        role: 'assistant',
        content: data.response,
        agent: data.agent_used
      });
    } catch (err) {
      appendMessage('error', `Failed to reach backend: ${err.message}`);
    } finally {
      updateState({ isThinking: false });
    }
  }

  // ─── Streaming Support ────────────────────────────────
  function startStreamingMessage() {
    streamBuffer = '';
    const msgEl = document.createElement('div');
    msgEl.className = 'chat-message maya-msg';

    const prefix = document.createElement('span');
    prefix.className = 'chat-prefix maya';
    prefix.textContent = 'M·A·Y·A ❯';

    const textEl = document.createElement('span');
    textEl.className = 'chat-text streaming';
    textEl.textContent = '';

    msgEl.appendChild(prefix);
    msgEl.appendChild(textEl);
    messagesContainer.appendChild(msgEl);

    currentStreamEl = textEl;
    scrollToBottom();
  }

  function appendStreamToken(token) {
    if (!currentStreamEl) {
      startStreamingMessage();
    }
    streamBuffer += token;
    currentStreamEl.textContent = streamBuffer;
    scrollToBottom();
  }

  function finalizeStream(data) {
    if (currentStreamEl) {
      currentStreamEl.classList.remove('streaming');
      currentStreamEl = null;
    }

    // Show agent if used
    if (data && data.agent_used) {
      // Insert agent indicator before the MAYA message
      const mayaMsg = messagesContainer.lastElementChild;
      const agentEl = document.createElement('div');
      agentEl.className = 'chat-message agent-msg';
      agentEl.innerHTML = `<span class="chat-prefix agent">→</span><span class="chat-text">[ → INVOKING ${data.agent_used.toUpperCase()} ]</span>`;
      messagesContainer.insertBefore(agentEl, mayaMsg);

      MAYAAgents.setActive(data.agent_used);
    }

    // Save to history
    MAYAState.messageHistory.push({
      role: 'assistant',
      content: streamBuffer,
      agent: data ? data.agent_used : null
    });

    streamBuffer = '';
    updateState({ isThinking: false });
  }

  // ─── Append Message ───────────────────────────────────
  function appendMessage(type, text) {
    const msgEl = document.createElement('div');
    msgEl.className = `chat-message ${type}-msg`;

    let prefixText = '';
    let prefixClass = '';

    switch (type) {
      case 'user':
        prefixText = 'YOU ❯';
        prefixClass = 'user';
        break;
      case 'maya':
        prefixText = 'M·A·Y·A ❯';
        prefixClass = 'maya';
        break;
      case 'error':
        prefixText = '✖ ERROR ❯';
        prefixClass = 'error';
        break;
      case 'agent':
        prefixText = '→';
        prefixClass = 'agent';
        break;
      default:
        prefixText = '●';
        prefixClass = 'user';
    }

    const prefix = document.createElement('span');
    prefix.className = `chat-prefix ${prefixClass}`;
    prefix.textContent = prefixText;

    const textEl = document.createElement('span');
    textEl.className = 'chat-text';
    textEl.textContent = text;

    msgEl.appendChild(prefix);
    msgEl.appendChild(textEl);
    messagesContainer.appendChild(msgEl);

    scrollToBottom();
  }

  // ─── History Navigation ───────────────────────────────
  function recallHistory() {
    if (MAYAState.inputHistory.length === 0) return;

    if (MAYAState.inputHistoryIndex === undefined) {
      MAYAState.inputHistoryIndex = MAYAState.inputHistory.length;
    }

    MAYAState.inputHistoryIndex = Math.max(0, MAYAState.inputHistoryIndex - 1);
    chatInput.value = MAYAState.inputHistory[MAYAState.inputHistoryIndex] || '';
  }

  // ─── Clear Chat ───────────────────────────────────────
  function clearChat() {
    messagesContainer.innerHTML = '';
    MAYAState.messageHistory = [];
    MAYAState.inputHistory = [];
    MAYAState.inputHistoryIndex = 0;

    // Show welcome again
    const welcome = document.createElement('div');
    welcome.className = 'chat-welcome';
    welcome.innerHTML = `<span class="chat-prefix maya">M·A·Y·A ❯</span><span class="chat-text">New session initialized. All agents standing by.</span>`;
    messagesContainer.appendChild(welcome);
  }

  // ─── Disable / Enable Input ───────────────────────────
  function setInputEnabled(enabled) {
    chatInput.disabled = !enabled;
    if (!enabled) {
      chatInput.placeholder = 'BACKEND OFFLINE — RECONNECTING...';
    } else {
      chatInput.placeholder = 'Enter command...';
    }
  }

  // ─── Inject Text (from voice) ─────────────────────────
  function injectAndSend(text) {
    chatInput.value = text;
    sendMessage(text);
  }

  // ─── Scroll ───────────────────────────────────────────
  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    });
  }

  // Helper to call updateState from app.js (set after load)
  function updateState(changes) {
    if (typeof MAYAApp !== 'undefined' && MAYAApp.updateState) {
      MAYAApp.updateState(changes);
    }
  }

  return {
    init,
    sendMessage,
    appendMessage,
    appendStreamToken,
    finalizeStream,
    startStreamingMessage,
    clearChat,
    setInputEnabled,
    injectAndSend,
    scrollToBottom
  };
})();
