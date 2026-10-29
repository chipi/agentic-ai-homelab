"""Tests for the Hetzner status poller: parsing, classification, new/updated detection."""
import poll

FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Hetzner Online GmbH - Status-Webseite</title>
  <entry>
    <id>https://status.hetzner.com/aaa/0</id>
    <updated>2026-11-01T08:00:00+00:00</updated>
    <link href="https://status.hetzner.com/incident/aaa" />
    <title>Maintenance UPS systems in FSN1-DC22</title>
    <category term="FSN1-DC22"/>
    <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">
      <p>Start: 2026-11-02T08:00:00+00:00</p><p>End: 2026-11-02T12:00:00+00:00</p>
      <p>We will maintain the UPS.</p></div></content>
  </entry>
  <entry>
    <id>https://status.hetzner.com/bbb/0</id>
    <updated>2026-10-15T10:21:52+00:00</updated>
    <link href="https://status.hetzner.com/incident/bbb" />
    <title>Urgent maintenance on all core routers</title>
    <category term="Network"/>
    <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>Start: 2026-10-15T10:00:00+00:00</p><p>Routers.</p></div></content>
  </entry>
  <entry>
    <id>https://status.hetzner.com/ccc/1</id>
    <updated>2026-10-28T17:08:08+00:00</updated>
    <link href="https://status.hetzner.com/incident/ccc" />
    <title>Disk failures in HEL1-DC1</title>
    <category term="HEL1-DC1"/>
    <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>Start: 2026-10-28T17:00:00+00:00</p></div></content>
  </entry>
