"""Agent registry and configuration, primary assignments, dependencies, and team presets."""
import hashlib
import os

from . import security, timeutil
from .db import dumps, loads, new_id
from .settings import APPROVAL_CHOICES, SANDBOX_CHOICES

AGENT_IDS = ["agent-0%d" % n for n in range(1, 8)]
# Slot order: Manager, SEO Caption Bot, Loader, Scheduler, Posting Bot, Video Editor, RVS (existing characters).
SPRITES = ["mgr", "cap", "in", "sch", "pack", "ved", "rvs"]
SPRITE_LABELS = {"mgr": "Green", "cap": "Blue", "in": "Grey", "sch": "Purple", "pack": "Pink",
                 "ved": "Orange", "rvs": "Lime"}
DEFAULT_ROLE = "Unassigned"
DEFAULT_PERSONALITY = "Friendly general-purpose AI assistant"
DEFAULT_PERMISSIONS = {"sandbox": "read-only", "network": False, "approval": "on-request"}

PRESETS = [
    {"id": "default", "name": "Default Office", "summary": "Seven unassigned agents, Agent 1 to Agent 7.",
     "agents": [{"display_name": "Agent %d" % n, "role": DEFAULT_ROLE, "description": "", "instructions": ""}
                for n in range(1, 8)]},
    {"id": "vibe-coding", "name": "Vibe Coding Team", "summary": "A small software team that plans, builds, tests, and ships.",
     "agents": [
         {"role": "Software Architect and Project Manager", "instructions": "Turn requests into a clear technical plan, break the work into steps, and keep scope and decisions written down."},
         {"role": "UI/UX Designer", "instructions": "Design clear, accessible screens and flows. Describe layouts, states, and copy precisely enough to build from."},
         {"role": "Frontend Engineer", "instructions": "Implement user interfaces that match the design. Keep components small and explain how to run and check your work."},
         {"role": "Backend Engineer", "instructions": "Implement server logic and APIs with input validation and clear error handling. Say how you verified it."},
         {"role": "Database Engineer", "instructions": "Design schemas, migrations, and queries. Protect data integrity and explain any change that is hard to undo."},
         {"role": "QA and Security Engineer", "instructions": "Test the work, report defects with steps to reproduce, and review for security problems before release."},
         {"role": "DevOps Engineer", "instructions": "Prepare build, run, and deployment steps. Never deploy or change live systems without explicit approval."},
     ]},
    {"id": "it-department", "name": "IT Department", "summary": "Seven IT specialists for planning, systems, security, and support.",
     "agents": [
         {"role": "IT Manager", "instructions": "Prioritise requests, assign owners, and summarise status and risks in plain language."},
         {"role": "Network Engineer", "instructions": "Analyse and document network designs and problems. Propose changes; do not apply them without approval."},
         {"role": "Systems Engineer", "instructions": "Investigate operating system and server issues, and write clear step-by-step procedures."},
         {"role": "Cybersecurity Analyst", "instructions": "Review configurations and reports for security weaknesses and recommend defensive fixes."},
         {"role": "Software Developer", "instructions": "Write and fix code, with a short explanation of what changed and how it was checked."},
         {"role": "Data Analyst", "instructions": "Analyse data files, state your method, and present findings with the figures that support them."},
         {"role": "Technical Support Specialist", "instructions": "Diagnose user problems and write friendly, step-by-step answers a non-technical person can follow."},
     ]},
    {"id": "personal", "name": "Personal Workforce", "summary": "Helpers for everyday personal work.",
     "agents": [
         {"role": "Personal Assistant", "instructions": "Help organise tasks, notes, and plans. Ask before doing anything that cannot be undone."},
         {"role": "Researcher", "instructions": "Research topics, separate facts from assumptions, and name your sources."},
         {"role": "Data Analyst", "instructions": "Analyse data files, state your method, and present findings with the figures that support them."},
         {"role": "Content Writer", "instructions": "Write and edit clear text in the requested tone and length."},
         {"role": "Project Coordinator", "instructions": "Track tasks, owners, and dates, and flag what is blocked or late."},
         {"role": "Automation Engineer", "instructions": "Write small scripts and automations, with instructions for running them safely."},
         {"role": "General Assistant", "instructions": "Take any general request and deliver a clear, complete result."},
     ]},
    {"id": "business", "name": "Business Workforce", "summary": "Analysts and writers for business work.",
     "agents": [
         {"role": "Executive Assistant", "instructions": "Prepare briefings, summaries, and drafts. Never send anything externally without approval."},
         {"role": "Business Analyst", "instructions": "Clarify requirements, analyse processes, and recommend options with their trade-offs."},
         {"role": "Market Researcher", "instructions": "Research markets and competitors, and name your sources and their dates."},
         {"role": "Marketing Specialist", "instructions": "Draft campaign ideas and marketing copy for review. Do not publish anything."},
         {"role": "Sales Analyst", "instructions": "Analyse sales data and pipelines, and explain the numbers behind each conclusion."},
         {"role": "Operations Analyst", "instructions": "Review operational data and procedures, and propose measurable improvements."},
         {"role": "Report Writer", "instructions": "Turn findings into well-structured reports with a short summary at the top."},
     ]},
]


