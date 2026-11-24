"""UTC timestamps, time zones, and recurrence calculations.

Storage is always UTC. Schedules are entered and displayed in a named time zone (default Asia/Manila).
This Windows machine has no tz database, so zones without one fall back to a built-in table of
fixed-offset zones (zones that do not observe daylight saving time).
"""
import calendar
import datetime as _dt

UTC = _dt.timezone.utc
DEFAULT_TZ = "Asia/Manila"

# Zones with a constant offset all year. Used only when the system tz database is unavailable.
_FIXED = {
    "UTC": 0, "Etc/UTC": 0,
    "Asia/Manila": 8 * 60, "Asia/Singapore": 8 * 60, "Asia/Hong_Kong": 8 * 60, "Asia/Shanghai": 8 * 60,
    "Asia/Taipei": 8 * 60, "Asia/Kuala_Lumpur": 8 * 60, "Australia/Perth": 8 * 60,
    "Asia/Tokyo": 9 * 60, "Asia/Seoul": 9 * 60,
    "Asia/Bangkok": 7 * 60, "Asia/Jakarta": 7 * 60, "Asia/Ho_Chi_Minh": 7 * 60,
    "Asia/Kolkata": 5 * 60 + 30, "Asia/Dubai": 4 * 60,
}


def now():
    return _dt.datetime.now(UTC).replace(microsecond=0)


def iso(dt=None):
    dt = dt or now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(text):
    """Parse a stored UTC timestamp. Returns an aware datetime or None."""
    if not text:
        return None
    try:
        s = str(text).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def get_tz(name):
    """Return a tzinfo for name. Raises ValueError if the zone cannot be resolved on this computer."""
    name = (name or DEFAULT_TZ).strip()
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(name)
    except Exception:
        pass
    if name in _FIXED:
        return _dt.timezone(_dt.timedelta(minutes=_FIXED[name]), name)
    raise ValueError("The time zone '%s' is not available on this computer." % name)


def tz_available(name):
    try:
        get_tz(name)
        return True
    except ValueError:
        return False


def available_zones():
    try:
        import zoneinfo
        zones = zoneinfo.available_timezones()
        if zones:
            return sorted(zones)
    except Exception:
        pass
    return sorted(_FIXED)


def local_to_utc(naive, tzname):
    return naive.replace(tzinfo=get_tz(tzname)).astimezone(UTC)


def parse_local(text):
    """Parse 'YYYY-MM-DDTHH:MM' (or with seconds / a space) as a naive local datetime."""
    s = str(text or "").strip().replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError("Use the date and time format YYYY-MM-DD HH:MM.")


def parse_date(text):
    try:
        return _dt.datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Use the date format YYYY-MM-DD.")


def parse_hhmm(text):
    try:
        hh, mm = str(text).strip().split(":")[:2]
        hh, mm = int(hh), int(mm)
    except (ValueError, AttributeError):
        raise ValueError("Use the time format HH:MM.")
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("Use a time between 00:00 and 23:59.")
    return hh, mm


# ---------------------------------------------------------------- cron
def _cron_field(text, lo, hi, names=None):
    values = set()
    for part in str(text).split(","):
        part = part.strip().lower()
        if not part:
            raise ValueError("Empty cron field.")
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step < 1:
                raise ValueError("Cron step must be 1 or more.")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = _cron_value(a, names), _cron_value(b, names)
        else:
            start = _cron_value(part, names)
            end = hi if step > 1 else start
        if start < lo or end > hi or start > end:
            raise ValueError("Cron value out of range (%d-%d)." % (lo, hi))
        values.update(range(start, end + 1, step))
    return values


def _cron_value(text, names):
    text = text.strip().lower()
    if names and text in names:
        return names[text]
    return int(text)


_DOW = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
_MON = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def parse_cron(expr):
    """Parse a five-field cron expression (minute hour day-of-month month day-of-week)."""
    fields = str(expr or "").split()
    if len(fields) != 5:
        raise ValueError("A cron schedule needs five fields: minute hour day month weekday.")
    try:
        minute = _cron_field(fields[0], 0, 59)
        hour = _cron_field(fields[1], 0, 23)
        dom = _cron_field(fields[2], 1, 31)
        month = _cron_field(fields[3], 1, 12, _MON)
        dow = _cron_field(fields[4].replace("7", "0") if fields[4].strip() == "7" else fields[4], 0, 7, _DOW)
    except ValueError as exc:
        raise ValueError("Invalid cron schedule: %s" % exc)
    if 7 in dow:
        dow.discard(7)
        dow.add(0)
    return {"minute": minute, "hour": hour, "dom": dom, "month": month, "dow": dow,
            "dom_any": fields[2].strip() == "*", "dow_any": fields[4].strip() == "*"}


def _cron_day_ok(c, day):
    cron_dow = (day.weekday() + 1) % 7  # Python Monday=0 -> cron Sunday=0
    dom_ok = day.day in c["dom"]
    dow_ok = cron_dow in c["dow"]
    if c["dom_any"] and c["dow_any"]:
        return True
    if c["dom_any"]:
        return dow_ok
    if c["dow_any"]:
        return dom_ok
    return dom_ok or dow_ok  # standard cron: either matches when both are restricted


