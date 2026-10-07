from datetime import datetime
from zoneinfo import ZoneInfo

from jarvis.cogs.reminders import next_occurrence

TZ = ZoneInfo("Europe/Paris")


def test_daily_skips_missed_days():
    due = datetime(2026, 10, 1, 9, tzinfo=TZ)
    now = datetime(2026, 10, 7, 14, tzinfo=TZ)
    assert next_occurrence(due, "quotidien", now) == datetime(2026, 10, 8, 9, tzinfo=TZ)


def test_daily_keeps_wall_clock_across_dst():
    # Passage à l'heure d'hiver le 25 octobre 2026
    due = datetime(2026, 10, 24, 9, tzinfo=TZ)
    now = datetime(2026, 10, 24, 9, 0, 1, tzinfo=TZ)
    result = next_occurrence(due, "quotidien", now)
    assert (result.hour, result.day) == (9, 25)
    assert result.utcoffset() != due.utcoffset()


def test_weekly():
    due = datetime(2026, 10, 7, 18, tzinfo=TZ)
    assert next_occurrence(due, "hebdo", due) == datetime(2026, 10, 14, 18, tzinfo=TZ)


def test_monthly_end_of_month():
    due = datetime(2026, 1, 31, 9, tzinfo=TZ)
    assert next_occurrence(due, "mensuel", due) == datetime(2026, 2, 28, 9, tzinfo=TZ)
