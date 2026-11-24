PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY CHECK (id GLOB 'agent-0[1-7]'),
  slot_number INTEGER NOT NULL UNIQUE CHECK (slot_number BETWEEN 1 AND 7),
  display_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'Unassigned',
  description TEXT NOT NULL DEFAULT '',
  personality TEXT NOT NULL DEFAULT 'Friendly general-purpose AI assistant',
  instructions TEXT NOT NULL DEFAULT '',
  sprite_key TEXT NOT NULL,
  model TEXT,
  reasoning_effort TEXT,
  working_directory TEXT,
  output_directory TEXT,
  permissions TEXT NOT NULL DEFAULT '{}',
  allowed_tools TEXT NOT NULL DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_threads (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  provider TEXT NOT NULL DEFAULT 'codex',
  account_scope TEXT NOT NULL DEFAULT '',
  provider_thread_id TEXT,
  origin TEXT NOT NULL DEFAULT 'created',
  status TEXT NOT NULL DEFAULT 'uninitialized',
  status_detail TEXT,
  applied_config_hash TEXT,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  archived_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_threads_active ON agent_threads(agent_id, archived_at);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  title TEXT NOT NULL,
  prompt TEXT NOT NULL,
  expected_output TEXT NOT NULL DEFAULT '',
  completion_criteria TEXT NOT NULL DEFAULT '',
  priority TEXT NOT NULL DEFAULT 'normal',
  execution_mode TEXT NOT NULL DEFAULT 'one_time',
  working_directory TEXT,
  max_duration_sec INTEGER,
  max_retries INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1,
  in_batch INTEGER NOT NULL DEFAULT 0,
  completed_at TEXT,
  archived_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedules (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id),
  recurrence TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'Asia/Manila',
  next_run_at TEXT,
  last_run_at TEXT,
  last_occurrence_id TEXT,
  missed_execution_policy TEXT NOT NULL DEFAULT 'skip',
  overlap_policy TEXT NOT NULL DEFAULT 'skip',
  enabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_runs (
  id TEXT PRIMARY KEY,
  task_id TEXT REFERENCES tasks(id),
  agent_id TEXT NOT NULL REFERENCES agents(id),
  kind TEXT DEFAULT 'task',
  title TEXT DEFAULT '',
  prompt TEXT DEFAULT '',
  attachments TEXT DEFAULT '[]',
  working_directory TEXT,
  provider_thread_id TEXT,
  provider_turn_id TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  trigger_type TEXT DEFAULT 'manual',
  status TEXT DEFAULT 'queued',
  status_detail TEXT DEFAULT '',
  activity TEXT DEFAULT '',
  queued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  retry_count INTEGER DEFAULT 0,
  max_retries INTEGER,
  max_duration_sec INTEGER,
  error_message TEXT DEFAULT '',
  result_summary TEXT DEFAULT '',
  occurrence_id TEXT,
  batch_id TEXT,
  parent_run_id TEXT,
  root_run_id TEXT,
  depth INTEGER DEFAULT 0,
  waiting_on_run_id TEXT,
  priority INTEGER DEFAULT 0,
  cwd TEXT,
  meta TEXT DEFAULT '{}',
  error_kind TEXT,
  usage TEXT,
  side_effects INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_task_runs_agent ON task_runs(agent_id, queued_at);
CREATE INDEX IF NOT EXISTS idx_task_runs_status ON task_runs(status);
CREATE INDEX IF NOT EXISTS idx_task_runs_batch ON task_runs(batch_id);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  thread_id TEXT,
  run_id TEXT,
  provider_message_id TEXT,
  role TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'text',
  content TEXT,
  meta TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'complete',
  created_at TEXT NOT NULL,
  seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_agent ON messages(agent_id, seq);

CREATE TABLE IF NOT EXISTS outputs (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  run_id TEXT,
  task_id TEXT,
  title TEXT NOT NULL,
  output_type TEXT NOT NULL DEFAULT 'text',
  content TEXT,
  verified_file_path TEXT,
  mime_type TEXT,
  size_bytes INTEGER,
  status TEXT NOT NULL DEFAULT 'completed',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outputs_agent ON outputs(agent_id, created_at);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  run_id TEXT,
  provider_request_id TEXT,
  approval_type TEXT NOT NULL,
  request_details TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending',
  decision TEXT,
  requested_at TEXT NOT NULL,
  resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_approvals_pending ON approvals(status, requested_at);

CREATE TABLE IF NOT EXISTS agent_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id TEXT,
  run_id TEXT,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info',
  category TEXT,
  log_text TEXT,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_events_created ON agent_events(id);

CREATE TABLE IF NOT EXISTS dependencies (
  id TEXT PRIMARY KEY,
  source_agent_id TEXT NOT NULL REFERENCES agents(id),
  destination_agent_id TEXT NOT NULL REFERENCES agents(id),
  condition TEXT NOT NULL DEFAULT 'on_success',
  transfer TEXT NOT NULL DEFAULT 'result',
  require_approval INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS status_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status_transitions_run ON status_transitions(run_id, id);
