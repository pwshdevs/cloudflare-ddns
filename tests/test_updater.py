import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cloudflare-ddns-client"))

import updater

ZONE = "a" * 32
ID = "b" * 32
NAME = "home.example.com"


def response(ip="8.8.8.8"):
    return {"result": [{"id": ID, "name": NAME, "type": "A", "content": ip,
                        "proxied": True, "ttl": 1, "comment": "preserve me"}]}


class UpdaterTests(unittest.TestCase):
    @patch("updater.request_json", return_value=response())
    def test_unchanged_is_not_written(self, request):
        self.assertTrue(updater.reconcile([(ZONE, NAME)], "8.8.8.8", "secret"))
        self.assertEqual(request.call_count, 1)

    @patch("updater.request_json")
    def test_patch_only_changes_ip(self, request):
        request.side_effect = [response(), {"result": {"content": "1.1.1.1"}}]
        self.assertTrue(updater.reconcile([(ZONE, NAME)], "1.1.1.1", "secret"))
        self.assertEqual(request.call_args.args,
                         (f"{updater.API}/zones/{ZONE}/dns_records/{ID}",
                          "secret", "PATCH", {"content": "1.1.1.1"}))

    @patch("updater.request_json", return_value=response())
    def test_dry_run_never_writes(self, request):
        self.assertTrue(updater.reconcile([(ZONE, NAME)], "1.1.1.1", "secret", True))
        self.assertEqual(request.call_count, 1)

    @patch("updater.request_json")
    def test_missing_and_ambiguous_records_never_written(self, request):
        for matches in ([], response()["result"] * 2):
            request.reset_mock()
            request.return_value = {"result": matches}
            self.assertFalse(updater.reconcile([(ZONE, NAME)], "1.1.1.1", "secret"))
            self.assertEqual(request.call_count, 1)

    @patch("updater.request_json")
    def test_partial_failure_continues_and_next_cycle_retries(self, request):
        request.side_effect = [RuntimeError("HTTP 503"), response(),
                               {"result": {"content": "1.1.1.1"}}]
        self.assertFalse(updater.reconcile([(ZONE, "bad.example.com"), (ZONE, NAME)], "1.1.1.1", "secret"))
        self.assertEqual(request.call_count, 3)
        request.side_effect = [response(), {"result": {"content": "1.1.1.1"}}]
        self.assertTrue(updater.reconcile([(ZONE, NAME)], "1.1.1.1", "secret"))

    @patch("updater.request_json")
    def test_ip_validation(self, request):
        for ip in ("127.0.0.1", "172.18.0.1", "224.0.0.1", "::1", "2606:4700:4700::1111", "invalid"):
            request.return_value = {"ip": ip}
            with self.assertRaises(ValueError):
                updater.public_ip("http://example.com/ip")
        request.return_value = {"ip": "1.1.1.1"}
        self.assertEqual(updater.public_ip("http://example.com/ip"), "1.1.1.1")

    @patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test", "IP_URL": "https://ip.example.com/ip"}, clear=True)
    @patch("sys.argv", ["updater", "--once"])
    @patch("updater.signal.signal")
    @patch("updater.reconcile")
    @patch("updater.public_ip", side_effect=RuntimeError("Endpoint unreachable"))
    @patch("updater.load_records", return_value=[(ZONE, NAME)])
    def test_failed_ip_lookup_leaves_dns_untouched(self, records, ip, reconcile, signals):
        self.assertEqual(updater.main(), 1)
        reconcile.assert_not_called()

    @patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "test"}, clear=True)
    @patch("sys.argv", ["updater", "--once"])
    @patch("updater.request_json")
    def test_endpoint_is_required_before_network_calls(self, request):
        with self.assertRaises(SystemExit) as error:
            updater.main()
        self.assertEqual(error.exception.code, 2)
        request.assert_not_called()

    def test_configuration_reload_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            path.write_text(json.dumps({"records": [{"zone_id": ZONE, "name": NAME}]}))
            self.assertEqual(updater.load_records(path), [(ZONE, NAME)])
            path.write_text('{"records": []}')
            self.assertEqual(updater.load_records(path), [])
            path.write_text(json.dumps({"records": [{"zone_id": ZONE, "name": NAME, "type": "AAAA"}]}))
            with self.assertRaises(ValueError):
                updater.load_records(path)


if __name__ == "__main__":
    unittest.main()