</feed>"""


def test_parse_fields():
    b = poll.parse(FEED)
    assert [x["title"] for x in b] == ["Maintenance UPS systems in FSN1-DC22", "Urgent maintenance on all core routers",
                                       "Disk failures in HEL1-DC1"]
    ups = b[0]
    assert (ups["category"], ups["start"], ups["end"]) == ("FSN1-DC22", "2026-11-02T08:00:00+00:00", "2026-11-02T12:00:00+00:00")
    assert ups["link"] == "https://status.hetzner.com/incident/aaa"
    assert ups["summary"].startswith("We will maintain")


def test_classification():
    b = {x["title"]: x for x in poll.parse(FEED)}
    # the Storage Box's city, datacenter unknown -> nearby, not direct
    assert (b["Maintenance UPS systems in FSN1-DC22"]["relevance"], b["Maintenance UPS systems in FSN1-DC22"]["location"],
            b["Maintenance UPS systems in FSN1-DC22"]["kind"]) == ("nearby", "FSN1-DC22", "maintenance")
    assert b["Urgent maintenance on all core routers"]["relevance"] == "service"
    assert (b["Disk failures in HEL1-DC1"]["relevance"], b["Disk failures in HEL1-DC1"]["kind"]) == ("other", "incident")


def test_correlation_levels():
    c = lambda cats, title="x", text="": poll.classify(cats, title, text)[0]
    assert c(["NBG1-DC3"]) == "direct"            # our server's exact datacenter
    assert c(["NBG1"]) == "direct"                # whole-location bulletin for the server's location
    assert c(["General"], "x", "affects hosts in NBG1-DC3 only") == "direct"   # text names our DC
    assert c(["NBG1-DC5"]) == "nearby"            # same city, other datacenter
    assert c(["FSN1"]) == "nearby"                # the Storage Box's city
    assert c(["NBG10-DC1"]) == "other"            # NBG10 is not NBG1
    assert c(["General"], "x", "NBG1-DC30 maintenance") == "other"   # DC30 is not DC3
    assert c(["Cloud Server"]) == "service"


def _b(start, end="", relevance="direct"):
    return {"relevance": relevance, "start": start, "end": end, "kind": "maintenance", "category": "NBG1-DC3",
            "title": 'UPS "work"', "link": "https://status.hetzner.com/incident/x"}


def test_phase_and_active():
    from datetime import datetime, timezone
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    assert poll.phase(_b("2026-11-02T08:00:00+00:00"), now) == "upcoming"       # within 7 days
    assert poll.phase(_b("2026-11-20T08:00:00+00:00"), now) is None             # too far ahead
    assert poll.phase(_b("2026-10-29T10:00:00+00:00", "2026-10-29T14:00:00+00:00"), now) == "ongoing"
    assert poll.phase(_b("2026-10-29T08:00:00+00:00", "2026-10-29T10:00:00+00:00"), now) is None   # ended
    assert poll.phase(_b("2026-10-27T13:00:00+00:00"), now) == "ongoing"        # no end, < 72 h old
    assert poll.phase(_b("2026-10-20T13:00:00+00:00"), now) is None             # no end, too old
    assert poll.phase(_b(""), now) is None
    # service only while ongoing; other never
    rows = [_b("2026-11-02T08:00:00+00:00", relevance="service"), _b("2026-10-29T11:00:00+00:00", relevance="service"),
            _b("2026-11-02T08:00:00+00:00", relevance="nearby"), _b("2026-10-29T11:00:00+00:00", relevance="other")]
    assert [(a["relevance"], a["phase"]) for a in poll.active(rows, now)] == [("service", "ongoing"), ("nearby", "upcoming")]


def test_active_metric_line_escapes_labels():
    from datetime import datetime, timezone
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    b = dict(_b("2026-11-02T08:00:00+00:00"), entry_id="i", updated="u", location="NBG1-DC3", summary="s")
    lines = poll.metric_lines(True, [b], now)
    act = [l for l in lines if l.startswith("hetzner_status_active")]
    assert act == ['hetzner_status_active{relevance="direct",phase="upcoming",kind="maintenance",category="NBG1-DC3",'
                   'title="UPS \\"work\\"",start="2026-11-02T08:00:00+00:00",end="",link="https://status.hetzner.com/incident/x"} 1']
    assert 'hetzner_status_feed_entries{relevance="direct"} 1' in lines


def test_first_run_is_backfill_then_only_new_or_updated():
    state = {}
    events, _ = poll.poll_once(state, fetch=lambda: FEED)
    assert len(events) == 3 and all(e["backfill"] == "true" for e in events)
    events, _ = poll.poll_once(state, fetch=lambda: FEED)
    assert events == []
    updated = FEED.replace("2026-10-15T10:21:52+00:00", "2026-10-16T09:00:00+00:00")
    events, _ = poll.poll_once(state, fetch=lambda: updated)
    assert [(e["title"], e["backfill"]) for e in events] == [("Urgent maintenance on all core routers", "false")]
    new = updated.replace("<entry>", """<entry>
    <id>https://status.hetzner.com/ddd/0</id><updated>2026-11-03T00:00:00+00:00</updated>
    <link href="https://status.hetzner.com/incident/ddd" /><title>Outage in NBG1-DC3</title><category term="NBG1-DC3"/>
  </entry>
  <entry>""", 1)
    events, _ = poll.poll_once(state, fetch=lambda: new)
    assert [(e["title"], e["relevance"], e["backfill"]) for e in events] == [("Outage in NBG1-DC3", "direct", "false")]


def test_state_drops_ids_no_longer_in_feed():
    state = {}
    poll.poll_once(state, fetch=lambda: FEED)
    only_one = FEED.split("<entry>")[0] + "<entry>" + FEED.split("<entry>")[1].split("</entry>")[0] + "</entry></feed>"
    poll.poll_once(state, fetch=lambda: only_one)
    assert list(state["seen"]) == ["https://status.hetzner.com/aaa/0"]


def test_event_shape():
    e = poll.to_event(poll.parse(FEED)[0], backfill=False)
    assert e["_msg"] == "hetzner maintenance [FSN1-DC22] Maintenance UPS systems in FSN1-DC22"
    assert (e["app"], e["environment"], e["instance"], e["backfill"]) == ("hetzner-status", "operations", "homelab", "false")
    from datetime import datetime, timezone
    seen_at = datetime.fromisoformat(e["_time"])
    assert e["updated"] == "2026-11-01T08:00:00+00:00"
    assert abs((datetime.now(timezone.utc) - seen_at).total_seconds()) < 60   # observation time, not `updated`
