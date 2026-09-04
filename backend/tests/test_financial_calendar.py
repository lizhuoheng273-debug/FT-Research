from datetime import datetime, timedelta, timezone
import json
import pytest

import financial_calendar as cal

NOW = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
FED = '''<div id="article"><div class="row-title"><h4>September 2026</h4></div>
<div class="panel-body"><div class="row"><div class="col-xs-2"><p>8:30 a.m.</p></div><div class="col-xs-7"><p>Speech - Governor Christopher J. Waller</p><p class="calendar__title">Economic Outlook</p></div><div class="col-xs-3"><p>3</p></div></div></div>
<div class="panel-body"><div class="row"><div class="col-xs-2"><p>2:00 p.m.</p></div><div class="col-xs-7"><p>Beige Book</p></div><div class="col-xs-3"><p>2</p></div></div></div></div>'''
NVIDIA = '''<rss><channel><item><title>9/10/2026 : Goldman Sachs Technology Conference</title><link>https://investor.nvidia.com/events/2026/conference</link><pubDate>Thu, 27 Aug 2026 17:05:20 -0400</pubDate></item></channel></rss>'''
ICS = '''BEGIN:VCALENDAR
BEGIN:VEVENT
UID:jobs
DTSTART;TZID=America/New_York:20260904T083000
SUMMARY:Employment Situation
URL:https://www.bls.gov/news.release/empsit.htm
END:VEVENT
BEGIN:VEVENT
UID:cancelled
DTSTART:20260905T120000Z
SUMMARY:Consumer Price Index
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR'''


def test_fed_calendar_uses_event_date_and_daylight_saving_offset():
    events = cal.parse_fed(FED, 2026, 9, "https://www.federalreserve.gov/newsevents/2026-september.htm")
    assert events[0]["startsAt"] == "2026-09-03T20:30:00+08:00"
    assert events[0]["precision"] == "time"
    assert events[1]["startsAt"] == "2026-09-03T02:00:00+08:00"


def test_fomc_minutes_are_not_a_new_interest_rate_decision():
    rows=cal.parse_fed(FED.replace("Beige Book","FOMC Minutes"),2026,9,cal.FED_HOME)
    assert rows[1]["title"] == "美联储 FOMC 会议纪要"


def test_date_only_event_remains_until_its_local_day_ends(tmp_path):
    clock=[datetime(2026,9,10,16,1,tzinfo=timezone.utc)]
    svc=cal.FinancialCalendar(tmp_path,now_fn=lambda:clock[0],fetchers={"nvidia":lambda:cal.parse_nvidia(NVIDIA)})
    assert len(svc.refresh()["items"]) == 1
    clock[0]=datetime(2026,9,11,7,1,tzinfo=timezone.utc)
    assert svc.overview()["items"] == []


def test_truncated_ics_does_not_overwrite_successful_cache(tmp_path):
    clock=[NOW]
    future_ics = ICS.replace("20260904T083000", "20260911T083000")
    svc=cal.FinancialCalendar(tmp_path,now_fn=lambda:clock[0],fetchers={"bls":lambda:cal.parse_bls(future_ics)})
    assert len(svc.refresh()["items"]) == 1
    clock[0]=datetime(2026,9,4,20,0,tzinfo=timezone.utc)
    svc.fetchers={"bls":lambda:cal.parse_bls('BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Consumer Price Index')}
    result=svc.refresh()
    assert len(result["items"]) == 1
    assert result["stale"] is True


def test_nvidia_rss_pubdate_is_not_the_future_event_date():
    row = cal.parse_nvidia(NVIDIA)[0]
    assert row["date"] == "2026-09-10"
    assert row["startsAt"] is None
    assert row["precision"] == "date"
    assert row["originalUrl"] == "https://investor.nvidia.com/events/2026/conference"


def test_ics_unfolds_dates_and_excludes_cancelled_entries():
    rows = cal.parse_bls(ICS)
    assert len(rows) == 1
    assert rows[0]["startsAt"] == "2026-09-04T20:30:00+08:00"
    assert "非农" in rows[0]["title"]


def test_bea_table_and_ecb_date_only_calendar():
    bea = '<table id="release-schedule-table"><thead><th>Year 2026</th></thead><tbody><tr><td class="scheduled-date"><div class="release-date">September 3</div><small>8:30 AM</small></td><td class="release-title">U.S. International Trade in Goods and Services, July 2026</td></tr></tbody></table>'
    assert cal.parse_bea(bea)[0]["startsAt"] == "2026-09-03T20:30:00+08:00"
    ecb = '<dl><dt>09/09/2026</dt><dd>Governing Council: monetary policy meeting (Day 1)</dd><dt>10/09/2026</dt><dd>Press conference following the Governing Council meeting</dd></dl>'
    rows = cal.parse_ecb(ecb)
    assert [r["date"] for r in rows] == ["2026-09-09", "2026-09-10"]
    assert rows[1]["startsAt"] is None


def test_window_is_future_fourteen_days_and_never_keeps_past_from_cache(tmp_path):
    clock = [NOW]
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: clock[0], fetchers={"fed": lambda: cal.parse_fed(FED, 2026, 9, cal.FED_HOME)})
    result = svc.refresh()
    assert len(result["items"]) == 2
    clock[0] += timedelta(days=3)
    assert svc.overview()["items"] == []


def test_failed_parse_preserves_success_and_marks_stale_after_restart(tmp_path):
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: NOW, fetchers={"fed": lambda: cal.parse_fed(FED, 2026, 9, cal.FED_HOME)})
    svc.refresh()
    def bad():
        raise ValueError("changed markup")
    svc.fetchers = {"fed": bad}
    result = svc.refresh()
    assert len(result["items"]) == 2
    assert result["stale"] is True
    assert all(r["stale"] for r in result["items"])
    again = cal.FinancialCalendar(tmp_path, now_fn=lambda: NOW, fetchers={"fed": bad}).overview()
    assert again["items"] == result["items"]


