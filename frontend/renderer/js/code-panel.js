// ═══════════════════════════════════════════════════════════
// code-panel.js — Maya Code Agent UI Controller
// Multi-task, back navigation, collapsible logs
// ═══════════════════════════════════════════════════════════

const MAYACodePanel = (() => {
  let _pollTimer = null;
  let _currentJobId = null;
  let _isOpen = false;
  let _logCollapsed = false;
  let _currentView = 'jobs'; // 'jobs' | 'form' | 'detail'

  function $(id) { return document.getElementById(id); }

  // ─── Init ───────────────────────────────────────────────
  function init() {
    _on('code-toggle', 'click', toggle);
    _on('code-panel-close', 'click', close);
    _on('code-back-btn', 'click', goBack);
    _on('code-new-task-btn', 'click', () => switchView('form'));
    _on('code-start-btn', 'click', startTask);
    _on('code-panel-cancel', 'click', cancelTask);
    _on('code-history-toggle', 'click', toggleHistory);
    _on('code-log-toggle', 'click', toggleLog);

    const goalInput = $('code-goal');
    if (goalInput) {
      goalInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startTask(); }
      });
    }

    console.log('[MAYA] Code Panel initialized.');
  }

  function _on(id, event, fn) {
    const el = $(id);
    if (el) el.addEventListener(event, fn);
  }

  // ─── Panel Open / Close ────────────────────────────────
  function toggle() { _isOpen ? close() : open(); }

  function open() {
    const panel = $('code-panel');
    const btn = $('code-toggle');
    if (panel) panel.classList.remove('hidden');
    if (btn) btn.classList.add('active');
    _isOpen = true;
    switchView('jobs');
  }

  function close() {
    const panel = $('code-panel');
    const btn = $('code-toggle');
    if (panel) panel.classList.add('hidden');
    if (btn) btn.classList.remove('active');
    _isOpen = false;
    stopPolling();
  }

  // ─── View Switching ────────────────────────────────────
  function switchView(view) {
    _currentView = view;
    const views = ['code-view-jobs', 'code-view-form', 'code-view-detail'];
    views.forEach(id => {
      const el = $(id);
      if (el) el.classList.toggle('hidden', id !== `code-view-${view}`);
    });

    const backBtn = $('code-back-btn');
    const cancelBtn = $('code-panel-cancel');
    const badge = $('code-panel-badge');

    // Back button: show on form + detail, hide on jobs
    if (backBtn) backBtn.classList.toggle('hidden', view === 'jobs');

    // Cancel: only on detail when task is running
    if (view !== 'detail' && cancelBtn) cancelBtn.classList.add('hidden');

    // Refresh data when entering a view
    if (view === 'jobs') {
      stopPolling();
      refreshJobsList();
      if (badge) badge.classList.add('hidden');
    }
    if (view === 'detail' && _currentJobId) {
      startPolling();
    }
  }

  function goBack() {
    if (_currentView === 'detail' || _currentView === 'form') {
      switchView('jobs');
    }
  }

  // ─── Jobs List ─────────────────────────────────────────
  async function refreshJobsList() {
    const activeContainer = $('code-active-jobs');
    if (!activeContainer) return;

    try {
      const resp = await MAYAAPI.fetchJSON('/api/code/jobs');
      if (resp.status !== 'success') return;

      const jobs = resp.data.jobs || [];
      const active = jobs.filter(j => !j.done);
      const done = jobs.filter(j => j.done);

      // Active tasks
      activeContainer.innerHTML = '';
      if (active.length === 0) {
        activeContainer.innerHTML = '<div class="code-empty-state">No active tasks</div>';
      } else {
        for (const job of active) {
          activeContainer.appendChild(_buildJobCard(job, true));
        }
      }

      // History (done tasks)
      const histContainer = $('code-history');
      if (histContainer && !histContainer.classList.contains('hidden')) {
        histContainer.innerHTML = '';
        if (done.length === 0) {
          histContainer.innerHTML = '<div class="code-empty-state">No completed tasks</div>';
        } else {
          for (const job of done.reverse()) {
            histContainer.appendChild(_buildJobCard(job, false));
          }
        }
      }

      // Badge on statusbar toggle
      const toggleBtn = $('code-toggle');
      if (toggleBtn) {
        const runningCount = active.length;
        toggleBtn.textContent = runningCount > 0 ? `⟐ CODE (${runningCount})` : '⟐ CODE';
        toggleBtn.classList.toggle('active-jobs', runningCount > 0);
      }

    } catch (err) { /* backend offline */ }
  }

  function _buildJobCard(job, isActive) {
    const card = document.createElement('div');
    card.className = 'code-job-card' + (isActive ? ' active' : '');
    card.addEventListener('click', () => viewJob(job.job_id));

    const top = document.createElement('div');
    top.className = 'code-job-card-top';

    const goal = document.createElement('span');
    goal.className = 'code-job-goal';
    goal.textContent = job.goal;

    const state = document.createElement('span');
    state.className = 'code-job-state ' + job.state.toLowerCase();
    state.textContent = job.state;

    top.appendChild(goal);
    top.appendChild(state);
    card.appendChild(top);

    if (isActive) {
      const progress = document.createElement('div');
      progress.className = 'code-job-card-progress';

      const bar = document.createElement('div');
      bar.className = 'code-job-card-bar';
      bar.style.width = `${Math.round((job.progress || 0) * 100)}%`;

      const info = document.createElement('span');
      info.className = 'code-job-card-info';
      info.textContent = job.current_step || job.phase || '';

      progress.appendChild(bar);
      card.appendChild(progress);
      card.appendChild(info);
    }

    return card;
  }

  // ─── View Job Detail ───────────────────────────────────
  async function viewJob(jobId) {
    _currentJobId = jobId;
    switchView('detail');

    // Reset UI
    const log = $('code-log');
    if (log) log.innerHTML = '';
    const summary = $('code-summary');
    if (summary) summary.classList.add('hidden');

    try {
      const resp = await MAYAAPI.fetchJSON(`/api/code/status/${jobId}`);
      if (resp.status === 'success') {
        updateDetailUI(resp.data);
        if (!resp.data.done) startPolling();
        else stopPolling();
      }
    } catch (err) {
      flashError('Could not load job');
    }
  }

  // ─── Start Task ────────────────────────────────────────
  async function startTask() {
    const projectRoot = ($('code-project-root') || {}).value || '';
    const goal = ($('code-goal') || {}).value || '';
    const dryRun = ($('code-dry-run') || {}).checked || false;

    if (!projectRoot.trim()) { flashError('Project path is required'); return; }
    if (!goal.trim()) { flashError('Goal is required'); return; }

    const startBtn = $('code-start-btn');
    if (startBtn) { startBtn.disabled = true; startBtn.textContent = 'STARTING...'; }

    try {
      const resp = await MAYAAPI.fetchJSON('/api/code/start', {
        method: 'POST',
        body: JSON.stringify({
          goal: goal.trim(),
          project_root: projectRoot.trim(),
          dry_run: dryRun,
        }),
      });

      if (resp.status === 'success') {
        _currentJobId = resp.data.job_id;
        // Clear form for next use
        const goalEl = $('code-goal');
        if (goalEl) goalEl.value = '';
        viewJob(_currentJobId);
      } else {
        flashError(resp.message || 'Failed to start task');
      }
    } catch (err) {
      flashError('Backend unreachable: ' + err.message);
    } finally {
      if (startBtn) { startBtn.disabled = false; startBtn.textContent = 'START TASK'; }
    }
  }

  // ─── Cancel Task ───────────────────────────────────────
  async function cancelTask() {
    if (!_currentJobId) return;
    try {
      await MAYAAPI.fetchJSON('/api/code/cancel', {
        method: 'POST',
        body: JSON.stringify({ job_id: _currentJobId }),
      });
    } catch (err) {
      console.warn('[Code Panel] Cancel failed:', err.message);
    }
  }

  // ─── Polling ───────────────────────────────────────────
  function startPolling() {
    stopPolling();
    _pollTimer = setInterval(pollStatus, 1500);
    pollStatus();
  }

  function stopPolling() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
  }

  async function pollStatus() {
    if (!_currentJobId) { stopPolling(); return; }
    try {
      const resp = await MAYAAPI.fetchJSON(`/api/code/status/${_currentJobId}`);
      if (resp.status === 'success') {
        updateDetailUI(resp.data);
        if (resp.data.done) {
          stopPolling();
          refreshJobsList();
        }
      }
    } catch (err) { /* keep polling */ }
  }

  // ─── Detail View UI ────────────────────────────────────
  function updateDetailUI(data) {
    const goalEl = $('code-detail-goal');
    const stateEl = $('code-state');
    const phaseEl = $('code-phase');
    const stepInfo = $('code-step-info');
    const progressBar = $('code-progress-bar');
    const currentStep = $('code-current-step');
    const logEl = $('code-log');
    const badge = $('code-panel-badge');
    const cancelBtn = $('code-panel-cancel');
    const summarySection = $('code-summary');
    const summaryText = $('code-summary-text');

    if (goalEl) goalEl.textContent = data.goal;

    if (stateEl) {
      stateEl.textContent = data.state;
      stateEl.className = 'code-state ' + data.state.toLowerCase();
    }
    if (phaseEl) phaseEl.textContent = data.phase;

    if (stepInfo) {
      stepInfo.textContent = data.total_steps > 0
        ? `${data.step_index} / ${data.total_steps}`
        : '—';
    }

    if (progressBar) progressBar.style.width = `${Math.round(data.progress * 100)}%`;
    if (currentStep) currentStep.textContent = data.current_step || 'Waiting...';

    // Badge
    if (badge) {
      badge.classList.remove('hidden', 'completed', 'failed');
      if (data.done) {
        if (data.state === 'COMPLETED') { badge.textContent = 'DONE'; badge.classList.add('completed'); }
        else if (data.state === 'FAILED') { badge.textContent = 'FAILED'; badge.classList.add('failed'); }
        else if (data.state === 'CANCELLED') { badge.textContent = 'CANCELLED'; badge.classList.add('failed'); }
      } else {
        badge.textContent = data.phase;
      }
    }

    // Cancel button: only if still running
    if (cancelBtn) cancelBtn.classList.toggle('hidden', data.done);

    // Subtask progress (v2 only)
    const subtasksSection = $('code-subtasks');
    const subtaskList = $('code-subtask-list');
    if (subtasksSection && subtaskList && data.version === 'v2' && data.subtasks) {
      subtasksSection.classList.remove('hidden');
      subtaskList.innerHTML = '';
      for (const st of data.subtasks) {
        const row = document.createElement('div');
        row.className = 'code-subtask-row ' + st.state.toLowerCase();

        const icon = document.createElement('span');
        icon.className = 'code-subtask-icon';
        if (st.state === 'COMPLETED') icon.textContent = '✓';
        else if (st.state === 'FAILED') icon.textContent = '✗';
        else if (st.state === 'RUNNING') icon.textContent = '▸';
        else if (st.state === 'SKIPPED') icon.textContent = '—';
        else icon.textContent = '○';

        const title = document.createElement('span');
        title.className = 'code-subtask-title';
        title.textContent = st.title;

        const budget = document.createElement('span');
        budget.className = 'code-subtask-budget';
        budget.textContent = `${st.actions_used}/${st.action_budget}`;

        row.appendChild(icon);
        row.appendChild(title);
        row.appendChild(budget);
        subtaskList.appendChild(row);
      }

      // v2 progress = completed subtasks / total
      if (data.total_subtasks > 0) {
        const completed = data.subtasks.filter(s => s.state === 'COMPLETED').length;
        if (stepInfo) stepInfo.textContent = `${data.subtask_index} / ${data.total_subtasks} subtasks`;
        if (!data.done && progressBar) {
          progressBar.style.width = `${Math.round((completed / data.total_subtasks) * 100)}%`;
        }
      }
      if (data.current_subtask && currentStep) {
        currentStep.textContent = data.current_subtask;
      }
    } else if (subtasksSection) {
      subtasksSection.classList.add('hidden');
    }

    // Log (only update if not collapsed)
    if (logEl && data.log_tail && !_logCollapsed) {
      logEl.innerHTML = '';
      for (const line of data.log_tail) {
        const div = document.createElement('div');
        div.className = 'code-log-line';
        if (line.includes('FAILED') || line.includes('error') || line.includes('FATAL')) div.classList.add('error');
        else if (line.includes('OK') || line.includes('passed') || line.includes('Fixed')) div.classList.add('success');
        div.textContent = line;
        logEl.appendChild(div);
      }
      logEl.scrollTop = logEl.scrollHeight;
    }

    // Summary on completion
    if (data.done && summarySection && summaryText) {
      if (data.summary) {
        summaryText.textContent = data.summary;
        summaryText.style.borderColor = '';
        summarySection.classList.remove('hidden');
      }
      if (data.error && !data.summary) {
        summaryText.textContent = `Error: ${data.error}`;
        summaryText.style.borderColor = 'rgba(248, 113, 113, 0.2)';
        summarySection.classList.remove('hidden');
      }
    }
  }

  // ─── Collapsible Log ───────────────────────────────────
  function toggleLog() {
    _logCollapsed = !_logCollapsed;
    const logEl = $('code-log');
    const toggleEl = $('code-log-toggle');
    if (logEl) logEl.classList.toggle('collapsed', _logCollapsed);
    if (toggleEl) toggleEl.textContent = _logCollapsed ? 'LIVE LOG ▸' : 'LIVE LOG ▾';
  }

  // ─── History Toggle ────────────────────────────────────
  function toggleHistory() {
    const hist = $('code-history');
    const toggle = $('code-history-toggle');
    if (!hist) return;

    const willShow = hist.classList.contains('hidden');
    hist.classList.toggle('hidden');
    if (toggle) toggle.textContent = willShow ? 'HISTORY ▾' : 'HISTORY ▸';
    if (willShow) refreshJobsList();
  }

  // ─── Helpers ───────────────────────────────────────────
  function flashError(msg) {
    const el = $('code-current-step');
    if (el) {
      const prev = el.textContent;
      el.textContent = msg;
      el.style.color = 'var(--accent-red)';
      setTimeout(() => { el.textContent = prev; el.style.color = ''; }, 3000);
    }
  }

  return { init, toggle, open, close };
})();