# ---------------------------------------------------------------- recurrence
TYPES = ("once", "hourly", "daily", "weekly", "monthly", "cron")


def validate_recurrence(rec, tzname):
    """Return a cleaned recurrence dict. Raises ValueError with a user-readable message."""
    if not isinstance(rec, dict):
        raise ValueError("Schedule details are missing.")
    get_tz(tzname)
    kind = rec.get("type")
    if kind not in TYPES:
        raise ValueError("Choose how often the assignment should run.")
    out = {"type": kind}
    if kind == "once":
        out["run_at"] = parse_local(rec.get("run_at")).strftime("%Y-%m-%dT%H:%M")
    elif kind == "hourly":
        minute = int(rec.get("minute", 0))
        if not 0 <= minute <= 59:
            raise ValueError("Minute must be between 0 and 59.")
        out["minute"] = minute
    elif kind in ("daily", "weekly", "monthly"):
        hh, mm = parse_hhmm(rec.get("time"))
        out["time"] = "%02d:%02d" % (hh, mm)
        if kind == "weekly":
            days = sorted({int(d) for d in (rec.get("weekdays") or [])})
            if not days or any(d < 0 or d > 6 for d in days):
                raise ValueError("Choose at least one weekday.")
            out["weekdays"] = days
        if kind == "monthly":
            day = int(rec.get("day", 1))
            if not 1 <= day <= 31:
                raise ValueError("Day of month must be between 1 and 31.")
            out["day"] = day
    elif kind == "cron":
        parse_cron(rec.get("cron"))
        out["cron"] = " ".join(str(rec.get("cron")).split())
    for key in ("start_date", "end_date"):
        if rec.get(key):
            out[key] = parse_date(rec[key]).isoformat()
    if out.get("start_date") and out.get("end_date") and out["end_date"] < out["start_date"]:
        raise ValueError("The end date is before the start date.")
    return out


def next_occurrence(rec, tzname, after=None):
    """First occurrence strictly after `after` (aware UTC). Returns aware UTC datetime or None."""
    tz = get_tz(tzname)
    after = (after or now()).astimezone(UTC)
    local_after = after.astimezone(tz).replace(tzinfo=None)
    start = parse_date(rec["start_date"]) if rec.get("start_date") else None
    end = parse_date(rec["end_date"]) if rec.get("end_date") else None
    kind = rec.get("type")

    def finish(naive):
        if naive is None:
            return None
        if end and naive.date() > end:
            return None
        return naive.replace(tzinfo=tz).astimezone(UTC)

    floor = local_after
    if start:
        start_dt = _dt.datetime.combine(start, _dt.time(0, 0)) - _dt.timedelta(seconds=1)
        if start_dt > floor:
            floor = start_dt

    if kind == "once":
        run_at = parse_local(rec["run_at"])
        return finish(run_at) if run_at > local_after else None

    if kind == "hourly":
        cand = floor.replace(minute=int(rec.get("minute", 0)), second=0, microsecond=0)
        while cand <= floor:
            cand += _dt.timedelta(hours=1)
        return finish(cand)

    if kind in ("daily", "weekly", "monthly"):
        hh, mm = parse_hhmm(rec["time"])
        day = floor.date()
        for _ in range(800):
            if kind == "monthly":
                last = calendar.monthrange(day.year, day.month)[1]
                ok = day.day == min(int(rec.get("day", 1)), last)
            elif kind == "weekly":
                ok = day.weekday() in set(rec.get("weekdays") or [])
            else:
                ok = True
            if ok:
                cand = _dt.datetime.combine(day, _dt.time(hh, mm))
                if cand > floor:
                    return finish(cand)
            day += _dt.timedelta(days=1)
            if end and day > end:
                return None
        return None

    if kind == "cron":
        c = parse_cron(rec["cron"])
        cand = floor.replace(second=0, microsecond=0) + _dt.timedelta(minutes=1)
        hours = sorted(c["hour"])
        minutes = sorted(c["minute"])
        day = cand.date()
        for _ in range(366 * 5):
            if end and day > end:
                return None
            if day.month in c["month"] and _cron_day_ok(c, day):
                for h in hours:
                    for m in minutes:
                        t = _dt.datetime.combine(day, _dt.time(h, m))
                        if t >= cand:
                            return finish(t)
            day += _dt.timedelta(days=1)
        return None
    return None


def describe(rec, tzname):
    """Short human description of a recurrence."""
    kind = rec.get("type")
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if kind == "once":
        return "Once on %s (%s)" % (rec.get("run_at", "").replace("T", " "), tzname)
    if kind == "hourly":
        return "Every hour at :%02d" % int(rec.get("minute", 0))
    if kind == "daily":
        return "Every day at %s (%s)" % (rec.get("time"), tzname)
    if kind == "weekly":
        return "Every %s at %s (%s)" % (", ".join(names[d] for d in rec.get("weekdays", [])), rec.get("time"), tzname)
    if kind == "monthly":
        return "Monthly on day %s at %s (%s)" % (rec.get("day"), rec.get("time"), tzname)
    if kind == "cron":
        return "Cron %s (%s)" % (rec.get("cron"), tzname)
    return "Manual"