def test_successful_empty_source_removes_cancelled_or_rescheduled_events(tmp_path):
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: NOW, fetchers={"nvidia": lambda: cal.parse_nvidia(NVIDIA)})
    assert len(svc.refresh()["items"]) == 1
    svc.fetchers = {"nvidia": lambda: []}
    assert svc.refresh()["items"] == []


@pytest.mark.parametrize("parser", [lambda: cal.parse_fed('<html>blocked</html>', 2026, 9, cal.FED_HOME), lambda: cal.parse_bea('<html>blocked</html>'), lambda: cal.parse_ecb('<html>blocked</html>'), lambda: cal.parse_nvidia('<html>blocked</html>'), lambda: cal.parse_bls('<html>blocked</html>')])
def test_unrecognized_markup_is_not_a_successful_empty_calendar(parser):
    with pytest.raises(ValueError):
        parser()


def test_date_only_and_exact_fourteen_day_boundary(tmp_path):
    rows = [cal.calendar_event("a", "事件", "会议", "2026-09-16", None, "UTC", "https://example.test/a"),
            cal.calendar_event("b", "事件", "会议", "2026-09-17", None, "UTC", "https://example.test/b"),
            cal.calendar_event("c", "已结束", "会议", "2026-09-01", None, "UTC", "https://example.test/c")]
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: NOW, fetchers={"x": lambda: rows})
    assert [r["date"] for r in svc.refresh()["items"]] == ["2026-09-16"]


def test_calendar_endpoint_only_reads_cache(monkeypatch, tmp_path):
    import app
    from fastapi.testclient import TestClient
    def forbidden():
        pytest.fail("GET must never fetch upstream")
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: NOW, fetchers={"fed": forbidden})
    monkeypatch.setattr(app.financial_news_service, "calendar", svc, raising=False)
    response = TestClient(app.app).get("/api/finance/news/calendar")
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    assert response.json()["data"]["partial"] is True


def test_calendar_refresh_endpoint_fetches_once_then_applies_shared_cooldown(monkeypatch):
    import app
    from fastapi.testclient import TestClient

    calls = []
    clock = [100.0]
    refreshed = {"items": [{"id": "latest"}], "partial": False, "stale": False}
    monkeypatch.setattr(app.financial_news_service.calendar, "refresh", lambda **_kwargs: calls.append("refresh") or refreshed)
    monkeypatch.setattr(app.financial_news_service.calendar, "overview", lambda: refreshed)
    monkeypatch.setattr(app, "_calendar_refresh_clock", lambda: clock[0])
    monkeypatch.setattr(app, "_calendar_refresh_last_attempt", None)

    client = TestClient(app.app)
    first = client.post("/api/finance/news/calendar/refresh")
    second = client.post("/api/finance/news/calendar/refresh")

    assert first.status_code == 200
    assert first.json()["data"]["outcome"] == "updated"
    assert first.json()["data"]["calendar"]["items"][0]["id"] == "latest"
    assert second.status_code == 200
    assert second.json()["data"]["outcome"] == "cooldown"
    assert second.json()["data"]["retryAfter"] == 60
    assert calls == ["refresh"]


def test_manual_calendar_refresh_waits_for_an_active_scheduler_refresh(tmp_path):
    import threading
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: NOW, fetchers={"nvidia": lambda: []})
    finished = threading.Event()
    svc.lock.acquire()
    worker = threading.Thread(target=lambda: (svc.refresh(blocking=True), finished.set()))
    worker.start()
    assert not finished.wait(0.05)
    svc.lock.release()
    assert finished.wait(1)
    worker.join(1)


def test_bls_is_checked_once_per_official_week_while_other_sources_keep_refreshing(tmp_path):
    clock = [datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)]  # Friday 16:00 New York.
    calls = {"bls": 0, "fed": 0}
    def fetch_bls():
        calls["bls"] += 1
        return []
    def fetch_fed():
        calls["fed"] += 1
        return []
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: clock[0], fetchers={"bls": fetch_bls, "fed": fetch_fed})
    svc.refresh()
    clock[0] += timedelta(hours=1)
    svc.refresh()
    assert calls == {"bls": 1, "fed": 2}
    clock[0] += timedelta(days=7)
    svc.refresh()
    assert calls == {"bls": 2, "fed": 3}


def test_bls_waits_until_friday_1540_new_york_after_a_prior_week_attempt(tmp_path):
    clock = [datetime(2026, 9, 11, 19, 39, tzinfo=timezone.utc)]  # Friday 15:39 EDT.
    calls = []
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: clock[0], fetchers={"bls": lambda: calls.append(clock[0]) or []})
    svc.path.write_text(json.dumps({"sources": {"bls": {"ok": False, "items": [], "attemptedAt": "2026-09-04T19:40:00+00:00"}}}), encoding="utf-8")
    svc.refresh()
    assert calls == []
    clock[0] += timedelta(minutes=1)
    svc.refresh()
    assert calls == [clock[0]]


def test_successful_bls_cache_stays_fresh_for_eight_days(tmp_path):
    clock = [datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)]
    row = cal.calendar_event("jobs", "美国非农就业报告", "经济数据", "2026-09-13", "08:30:00", "America/New_York", cal.BLS_URL)
    svc = cal.FinancialCalendar(tmp_path, now_fn=lambda: clock[0], fetchers={"bls": lambda: [row]})
    assert svc.refresh()["stale"] is False
    clock[0] += timedelta(days=7, hours=23)
    assert svc.overview()["stale"] is False
    clock[0] += timedelta(hours=2)
    assert svc.overview()["stale"] is True