class AgentService(object):
    def __init__(self, db, bus, settings, config):
        self.db = db
        self.bus = bus
        self.settings = settings
        self.config = config
        self.extra_private_roots = []

    # ---- seeding
    def seed(self):
        """Create the seven permanent agent records if they are missing. Never alters existing ones."""
        created = 0
        now = timeutil.iso()
        with self.db.tx() as c:
            for n, agent_id in enumerate(AGENT_IDS, 1):
                if c.execute("SELECT 1 FROM agents WHERE id = ?", (agent_id,)).fetchone():
                    continue
                c.execute(
                    "INSERT INTO agents(id, slot_number, display_name, role, personality, sprite_key, permissions, "
                    "allowed_tools, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (agent_id, n, "Agent %d" % n, DEFAULT_ROLE, DEFAULT_PERSONALITY, SPRITES[n - 1],
                     dumps(DEFAULT_PERMISSIONS), "[]", now, now))
                created += 1
        return created

    # ---- path policy
    def policy(self, roots=None):
        private = [self.config.data_dir, os.path.join(os.path.expanduser("~"), ".codex")] + list(self.extra_private_roots)
        return security.PathPolicy(self.settings.get("allowed_roots") if roots is None else roots, private)

    # ---- reading
    @staticmethod
    def _shape(row):
        row = dict(row)
        row["permissions"] = dict(DEFAULT_PERMISSIONS, **(loads(row.get("permissions"), {}) or {}))
        row["allowed_tools"] = loads(row.get("allowed_tools"), []) or []
        row["enabled"] = bool(row.get("enabled"))
        return row

    def list(self):
        return [self._shape(r) for r in self.db.all("SELECT * FROM agents ORDER BY slot_number")]

    def get(self, agent_id):
        security.agent_id(agent_id)
        row = self.db.one("SELECT * FROM agents WHERE id = ?", (agent_id,))
        if row is None:
            raise security.not_found("There is no agent with that id.")
        return self._shape(row)

    def workdir(self, agent, task=None):
        return (task or {}).get("working_directory") or agent.get("working_directory") or self.settings.get("default_workspace")

    def output_dir(self, agent):
        return agent.get("output_directory") or self.settings.get("default_output_dir")

    # ---- instructions sent to Codex
    def developer_instructions(self, agent):
        lines = [
            "You are %s, one of seven agents in AGENTS HQ, a local application that manages a small AI workforce "
            "for its user." % agent["display_name"],
            "Your role: %s." % (agent["role"] if agent["role"] != DEFAULT_ROLE else "general assistant (no role assigned yet)"),
        ]
        if agent.get("description"):
            lines.append("About this role: %s" % agent["description"])
        if agent.get("personality"):
            lines.append("Tone and personality: %s" % agent["personality"])
        if agent.get("instructions"):
            lines.append("Standing instructions from the user:\n%s" % agent["instructions"])
        lines.append(
            "When you finish a request, state plainly what you did and list the full path of every file you created "
            "or changed. Never say an action was done unless you did it. If something is blocked or needs the user's "
            "approval, say so instead of working around it.")
        if agent["permissions"].get("sandbox") == "workspace-write":
            lines.append("Save deliverable files inside this folder unless told otherwise: %s" % self.output_dir(agent))
        return "\n\n".join(lines)

    def config_hash(self, agent):
        return hashlib.sha256(self.developer_instructions(agent).encode("utf-8")).hexdigest()[:16]

    # ---- updating
    def update(self, agent_id, body, known_models=None, known_tools=None):
        agent = self.get(agent_id)
        if not isinstance(body, dict):
            raise security.bad_request("Agent settings must be an object.")
        fields = {}
        if "display_name" in body:
            fields["display_name"] = security.text(body["display_name"], "Name", 40, required=True, multiline=False)
        if "role" in body:
            fields["role"] = security.text(body["role"], "Role", 80, multiline=False) or DEFAULT_ROLE
        if "description" in body:
            fields["description"] = security.text(body["description"], "Description", 600)
        if "personality" in body:
            fields["personality"] = security.text(body["personality"], "Personality", 400)
        if "instructions" in body:
            fields["instructions"] = security.text(body["instructions"], "Instructions", 8000)
        if "sprite_key" in body:
            fields["sprite_key"] = security.choice(body["sprite_key"], "Character", SPRITES)
        if "model" in body:
            model = security.text(body["model"], "Model", 80, multiline=False) or None
            if model and known_models is not None and model not in known_models:
                raise security.bad_request("That model is not offered by the connected Codex.")
            fields["model"] = model
        if "reasoning_effort" in body:
            effort = security.text(body["reasoning_effort"], "Reasoning effort", 20, multiline=False) or None
            if effort and not effort.isalpha():
                raise security.bad_request("That reasoning effort is not valid.")
            fields["reasoning_effort"] = effort
        policy = self.policy()
        for key, label in (("working_directory", "Working folder"), ("output_directory", "Output folder")):
            if key in body:
                value = body[key]
                fields[key] = policy.check_workdir(value) if value else None
        if "permissions" in body:
            perms = body["permissions"]
            if not isinstance(perms, dict):
                raise security.bad_request("Permissions must be an object.")
            merged = dict(agent["permissions"])
            if "sandbox" in perms:
                merged["sandbox"] = security.choice(perms["sandbox"], "Access level", SANDBOX_CHOICES)
            if "network" in perms:
                merged["network"] = security.boolean(perms["network"], "Network access")
            if "approval" in perms:
                merged["approval"] = security.choice(perms["approval"], "Approval preference", APPROVAL_CHOICES)
            if merged["sandbox"] == "read-only":
                merged["network"] = False
            fields["permissions"] = dumps(merged)
        if "allowed_tools" in body:
            tools = body["allowed_tools"]
            if not isinstance(tools, list) or len(tools) > 50:
                raise security.bad_request("Allowed integrations must be a list.")
            clean = []
            for item in tools:
                name = security.text(item, "Integration name", 80, required=True, multiline=False)
                if known_tools is not None and name not in known_tools:
                    raise security.bad_request("The integration '%s' is not available in the connected Codex." % name)
                if name not in clean:
                    clean.append(name)
            fields["allowed_tools"] = dumps(clean)
        if "enabled" in body:
            fields["enabled"] = 1 if security.boolean(body["enabled"], "Enabled") else 0
        if not fields:
            return agent
        fields["updated_at"] = timeutil.iso()
        sets = ", ".join("%s = ?" % k for k in fields)
        self.db.execute("UPDATE agents SET %s WHERE id = ?" % sets, list(fields.values()) + [agent_id])
        updated = self.get(agent_id)
        changed = sorted(k for k in fields if k != "updated_at")
        self.bus.publish("agent.updated", {"agent": updated, "changed": changed}, agent_id=agent_id,
                         log="%s was configured (%s)." % (updated["display_name"], ", ".join(c.replace("_", " ") for c in changed)),
                         category="info")
        return updated

    # ---- presets
    def presets(self):
        out = []
        for preset in PRESETS:
            agents = []
            for n, spec in enumerate(preset["agents"], 1):
                agents.append({"agent_id": AGENT_IDS[n - 1],
                               "display_name": spec.get("display_name") or spec["role"],
                               "role": spec["role"], "description": spec.get("description", ""),
                               "instructions": spec.get("instructions", "")})
            out.append({"id": preset["id"], "name": preset["name"], "summary": preset["summary"], "agents": agents})
        return out

    def apply_preset(self, preset_id):
        """Set names, roles, and instructions only. Threads, history, permissions, and assignments are untouched."""
        preset = next((p for p in self.presets() if p["id"] == preset_id), None)
        if preset is None:
            raise security.not_found("There is no team preset with that id.")
        now = timeutil.iso()
        with self.db.tx() as c:
            for spec in preset["agents"]:
                c.execute("UPDATE agents SET display_name = ?, role = ?, description = ?, instructions = ?, updated_at = ? "
                          "WHERE id = ?", (spec["display_name"][:40], spec["role"], spec["description"],
                                           spec["instructions"], now, spec["agent_id"]))
        for agent in self.list():
            self.bus.publish("agent.updated", {"agent": agent, "changed": ["display_name", "role", "instructions"]},
                             agent_id=agent["id"])
        self.bus.publish("preset.applied", {"preset": preset["id"]},
                         log="Team preset applied: %s." % preset["name"], category="info")
        return preset


