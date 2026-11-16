"""python3 -m unittest test_resolve_stale (from infra/glitchtip): resolve-stale.py's listing and plan, no network."""
import datetime as dt
import importlib.util
import os
import unittest

_spec = importlib.util.spec_from_file_location(
    "resolve_stale", os.path.join(os.path.dirname(os.path.abspath(__file__)), "resolve-stale.py"))
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)

NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)


def issue(n, days_ago):
    return {"id": n, "lastSeen": (NOW - dt.timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")}


class FakeSession:
    """Projects and per-project issue pages; the org-wide issues listing is not served (it skipped issues)."""

    def __init__(self, projects):
        self.projects, self.paths = projects, []

    def call(self, method, path, body=None):
        self.paths.append(path)
        if path.startswith(f"/api/0/organizations/{rs.ORG}/projects/"):
            return [{"slug": s} for s in self.projects], {}
        for slug, pages in self.projects.items():
            if path.startswith(f"/api/0/projects/{rs.ORG}/{slug}/issues/"):
                k = int(path.split("cursor=")[1]) if "cursor=" in path else 0
                link = (f'<x?cursor={k + 1}>; rel="next"; results="true"' if k + 1 < len(pages)
                        else '<x>; rel="next"; results="false"')
                return pages[k], {"Link": link}
        raise AssertionError(path)


class ResolveStale(unittest.TestCase):
    def test_lists_project_by_project_and_follows_pages(self):
        s = FakeSession({"orrery": [[issue(1, 1)], [issue(2, 20)]], "podcast-pipeline-dev": [[issue(3, 32)]]})
        got = sorted((p, i["id"]) for p, i in rs.unresolved(s))
        self.assertEqual(got, [("orrery", 1), ("orrery", 2), ("podcast-pipeline-dev", 3)])
        self.assertFalse(any("/organizations/homelab/issues/" in p for p in s.paths))

    def test_dev_projects_use_the_shorter_threshold(self):
        items = [("orrery-dev", issue(1, 4)), ("orrery-dev", issue(2, 2)),
                 ("orrery-prod", issue(3, 4)), ("orrery-prod", issue(4, 15))]
        stale, kept = rs.plan(items, NOW, days=14, dev_days=3)
        self.assertEqual(dict(stale), {"orrery-dev": [1], "orrery-prod": [4]})
        self.assertEqual(dict(kept), {"orrery-dev": 1, "orrery-prod": 1})

    def test_is_dev(self):
        self.assertTrue(rs.is_dev("podcast-pipeline-dev"))
        self.assertTrue(rs.is_dev("Player-Dev"))
        self.assertFalse(rs.is_dev("devwhateverops-web"))
        self.assertFalse(rs.is_dev("orrery"))


if __name__ == "__main__":
    unittest.main()
