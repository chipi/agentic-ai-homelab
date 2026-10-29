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
    assert (b["Maintenance UPS systems in FSN1-DC22"]["affects"], b["Maintenance UPS systems in FSN1-DC22"]["location"],
            b["Maintenance UPS systems in FSN1-DC22"]["kind"]) == ("ours", "FSN1-DC22", "maintenance")
    assert b["Urgent maintenance on all core routers"]["affects"] == "service"
    assert (b["Disk failures in HEL1-DC1"]["affects"], b["Disk failures in HEL1-DC1"]["kind"]) == ("other", "incident")


def test_location_prefix_is_exact():
    # NBG10 is not NBG1: only the location itself or LOC-<dc> counts
    assert poll.classify(["NBG10-DC1"], "x")[0] == "other"
    assert poll.classify(["NBG1-DC3"], "x")[0] == "ours"
    assert poll.classify(["NBG1"], "x")[0] == "ours"


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
    assert [(e["title"], e["affects"], e["backfill"]) for e in events] == [("Outage in NBG1-DC3", "ours", "false")]


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