class TaskService(object):
    """One primary assignment per agent, with an optional schedule."""

    def __init__(self, db, bus, settings, agents):
        self.db = db
        self.bus = bus
        self.settings = settings
        self.agents = agents

    @staticmethod
    def _shape_schedule(row):
        if row is None:
            return None
        row = dict(row)
        row["recurrence"] = loads(row["recurrence"], {})
        row["enabled"] = bool(row["enabled"])
        try:
            row["description"] = timeutil.describe(row["recurrence"], row["timezone"])
        except Exception:
            row["description"] = "Schedule"
        return row

    def _shape(self, row):
        if row is None:
            return None
        task = dict(row)
        task["enabled"] = bool(task["enabled"])
        task["in_batch"] = bool(task["in_batch"])
        task["schedule"] = self._shape_schedule(self.db.one("SELECT * FROM schedules WHERE task_id = ?", (task["id"],)))
        task["state"] = self.state(task)
        return task

    @staticmethod
    def state(task):
        if not task["enabled"]:
            return "disabled"
        if task["execution_mode"] == "one_time" and task["completed_at"]:
            return "completed"
        if task["schedule"] and task["schedule"]["enabled"] and task["schedule"]["next_run_at"]:
            return "scheduled"
        return "pending" if task["in_batch"] else "draft"

    def get_active(self, agent_id):
        return self._shape(self.db.one("SELECT * FROM tasks WHERE agent_id = ? AND archived_at IS NULL", (agent_id,)))

    def get(self, task_id):
        return self._shape(self.db.one("SELECT * FROM tasks WHERE id = ?", (task_id,)))

    def all_active(self):
        rows = self.db.all("SELECT * FROM tasks WHERE archived_at IS NULL")
        return {r["agent_id"]: self._shape(r) for r in rows}

    def schedules(self):
        rows = self.db.all("SELECT s.* FROM schedules s JOIN tasks t ON t.id = s.task_id "
                           "WHERE t.archived_at IS NULL ORDER BY s.next_run_at IS NULL, s.next_run_at")
        return [self._shape_schedule(r) for r in rows]

    # ---- saving
    def save(self, agent_id, body):
        agent = self.agents.get(agent_id)
        if not isinstance(body, dict):
            raise security.bad_request("The assignment must be an object.")
        current = self.get_active(agent_id)
        fields = {
            "title": security.text(body.get("title"), "Task title", 120, required=True, multiline=False),
            "prompt": security.text(body.get("prompt"), "Task prompt", 20000, required=True),
            "expected_output": security.text(body.get("expected_output"), "Expected output", 2000),
            "completion_criteria": security.text(body.get("completion_criteria"), "Completion criteria", 2000),
            "priority": security.choice(body.get("priority"), "Priority", ("low", "normal", "high"), "normal"),
            "execution_mode": security.choice(body.get("execution_mode"), "Execution mode", ("one_time", "repeatable"), "one_time"),
            "max_duration_sec": security.integer(body.get("max_duration_sec"), "Maximum duration", 60, 6 * 3600, None)
            if body.get("max_duration_sec") not in (None, "") else None,
            "max_retries": security.integer(body.get("max_retries"), "Retry limit", 0, 2, None)
            if body.get("max_retries") not in (None, "") else None,
            "enabled": 1 if security.boolean(body.get("enabled"), "Enabled", True) else 0,
        }
        workdir = body.get("working_directory")
        fields["working_directory"] = self.agents.policy().check_workdir(workdir) if workdir else None
        if "in_batch" in body:
            fields["in_batch"] = 1 if security.boolean(body["in_batch"], "Add to Run Everything") else 0
        schedule_body = body.get("schedule")
        schedule = self._validate_schedule(schedule_body) if schedule_body else None
        now = timeutil.iso()
        with self.db.tx() as c:
            if current is None:
                task_id = new_id("task")
                fields.setdefault("in_batch", 0)
                cols = ["id", "agent_id", "created_at", "updated_at"] + list(fields)
                c.execute("INSERT INTO tasks(%s) VALUES (%s)" % (", ".join(cols), ", ".join("?" * len(cols))),
                          [task_id, agent_id, now, now] + list(fields.values()))
            else:
                task_id = current["id"]
                if current["prompt"] != fields["prompt"] or current["execution_mode"] != fields["execution_mode"]:
                    fields["completed_at"] = None  # edited work is a new assignment, so it may run again
                fields["updated_at"] = now
                c.execute("UPDATE tasks SET %s WHERE id = ?" % ", ".join("%s = ?" % k for k in fields),
                          list(fields.values()) + [task_id])
            if "schedule" in body:
                self._write_schedule(c, agent_id, task_id, schedule, now)
        task = self.get(task_id)
        self.bus.publish("task.created" if current is None else "task.updated", {"task": task}, agent_id=agent_id,
                         log="Task %s for %s: %s." % ("assigned" if current is None else "updated",
                                                     agent["display_name"], task["title"]), category="info")
        return task

    def _validate_schedule(self, body):
        if not isinstance(body, dict):
            raise security.bad_request("The schedule must be an object.")
        tz = security.text(body.get("timezone") or self.settings.get("timezone"), "Time zone", 64, required=True, multiline=False)
        try:
            recurrence = timeutil.validate_recurrence(body.get("recurrence"), tz)
        except ValueError as exc:
            raise security.bad_request(str(exc))
        return {
            "recurrence": recurrence, "timezone": tz,
            "missed_execution_policy": security.choice(body.get("missed_execution_policy"), "Missed-run policy",
                                                       ("skip", "catch_up"), self.settings.get("missed_policy_default")),
            "overlap_policy": security.choice(body.get("overlap_policy"), "Overlap policy", ("skip", "queue"),
                                              self.settings.get("overlap_policy_default")),
            "enabled": 1 if security.boolean(body.get("enabled"), "Schedule enabled", True) else 0,
        }

    @staticmethod
    def _write_schedule(c, agent_id, task_id, schedule, now):
        if schedule is None:
            c.execute("DELETE FROM schedules WHERE task_id = ?", (task_id,))
            return
        next_run = timeutil.next_occurrence(schedule["recurrence"], schedule["timezone"]) if schedule["enabled"] else None
        row = c.execute("SELECT id FROM schedules WHERE task_id = ?", (task_id,)).fetchone()
        values = (dumps(schedule["recurrence"]), schedule["timezone"], timeutil.iso(next_run) if next_run else None,
                  schedule["missed_execution_policy"], schedule["overlap_policy"], schedule["enabled"], now)
        if row:
            c.execute("UPDATE schedules SET recurrence = ?, timezone = ?, next_run_at = ?, missed_execution_policy = ?, "
                      "overlap_policy = ?, enabled = ?, updated_at = ? WHERE id = ?", values + (row["id"],))
        else:
            c.execute("INSERT INTO schedules(id, agent_id, task_id, recurrence, timezone, next_run_at, "
                      "missed_execution_policy, overlap_policy, enabled, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (new_id("sch"), agent_id, task_id) + values[:6] + (now, now))

    def patch_schedule(self, schedule_id, body):
        row = self.db.one("SELECT * FROM schedules WHERE id = ?", (security.record_id(schedule_id, "schedule"),))
        if row is None:
            raise security.not_found("There is no schedule with that id.")
        current = self._shape_schedule(row)
        merged = {"recurrence": current["recurrence"], "timezone": current["timezone"],
                  "missed_execution_policy": current["missed_execution_policy"],
                  "overlap_policy": current["overlap_policy"], "enabled": current["enabled"]}
        merged.update({k: v for k, v in (body or {}).items() if k in merged})
        schedule = self._validate_schedule(merged)
        with self.db.tx() as c:
            self._write_schedule(c, row["agent_id"], row["task_id"], schedule, timeutil.iso())
        task = self.get(row["task_id"])
        self.bus.publish("task.updated", {"task": task}, agent_id=row["agent_id"],
                         log="Schedule %s for %s." % ("enabled" if schedule["enabled"] else "disabled", task["title"]),
                         category="info")
        return task["schedule"]

    def set_batch(self, agent_id, in_batch):
        task = self.get_active(agent_id)
        if task is None:
            raise security.conflict("Save an assignment for this agent first.", "no_assignment")
        self.db.execute("UPDATE tasks SET in_batch = ?, updated_at = ? WHERE id = ?",
                        (1 if in_batch else 0, timeutil.iso(), task["id"]))
        task = self.get(task["id"])
        self.bus.publish("task.updated", {"task": task}, agent_id=agent_id)
        return task

    def clear(self, agent_id):
        """Archive the assignment. Its runs and outputs stay in History."""
        task = self.get_active(agent_id)
        if task is None:
            return None
        with self.db.tx() as c:
            c.execute("DELETE FROM schedules WHERE task_id = ?", (task["id"],))
            c.execute("UPDATE tasks SET archived_at = ?, updated_at = ? WHERE id = ?",
                      (timeutil.iso(), timeutil.iso(), task["id"]))
        self.bus.publish("task.cleared", {"task_id": task["id"]}, agent_id=agent_id,
                         log="Assignment cleared: %s." % task["title"], category="info")
        return task

    def mark_completed(self, task_id):
        self.db.execute("UPDATE tasks SET completed_at = ?, updated_at = ? WHERE id = ?",
                        (timeutil.iso(), timeutil.iso(), task_id))


class DependencyService(object):
    """Optional, user-configured hand-offs between agents."""

    def __init__(self, db, bus, settings):
        self.db = db
        self.bus = bus
        self.settings = settings

    @staticmethod
    def _shape(row):
        row = dict(row)
        row["enabled"] = bool(row["enabled"])
        row["require_approval"] = bool(row["require_approval"])
        return row

    def list(self):
        return [self._shape(r) for r in self.db.all("SELECT * FROM dependencies ORDER BY created_at")]

    def active(self):
        if not self.settings.get("collaboration_enabled"):
            return []
        return [d for d in self.list() if d["enabled"]]

    def _would_cycle(self, source, destination, ignore_id=None):
        edges = {}
        for d in self.list():
            if d["id"] != ignore_id:
                edges.setdefault(d["source_agent_id"], set()).add(d["destination_agent_id"])
        edges.setdefault(source, set()).add(destination)
        seen, stack = set(), [destination]
        while stack:
            node = stack.pop()
            if node == source:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack.extend(edges.get(node, ()))
        return False

    def create(self, body):
        if not self.settings.get("collaboration_enabled"):
            raise security.conflict("Turn on collaboration before adding hand-offs.", "collaboration_disabled")
        source = security.agent_id((body or {}).get("source_agent_id"))
        dest = security.agent_id((body or {}).get("destination_agent_id"))
        if source == dest:
            raise security.bad_request("An agent cannot hand work to itself.")
        if self.db.one("SELECT 1 FROM dependencies WHERE source_agent_id = ? AND destination_agent_id = ?", (source, dest)):
            raise security.conflict("That hand-off already exists.")
        if self._would_cycle(source, dest):
            raise security.bad_request("That hand-off would create a loop between agents.", "cycle")
        dep_id = new_id("dep")
        self.db.execute(
            "INSERT INTO dependencies(id, source_agent_id, destination_agent_id, condition, transfer, require_approval, "
            "enabled, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (dep_id, source, dest,
             security.choice(body.get("condition"), "Condition", ("on_success", "on_finish"), "on_success"),
             security.choice(body.get("transfer"), "Transfer", ("result", "none"), "result"),
             1 if security.boolean(body.get("require_approval"), "Approval before hand-off", False) else 0,
             1, timeutil.iso()))
        dep = self._shape(self.db.one("SELECT * FROM dependencies WHERE id = ?", (dep_id,)))
        self.bus.publish("dependency.changed", {"dependencies": self.list()},
                         log="Hand-off configured: %s to %s." % (source, dest), category="info")
        return dep

    def update(self, dep_id, body):
        row = self.db.one("SELECT * FROM dependencies WHERE id = ?", (security.record_id(dep_id, "hand-off"),))
        if row is None:
            raise security.not_found("There is no hand-off with that id.")
        fields = {}
        body = body or {}
        if "condition" in body:
            fields["condition"] = security.choice(body["condition"], "Condition", ("on_success", "on_finish"))
        if "transfer" in body:
            fields["transfer"] = security.choice(body["transfer"], "Transfer", ("result", "none"))
        if "require_approval" in body:
            fields["require_approval"] = 1 if security.boolean(body["require_approval"], "Approval before hand-off") else 0
        if "enabled" in body:
            fields["enabled"] = 1 if security.boolean(body["enabled"], "Enabled") else 0
        if fields:
            self.db.execute("UPDATE dependencies SET %s WHERE id = ?" % ", ".join("%s = ?" % k for k in fields),
                            list(fields.values()) + [dep_id])
        self.bus.publish("dependency.changed", {"dependencies": self.list()})
        return self._shape(self.db.one("SELECT * FROM dependencies WHERE id = ?", (dep_id,)))

    def delete(self, dep_id):
        cur = self.db.execute("DELETE FROM dependencies WHERE id = ?", (security.record_id(dep_id, "hand-off"),))
        if cur.rowcount == 0:
            raise security.not_found("There is no hand-off with that id.")
        self.bus.publish("dependency.changed", {"dependencies": self.list()},
                         log="Hand-off removed.", category="info")
