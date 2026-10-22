"""Reconcile an explicit list of Cloudflare A records with this network's public IP."""
import argparse
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import signal
import threading
import urllib.error
import urllib.parse
import urllib.request

LOG = logging.getLogger("ddns")
API = "https://api.cloudflare.com/client/v4"
STOP = threading.Event()


def request_json(url, token=None, method="GET", payload=None):
    headers = {"Accept": "application/json", "User-Agent": "local-cloudflare-ddns/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise ValueError("Response exceeds size limit")
            result = json.loads(body)
    except urllib.error.HTTPError as error:
        # Do not print headers or response bodies that could contain credentials.
        raise RuntimeError(f"HTTP {error.code} from {urllib.parse.urlsplit(url).hostname}") from None
    except urllib.error.URLError:
        raise RuntimeError(f"Connection failed to {urllib.parse.urlsplit(url).hostname}") from None
    if token and (not isinstance(result, dict) or result.get("success") is not True):
        raise RuntimeError("Cloudflare reported an unsuccessful API response")
    return result


def load_records(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    records = config.get("records")
    if not isinstance(records, list):
        raise ValueError("Configuration must contain a records array")
    parsed = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each records entry must be a JSON object")
        zone = record.get("zone_id", "")
        name = record.get("name", "")
        if not isinstance(zone, str) or not isinstance(name, str):
            raise ValueError("Record zone_id and name must be strings")
        name = name.strip().lower().rstrip(".")
        if not re.fullmatch(r"[a-fA-F0-9]{32}", zone):
            raise ValueError("Each record requires a 32-character Cloudflare zone_id")
        if not re.fullmatch(r"(?:\*\.)?[a-z0-9_-]+(?:\.[a-z0-9_-]+)+", name):
            raise ValueError("Each record requires a full DNS name, e.g. home.example.com")
        if record.get("type", "A") != "A":
            raise ValueError("This updater supports IPv4 A records only")
        key = (zone.lower(), name)
        if key not in parsed:
            parsed.append(key)
    return parsed


def public_ip(url):
    value = request_json(url)
    ip = ipaddress.ip_address(value["ip"])
    if ip.version != 4 or not ip.is_global or ip.is_multicast:
        raise ValueError("IP endpoint must return a public IPv4 address in the ip field")
    return str(ip)


def reconcile(records, ip, token, dry_run=False):
    failures = 0
    for zone, name in records:
        try:
            query = urllib.parse.urlencode({"type": "A", "name": name, "per_page": 100})
            result = request_json(f"{API}/zones/{zone}/dns_records?{query}", token)
            matches = result["result"]
            if (len(matches) != 1 or result.get("result_info", {}).get("total_pages", 1) > 1
                    or matches[0].get("type") != "A"
                    or matches[0].get("name", "").lower().rstrip(".") != name):
                raise ValueError("Expected exactly one existing A record; missing/ambiguous record skipped")
            record = matches[0]
            if record["content"] == ip:
                LOG.debug("Unchanged: %s", name)
                continue
            if dry_run:
                LOG.info("DRY RUN: %s would change from %s to %s", name, record["content"], ip)
                continue
            record_id = record["id"]
            if not re.fullmatch(r"[a-fA-F0-9]{32}", record_id):
                raise ValueError("Unexpected Cloudflare record ID")
            # PATCH only content: preserve proxy status, TTL, comments and other settings.
            updated = request_json(f"{API}/zones/{zone}/dns_records/{record_id}", token,
                                   "PATCH", {"content": ip})
            if updated["result"].get("content") != ip:
                raise RuntimeError("Cloudflare did not confirm the requested IP")
            LOG.info("Updated %s: %s -> %s", name, record["content"], ip)
        except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
            LOG.error("%s: %s", name, error)
            failures += 1
    return failures == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Read DNS but never update it")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        parser.error("Set CLOUDFLARE_API_TOKEN")
    try:
        interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
        if interval < 30:
            raise ValueError()
    except ValueError:
        parser.error("POLL_INTERVAL_SECONDS must be an integer >= 30")
    config = os.environ.get("RECORDS_FILE", "/config/records.json")
    url = os.environ.get("IP_URL", "").strip()
    if (urllib.parse.urlsplit(url).scheme not in ("http", "https")
            or not urllib.parse.urlsplit(url).hostname):
        parser.error("Set IP_URL to the HTTP or HTTPS URL of your public-IP server")
    dry_run = args.dry_run or os.environ.get("DRY_RUN", "false").lower() == "true"
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    LOG.info("Starting IPv4 updater; interval=%ss dry_run=%s", interval, dry_run)
    last_ip = None
    while not STOP.is_set():
        ok = False
        try:
            # Reload each cycle; editing/replacing the file needs no container restart.
            records = load_records(config)
            if not records:
                LOG.info("No records configured; nothing to update")
                ok = True
            else:
                ip = public_ip(url)
                if ip != last_ip:
                    LOG.info("Public IPv4: %s", ip)
                    last_ip = ip
                ok = reconcile(records, ip, token, dry_run)
                LOG.info("Check complete: %s record(s), success=%s", len(records), ok)
        except (ValueError, KeyError, TypeError, RuntimeError, OSError) as error:
            LOG.error("Check failed; no further updates this cycle: %s", error)
        if args.once:
            return 0 if ok else 1
        # Recheck DNS even if IP is unchanged: handles config edits, drift and partial failures.
        STOP.wait(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
