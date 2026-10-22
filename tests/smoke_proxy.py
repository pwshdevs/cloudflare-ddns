"""Exercise real Nginx containers with direct and trusted-proxy requests."""
import json
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid

image = sys.argv[1] if len(sys.argv) > 1 else "cloudflare-ddns-server:local"
version = sys.argv[2] if len(sys.argv) > 2 else "dev"
revision = sys.argv[3] if len(sys.argv) > 3 else "unknown"

def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()

for port, header, trust in ((80, "X-Forwarded-For", ""),
                            (8123, "X-Forwarded-For", "127.0.0.1/32"),
                            (80, "CF-Connecting-IP", "127.0.0.1/32")):
    name = "ddns-test-" + uuid.uuid4().hex[:12]
    try:
        docker("run", "-d", "--name", name, "--read-only", "--tmpfs",
               "/tmp:rw,noexec,nosuid,size=16m,mode=1777", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges:true", "--sysctl",
               "net.ipv4.ip_unprivileged_port_start=0",
               "-e", f"PORT={port}", "-e", f"REAL_IP_HEADER={header}",
               "-e", f"TRUSTED_PROXY_CIDRS={trust}", "-p", f"127.0.0.1::{port}", image)
        host_port = docker("port", name, f"{port}/tcp").rsplit(":", 1)[1]
        subprocess.run([sys.executable, str(Path(__file__).with_name("smoke_server.py")),
                        f"http://127.0.0.1:{host_port}", version, revision], check=True)
        supplied = "203.0.113.8, 198.51.100.9" if header == "X-Forwarded-For" else "198.51.100.9"
        body = docker("exec", name, "wget", "-qO-", "--header", f"{header}: {supplied}",
                      f"http://127.0.0.1:{port}/ip")
        expected = "198.51.100.9" if trust else "127.0.0.1"
        assert json.loads(body)["ip"] == expected, body
        if trust:
            # Send a rapid burst through a trusted hop, then use another client
            # address through that same hop to verify independent buckets.
            output = docker("exec", name, "sh", "-c",
                            'for i in 1 2 3 4 5 6 7 8 9 10 11 12; do '
                            'wget -S -O /dev/null --header "$1" "$2" 2>&1; done; true',
                            "sh", f"{header}: {supplied}", f"http://127.0.0.1:{port}/ip")
            statuses = re.findall(r"HTTP/1\.[01] (\d{3})", output)
            assert "200" in statuses and "429" in statuses, output
            assert set(statuses) <= {"200", "429"}, output
            body = docker("exec", name, "wget", "-qO-", "--header",
                          f"{header}: 198.51.100.10", f"http://127.0.0.1:{port}/ip")
            assert json.loads(body)["ip"] == "198.51.100.10", body
        print(f"Passed: port={port}, header={header}, trusted={bool(trust)}")
    finally:
        subprocess.run(["docker", "logs", name], check=False)
        subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL)
