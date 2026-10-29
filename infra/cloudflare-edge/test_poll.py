"""Tests for the Cloudflare edge poller: status classes, aggregation, status-page correlation."""
import os
from datetime import datetime, timezone

import pytest

import poll

OURS = {"services": {"CDN/Cache", "Authoritative DNS"}, "pops": {"FRA"}, "pop_share_min": 0.05}
NOW = datetime(2026, 10, 29, 16, 0, tzinfo=timezone.utc)


def g(host, status, n):
    return {"count": n, "dimensions": {"clientRequestHTTPHost": host, "edgeResponseStatus": status}}


def test_status_class():
    assert [poll.status_class(s) for s in (200, 304, 404, 499, 500, 502, 519, 520, 522, 525, 526, 530)] == [
        "2xx", "3xx", "4xx", "client_closed", "5xx_server", "5xx_server", "5xx_server",
        "5xx_unreachable", "5xx_unreachable", "5xx_unreachable", "5xx_unreachable", "5xx_unreachable"]


def test_pop_code():
    assert poll.pop_code("Frankfurt, Germany - (FRA)") == "FRA"
    assert poll.pop_code("CDN/Cache") is None


def test_edge_lines_aggregates_per_host_and_class():
    edge = {"example.app": {
        "h1": [g("a.example.app", 200, 10), g("a.example.app", 204, 5), g("a.example.app", 522, 2), g("a.example.app", 520, 1)],
        "d1": [g("a.example.app", 200, 100), g("a.example.app", 499, 3)],
        "colo": [{"count": 90, "dimensions": {"coloCode": "CDG"}}, {"count": 10, "dimensions": {"coloCode": "FRA"}}],
        "fw": [{"action": "block", "source": "firewallManaged"}] * 4}}
    lines, share = poll.edge_lines(edge)
    assert 'cloudflare_edge_requests{zone="example.app",host="a.example.app",class="2xx",window="1h"} 15' in lines
    assert 'cloudflare_edge_requests{zone="example.app",host="a.example.app",class="5xx_unreachable",window="1h"} 3' in lines
    assert 'cloudflare_edge_5xx{zone="example.app",host="a.example.app",status="522",window="1h"} 2' in lines
    assert 'cloudflare_edge_requests{zone="example.app",host="a.example.app",class="client_closed",window="24h"} 3' in lines
    assert 'cloudflare_security_events{zone="example.app",action="block",source="firewallManaged"} 4' in lines
    assert 'cloudflare_edge_pop_share{colo="CDG"} 0.9000' in lines
    assert share == {"CDG": 0.9, "FRA": 0.1}
    assert poll.our_pops({"CDG": 0.9, "SIN": 0.01}, OURS) == {"CDG", "FRA"}


def summary(incidents=(), maint=(), comp_status=None):
    comp_status = comp_status or {}
    comps = [{"id": "gS", "name": "Cloudflare Sites and Services", "group": True},
             {"id": "gE", "name": "Europe", "group": True},
             {"id": "cdn", "name": "CDN/Cache", "group_id": "gS"},
             {"id": "d1", "name": "D1", "group_id": "gS"},
             {"id": "fra", "name": "Frankfurt, Germany - (FRA)", "group_id": "gE"},
             {"id": "cdg", "name": "Paris, France - (CDG)", "group_id": "gE"},
             {"id": "bcn", "name": "Barcelona, Spain - (BCN)", "group_id": "gE"}]
    for c in comps:
        c["status"] = comp_status.get(c["id"], "operational")
    return {"status": {"indicator": "major", "description": "Partial System Outage"}, "components": comps,
            "incidents": list(incidents), "scheduled_maintenances": list(maint)}


def test_only_our_components_are_published():
    s = summary(comp_status={"cdn": "degraded_performance", "d1": "major_outage", "bcn": "major_outage",
                             "cdg": "partial_outage"})
    lines = poll.status_lines(s, OURS, {"FRA", "CDG"}, NOW)
    comps = [l for l in lines if l.startswith("cloudflare_status_component")]
    assert comps == ['cloudflare_status_component{kind="service",name="CDN/Cache",status="degraded_performance"} 1',
                     'cloudflare_status_component{kind="pop",name="Paris, France - (CDG)",status="partial_outage"} 1']


def test_incident_relevance():
    inc = [{"name": "CDN errors", "impact": "major", "status": "investigating", "shortlink": "https://stspg.io/x",
            "components": [{"id": "cdn", "name": "CDN/Cache"}, {"id": "d1", "name": "D1"}]},
           {"name": "D1 errors", "impact": "minor", "status": "identified", "shortlink": "https://stspg.io/y",
            "components": [{"id": "d1", "name": "D1"}]}]
    lines = poll.status_lines(summary(incidents=inc), OURS, {"FRA"}, NOW)
    assert any('relevance="direct",name="CDN errors"' in l and 'components="CDN/Cache"' in l for l in lines)
    assert any('relevance="other",name="D1 errors"' in l for l in lines)


def test_maintenance_only_ours_and_soon():
    m = lambda name, cid, start, status="scheduled": {"name": name, "status": status, "scheduled_for": start,
                                                      "scheduled_until": "", "shortlink": "", "components": [{"id": cid}]}
    maint = [m("FRA soon", "fra", "2026-10-30T09:00:00.000Z"),
             m("FRA later", "fra", "2026-11-05T09:00:00.000Z"),
             m("FRA now", "fra", "2026-10-29T10:00:00.000Z", "in_progress"),
             m("BCN soon", "bcn", "2026-10-29T23:00:00.000Z")]
    lines = [l for l in poll.status_lines(summary(maint=maint), OURS, {"FRA"}, NOW) if "maintenance" in l]
    names = [l.split('name="')[1].split('"')[0] for l in lines]
    assert names == ["FRA soon", "FRA now"]


def test_label_values_are_escaped():
    assert poll._m("x", {"a": 'say "hi"\nnow'}, 1) == 'x{a="say \\"hi\\" now"} 1'


def test_token_file_must_be_private(tmp_path):
    p = tmp_path / "cf.env"
    p.write_text("CLOUDFLARE_API_TOKEN=abc\n")
    os.chmod(p, 0o644)
    with pytest.raises(SystemExit):
        poll.load_token(str(p))
    os.chmod(p, 0o600)
    assert poll.load_token(str(p)) == "abc"
