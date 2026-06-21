// ═══════════════════════════════════════════════════════════
// agents.js — Dynamic Agent Status Panel
// ═══════════════════════════════════════════════════════════

const MAYAAgents = (() => {
  // Fallback list used when backend is offline
  const DEFAULT_AGENTS = [
    'gmail', 'news', 'weather', 'file', 'todo',
    'browser', 'youtube', 'notes', 'memory', 'project'
  ];

  let AGENTS = [...DEFAULT_AGENTS];
  let activeAgent = null;
  let agentTimeout = null;

  // ─── Initialize ────────────────────────────────────────
  function init() {
    clearAllActive();
    fetchAgentList();
  }

  // ─── Fetch Agent List from Backend ────────────────────
  async function fetchAgentList() {
    try {
      const data = await MAYAAPI.fetchJSON('/api/agents');
      if (data && data.agents && data.agents.length > 0) {
        AGENTS = data.agents.map(a => a.id.replace('_agent', ''));
        renderAgentList(data.agents);
      }
    } catch (err) {
      // Backend offline — keep defaults already in HTML
    }
  }

  // ─── Render Agent List into DOM ───────────────────────
  function renderAgentList(agents) {
    const list = document.getElementById('agents-list');
    if (!list) return;

    list.innerHTML = '';
    for (const agent of agents) {
      const li = document.createElement('li');
      const shortName = agent.id.replace('_agent', '');
      li.setAttribute('data-agent', shortName);

      const dot = document.createElement('span');
      dot.className = 'agent-dot';

      const label = document.createTextNode(agent.display_name);
      li.appendChild(dot);
      li.appendChild(label);
      list.appendChild(li);
    }
  }

  // ─── Set Active Agent ──────────────────────────────────
  function setActive(agentName) {
    if (!agentName) {
      clearAllActive();
      return;
    }

    const normalized = agentName.toLowerCase().replace(/[^a-z]/g, '');

    // Find matching agent
    const match = AGENTS.find(a => normalized.includes(a));
    if (!match) {
      clearAllActive();
      return;
    }

    // Clear previous
    clearAllActive();

    // Set new active
    activeAgent = match;
    const el = document.querySelector(`[data-agent="${match}"]`);
    if (el) {
      el.classList.add('active');
    }

    // Auto-clear after 10s if no update
    if (agentTimeout) clearTimeout(agentTimeout);
    agentTimeout = setTimeout(() => {
      clearAllActive();
    }, 10000);
  }

  // ─── Clear All ─────────────────────────────────────────
  function clearAllActive() {
    activeAgent = null;
    const items = document.querySelectorAll('#agents-list li');
    items.forEach(li => li.classList.remove('active'));
    if (agentTimeout) {
      clearTimeout(agentTimeout);
      agentTimeout = null;
    }
  }

  // ─── Get Active ────────────────────────────────────────
  function getActive() {
    return activeAgent;
  }

  // ─── Refresh (call after adding a plugin) ─────────────
  function refresh() {
    fetchAgentList();
  }

  return {
    init,
    setActive,
    clearAllActive,
    getActive,
    refresh,
    get AGENTS() { return AGENTS; }
  };
})();
