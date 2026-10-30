"""Offline checks for scrub.py's IPv4 rule. No network.

  python3 test_scrub.py     # non-zero on failure
"""
import unittest

import scrub

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")


class IPv4(unittest.TestCase):
    def test_user_agent_versions_are_left_alone(self):
        self.assertEqual(scrub.scrub_str(UA), UA)
        self.assertEqual(scrub.scrub_str("HeadlessChrome/156.0.8078.4"), "HeadlessChrome/156.0.8078.4")

    def test_addresses_are_still_scrubbed(self):
        self.assertEqual(scrub.scrub_str("client 203.0.113.7 connected"), "client <ip> connected")
        self.assertEqual(scrub.scrub_str("upstream=10.1.2.3:8080"), "upstream=<ip>:8080")
        self.assertNotIn("192.168.1.20", scrub.scrub_str("GET http://192.168.1.20/health"))
        self.assertNotIn("100.64.0.9", scrub.scrub_str('{"ip": "100.64.0.9"}'))

    def test_idempotent(self):
        once = scrub.scrub_str("from 203.0.113.7 via " + UA)
        self.assertEqual(scrub.scrub_str(once), once)


if __name__ == "__main__":
    unittest.main()
