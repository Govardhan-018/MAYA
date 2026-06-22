# Maya Code Agent — Frontend Integration Guide

## API Endpoints

The agent exposes four actions through the standard `execute()` entry point.
All calls go through the brain's normal routing (`POST /api/chat` or direct agent call).

### 1. Start a Task

```json
{
  "action": "start_task",
  "parameters": {
    "goal": "Add user authentication to the Flask app",
    "project_root": "C:/Users/dev/myproject",
    "dry_run": false,
    "context": "optional extra context for the LLM"
  }
}
```

**Response** (immediate — work runs in background):
```json
{
  "status": "success",
  "action": "start_task",
  "data": { "job_id": "code_a1b2c3d4e5f6", "message": "Task started: ..." }
}
```

### 2. Poll Status

```json
{ "action": "get_status", "parameters": { "job_id": "code_a1b2c3d4e5f6" } }
```

**Response** — `StatusSnapshot`:
```json
{
  "status": "success",
  "action": "get_status",
  "data": {
    "job_id": "code_a1b2c3d4e5f6",
    "state": "RUNNING",
    "phase": "EXECUTING",
    "goal": "Add user authentication",
    "progress": 0.6,
    "current_step": "Creating auth middleware",
    "step_index": 3,
    "total_steps": 5,
    "log_tail": ["Step 1/5: Analyzing project", "Step 2/5: Installing deps", "..."],
    "started_at": "2025-01-15T10:30:00+00:00",
    "updated_at": "2025-01-15T10:30:45+00:00",
    "done": false,
    "summary": null,
    "error": null,
    "dry_run": false
  }
}
```

### 3. Cancel a Task

```json
{ "action": "cancel_task", "parameters": { "job_id": "code_a1b2c3d4e5f6" } }
```

### 4. List All Jobs

```json
{ "action": "list_jobs", "parameters": {} }
```

---

## Polling Pattern

```javascript
async function pollCodeJob(jobId, interval = 2000) {
  const poll = setInterval(async () => {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: `get_status ${jobId}`,
      }),
    });
    const data = await resp.json();
    const snap = data.data || data;

    updateCodePanel(snap);

    if (snap.done) {
      clearInterval(poll);
    }
  }, interval);
}
```

---

## State → Phase → UI Mapping

| `state`     | `phase`     | Suggested UI              |
|-------------|-------------|---------------------------|
| `PENDING`   | `ANALYZING` | Spinner + "Scanning..."   |
| `RUNNING`   | `PLANNING`  | Brain icon + "Planning…"  |
| `RUNNING`   | `EXECUTING` | Progress bar + step info  |
| `RUNNING`   | `VERIFYING` | Check icon + "Verifying…" |
| `RUNNING`   | `FIXING`    | Wrench icon + "Fixing…"   |
| `COMPLETED` | `DONE`      | Green check + summary     |
| `FAILED`    | `DONE`      | Red X + error message     |
| `CANCELLED` | *any*       | Grey dash + "Cancelled"   |

---

## Key Fields

- **`progress`** — float 0.0–1.0, suitable for a progress bar
- **`log_tail`** — last 25 log lines, suitable for a scrolling terminal view
- **`current_step`** — human-readable description of current work
- **`step_index` / `total_steps`** — "Step 3 of 5"
- **`summary`** — populated on completion with a multi-line report
- **`error`** — populated on failure

---

## Disk Mirror

Job snapshots are mirrored to `system/code_jobs/{job_id}.json` for debugging
and crash recovery. These are plain JSON files matching the `StatusSnapshot` schema.
