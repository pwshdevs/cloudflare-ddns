"""Smoke-test a running server, including untrusted forwarding headers."""
import ipaddress
import json
import sys
import time
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/")
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
    original_ip = json.load(response)["ip"]
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
print("Server smoke checks passed")
