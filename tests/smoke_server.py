"""Smoke-test a running server, including untrusted forwarding headers."""
import ipaddress
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import time
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/")
version = sys.argv[2] if len(sys.argv) > 2 else "dev"
revision = sys.argv[3] if len(sys.argv) > 3 else "unknown"
for attempt in range(30):
    try:
        with urllib.request.urlopen(base + "/healthz", timeout=2) as response:
            assert response.read() == b"ok\n"
        break
    except (OSError, AssertionError):
        if attempt == 29:
            raise
        time.sleep(1)

with urllib.request.urlopen(base + "/ip", timeout=5) as response:
    assert response.headers.get_content_type() == "application/json"
    assert response.headers["Cache-Control"] == "no-store"
    payload = json.load(response)
    original_ip = payload["ip"]
    assert payload == {"ip": original_ip, "service": "cloudflare-ddns-server",
                       "version": version, "revision": revision}, payload
    ipaddress.ip_address(original_ip)
request = urllib.request.Request(base + "/ip", headers={
    "X-Forwarded-For": "203.0.113.123", "CF-Connecting-IP": "203.0.113.124"})
with urllib.request.urlopen(request, timeout=5) as response:
    assert json.load(response)["ip"] == original_ip, "Untrusted headers changed reported IP"
try:
    urllib.request.urlopen(base + "/not-found", timeout=5)
except urllib.error.HTTPError as error:
    assert error.code == 404
else:
    raise AssertionError("Unknown route should return 404")

def flood_request(index):
    # Changing untrusted headers must not create fresh rate-limit buckets.
    request = urllib.request.Request(base + "/ip", headers={
        "X-Forwarded-For": f"203.0.113.{index + 1}",
        "CF-Connecting-IP": f"198.51.100.{index + 1}"})
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.headers["Cache-Control"] == "no-store"
        return response.code

with ThreadPoolExecutor(max_workers=12) as pool:
    statuses = list(pool.map(flood_request, range(24)))
assert 429 in statuses, f"Flood was not limited: {statuses}"
assert set(statuses) <= {200, 429}, statuses
with urllib.request.urlopen(base + "/healthz", timeout=5) as response:
    assert response.read() == b"ok\n", "Health checks must remain available"
time.sleep(1.2)
with urllib.request.urlopen(base + "/ip", timeout=5) as response:
    assert json.load(response)["ip"] == original_ip, "Limit did not recover"
print("Server smoke checks passed")
