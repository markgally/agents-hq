"""Scheduling: recurrence maths, time zones, occurrences, missed runs, overlap, duplicates."""
import datetime as dt
import unittest

from tests.helpers import Harness
from agent_hq import timeutil
from agent_hq.security import ApiError

UTC = dt.timezone.utc


def utc(*args):
    return dt.datetime(*args, tzinfo=UTC)


class RecurrenceTests(unittest.TestCase):
    """Asia/Manila is UTC+8 with no daylight saving time."""
    tz = "Asia/Manila"

    def nxt(self, rec, after):
        return timeutil.next_occurrence(timeutil.validate_recurrence(rec, self.tz), self.tz, after)

    def test_daily_is_stored_in_utc(self):
        # 09:00 in Manila is 01:00 UTC.
        self.assertEqual(self.nxt({"type": "daily", "time": "09:00"}, utc(2026, 11, 24, 0, 0)), utc(2026, 11, 24, 1, 0))
        self.assertEqual(self.nxt({"type": "daily", "time": "09:00"}, utc(2026, 11, 24, 1, 0)), utc(2026, 11, 25, 1, 0))
        # 06:00 in Manila is 22:00 UTC on the previous day.
        self.assertEqual(self.nxt({"type": "daily", "time": "06:00"}, utc(2026, 11, 24, 12, 0)), utc(2026, 11, 24, 22, 0))

    def test_hourly(self):
        self.assertEqual(self.nxt({"type": "hourly", "minute": 30}, utc(2026, 11, 24, 3, 31)), utc(2026, 11, 24, 4, 30))
        self.assertEqual(self.nxt({"type": "hourly", "minute": 30}, utc(2026, 11, 24, 3, 29)), utc(2026, 11, 24, 3, 30))

    def test_weekly(self):
        # 24 Nov 2026 is a Tuesday. Monday 08:00 Manila -> Monday 00:00 UTC, 30 Nov.
        rec = {"type": "weekly", "weekdays": [0], "time": "08:00"}
        self.assertEqual(self.nxt(rec, utc(2026, 11, 24, 0, 0)), utc(2026, 11, 30, 0, 0))
        rec = {"type": "weekly", "weekdays": [1, 4], "time": "08:00"}  # Tuesday and Friday
        self.assertEqual(self.nxt(rec, utc(2026, 11, 24, 0, 0)), utc(2026, 11, 27, 0, 0))

    def test_monthly_uses_the_last_day_in_shorter_months(self):
        rec = {"type": "monthly", "day": 31, "time": "10:00"}
        self.assertEqual(self.nxt(rec, utc(2026, 11, 1, 0, 0)), utc(2026, 11, 30, 2, 0))
        self.assertEqual(self.nxt(rec, utc(2026, 11, 30, 2, 0)), utc(2026, 12, 31, 2, 0))
        self.assertEqual(self.nxt(rec, utc(2027, 2, 1, 0, 0)), utc(2027, 2, 28, 2, 0))
        rec = {"type": "monthly", "day": 15, "time": "10:00"}
        self.assertEqual(self.nxt(rec, utc(2026, 11, 24, 0, 0)), utc(2026, 12, 15, 2, 0))

    def test_once(self):
        rec = {"type": "once", "run_at": "2026-12-01T09:00"}
        self.assertEqual(self.nxt(rec, utc(2026, 11, 24, 0, 0)), utc(2026, 12, 1, 1, 0))
        self.assertIsNone(self.nxt(rec, utc(2026, 12, 1, 1, 0)))

    def test_cron(self):
        rec = {"type": "cron", "cron": "*/15 9-10 * * 1-5"}
        self.assertEqual(self.nxt(rec, utc(2026, 11, 24, 1, 0)), utc(2026, 11, 24, 1, 15))   # Tue 09:15 Manila
        self.assertEqual(self.nxt(rec, utc(2026, 11, 27, 2, 45)), utc(2026, 11, 30, 1, 0))   # Fri 10:45 -> Mon 09:00

    def test_start_and_end_dates(self):
        rec = {"type": "daily", "time": "09:00", "start_date": "2026-12-10", "end_date": "2026-12-11"}
        self.assertEqual(self.nxt(rec, utc(2026, 11, 24, 0, 0)), utc(2026, 12, 10, 1, 0))
        self.assertEqual(self.nxt(rec, utc(2026, 12, 10, 1, 0)), utc(2026, 12, 11, 1, 0))
        self.assertIsNone(self.nxt(rec, utc(2026, 12, 11, 1, 0)))

    def test_invalid_recurrences_are_rejected(self):
        bad = [{"type": "sometimes"}, {"type": "daily", "time": "25:00"}, {"type": "hourly", "minute": 61},
               {"type": "weekly", "weekdays": [], "time": "09:00"}, {"type": "weekly", "weekdays": [9], "time": "09:00"},
               {"type": "monthly", "day": 0, "time": "09:00"}, {"type": "cron", "cron": "* * *"},
               {"type": "cron", "cron": "61 * * * *"}, {"type": "once", "run_at": "tomorrow"},
               {"type": "daily", "time": "09:00", "start_date": "2026-12-11", "end_date": "2026-12-10"}]
        for rec in bad:
            with self.assertRaises((ApiError, ValueError), msg=str(rec)):
                timeutil.validate_recurrence(rec, self.tz)
        with self.assertRaises((ApiError, ValueError)):
            timeutil.validate_recurrence({"type": "daily", "time": "09:00"}, "Mars/Olympus_Mons")

    def test_other_zone(self):
        self.assertEqual(timeutil.next_occurrence(timeutil.validate_recurrence({"type": "daily", "time": "09:00"}, "UTC"),
                                                  "UTC", utc(2026, 11, 24, 0, 0)), utc(2026, 11, 24, 9, 0))


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()  # scheduler thread interval is one hour in tests; tick() is called directly
        self.sched = self.h.app.scheduler

    def tearDown(self):
        self.h.close()

    def schedule(self, agent_id="agent-01", rec=None, prompt="scheduled work", **extra):
        body = {"recurrence": rec or {"type": "daily", "time": "09:00"}}
        body.update(extra)
        return self.h.save_task(agent_id, title="Scheduled", prompt=prompt, execution_mode="repeatable", schedule=body)

    def set_next(self, when):
        self.h.app.db.execute("UPDATE schedules SET next_run_at = ?", (timeutil.iso(when),))

    def runs(self, agent_id="agent-01"):
        return self.h.app.db.all("SELECT * FROM task_runs WHERE agent_id = ? ORDER BY rowid", (agent_id,))

    def test_default_time_zone_and_utc_storage(self):
        task = self.schedule()
        sched = task["schedule"]
        self.assertEqual(sched["timezone"], "Asia/Manila")
        self.assertTrue(sched["next_run_at"].endswith("Z"))
        self.assertEqual(timeutil.parse(sched["next_run_at"]).hour, 1, "09:00 Manila is stored as 01:00 UTC")
        self.assertEqual(self.h.runtime("agent-01")["status"], "scheduled")
        self.assertEqual(self.h.app.execution.summary()["next_scheduled"]["agent_id"], "agent-01")

    def test_nothing_runs_before_it_is_due(self):
        self.schedule()
        actions = self.sched.tick(timeutil.now())
        self.assertEqual(actions, [])
        self.assertEqual(self.runs(), [])
        self.assertEqual(self.h.app.adapter.inference_requests, 0)

    def test_due_occurrence_runs_once_even_if_ticked_repeatedly(self):
        self.schedule()
        due = timeutil.now() - dt.timedelta(seconds=5)
        self.set_next(due)
        first = self.sched.tick(timeutil.now())
        self.assertEqual([a["action"] for a in first], ["triggered"])
        occurrence = first[0]["occurrence_id"]
        self.assertTrue(occurrence.endswith("@" + timeutil.iso(due)))
        # The same occurrence can never start a second run, even if the schedule is rewound (e.g. a crash
        # between starting the run and saving the next time).
        self.set_next(due)
        again = self.sched.tick(timeutil.now())
        self.assertEqual([a["action"] for a in again], ["duplicate"])
        runs = self.runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["trigger_type"], "schedule")
        self.assertEqual(runs[0]["occurrence_id"], occurrence)
        self.assertEqual(self.h.wait_run(runs[0]["id"])["status"], "completed")
        sched = self.h.app.tasks.get_active("agent-01")["schedule"]
        self.assertGreater(timeutil.parse(sched["next_run_at"]), timeutil.now(), "the next occurrence is in the future")
        self.assertEqual(sched["last_occurrence_id"], occurrence)
        types = [e["type"] for e in self.h.app.bus.since(0)]
        self.assertEqual(types.count("schedule.triggered"), 1)

    def test_missed_occurrence_is_skipped_by_default(self):
        self.schedule()
        self.set_next(timeutil.now() - dt.timedelta(hours=3))
        actions = self.sched.tick(timeutil.now())
        self.assertEqual([a["action"] for a in actions], ["skipped_missed"])
        self.assertEqual(self.runs(), [])
        sched = self.h.app.tasks.get_active("agent-01")["schedule"]
        self.assertGreater(timeutil.parse(sched["next_run_at"]), timeutil.now())
        self.assertTrue(any("missed" in (e["log"] or "").lower() for e in self.h.app.bus.log_entries()))

    def test_missed_occurrence_runs_once_with_catch_up(self):
        self.schedule(rec={"type": "hourly", "minute": 0}, missed_execution_policy="catch_up")
        self.set_next(timeutil.now() - dt.timedelta(hours=5))
        actions = self.sched.tick(timeutil.now())
        self.assertEqual([a["action"] for a in actions], ["triggered"])
        self.assertEqual(len(self.runs()), 1, "five missed hours must produce one catch-up run, not five")
        self.h.wait_run(self.runs()[0]["id"])
        self.assertEqual(self.sched.tick(timeutil.now()), [])

    def test_overlap_is_skipped_by_default(self):
        self.schedule(prompt="[slow] long scheduled work")
        self.set_next(timeutil.now() - dt.timedelta(seconds=5))
        self.assertEqual([a["action"] for a in self.sched.tick(timeutil.now())], ["triggered"])
        run_id = self.runs()[0]["id"]
        self.h.wait(lambda: self.h.run_status(run_id) == "running", message="scheduled run")
        self.set_next(timeutil.now() - dt.timedelta(seconds=2))
        self.assertEqual([a["action"] for a in self.sched.tick(timeutil.now())], ["skipped_overlap"])
        self.assertEqual(len(self.runs()), 1)
        self.h.post("/api/agents/agent-01/interrupt")
        self.h.wait_run(run_id)

    def test_disabled_schedule_and_disabled_task_do_not_run(self):
        task = self.schedule()
        status, res = self.h.patch("/api/schedules/%s" % task["schedule"]["id"], {"enabled": False})
        self.assertEqual(status, 200, res)
        self.set_next(timeutil.now() - dt.timedelta(seconds=5))
        self.assertEqual(self.sched.tick(timeutil.now()), [])
        self.h.patch("/api/schedules/%s" % task["schedule"]["id"], {"enabled": True})
        self.h.save_task("agent-01", title="Scheduled", prompt="scheduled work", execution_mode="repeatable", enabled=False)
        self.set_next(timeutil.now() - dt.timedelta(seconds=5))
        self.assertEqual([a["action"] for a in self.sched.tick(timeutil.now())], ["skipped_disabled"])
        self.assertEqual(self.runs(), [])

    def test_one_time_schedule_runs_once_and_stops(self):
        when = (timeutil.now() + dt.timedelta(days=1)).astimezone(timeutil.get_tz("Asia/Manila")).strftime("%Y-%m-%dT%H:%M")
        self.h.save_task("agent-01", title="Once", prompt="one time", schedule={"recurrence": {"type": "once", "run_at": when}})
        self.set_next(timeutil.now() - dt.timedelta(seconds=5))
        self.assertEqual([a["action"] for a in self.sched.tick(timeutil.now())], ["triggered"])
        self.h.wait_run(self.runs()[0]["id"])
        sched = self.h.app.tasks.get_active("agent-01")["schedule"]
        self.assertIsNone(sched["next_run_at"])
        self.assertEqual(self.sched.tick(timeutil.now() + dt.timedelta(days=30)), [])
        self.assertEqual(len(self.runs()), 1)

    def test_scheduled_run_waits_for_codex_instead_of_failing(self):
        self.schedule()
        self.h.app.settings.set("auto_connect", False)
        self.h.post("/api/codex/disconnect", {"confirm": True})
        self.set_next(timeutil.now() - dt.timedelta(seconds=5))
        self.assertEqual([a["action"] for a in self.sched.tick(timeutil.now())], ["triggered"])
        run_id = self.runs()[0]["id"]
        self.h.wait(lambda: "Waiting for Codex" in (self.h.app.execution.get(run_id)["status_detail"] or ""),
                    message="honest waiting state")
        self.assertEqual(self.h.run_status(run_id), "queued")
        self.assertEqual(self.h.app.adapter.inference_requests, 0)
        self.h.post("/api/codex/connect")
        self.assertEqual(self.h.wait_run(run_id)["status"], "completed")

    def test_schedule_api_validation(self):
        status, res = self.h.post("/api/agents/agent-02/tasks", {
            "title": "Bad", "prompt": "x", "schedule": {"recurrence": {"type": "daily", "time": "99:99"}}})
        self.assertEqual(status, 400)
        status, res = self.h.post("/api/agents/agent-02/tasks", {
            "title": "Bad", "prompt": "x", "schedule": {"recurrence": {"type": "daily", "time": "09:00"}, "timezone": "Nowhere/None"}})
        self.assertEqual(status, 400)
        status, res = self.h.get("/api/schedules")
        self.assertEqual(res["schedules"], [])


if __name__ == "__main__":
    unittest.main()
