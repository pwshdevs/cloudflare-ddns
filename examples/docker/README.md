# Docker Compose examples

These examples pull the project's images from `ghcr.io/pwshdevs`. Run the client on the
network whose public IP you want to publish; run the server on a separate host.
Both examples use a non-root user, a read-only filesystem and dropped capabilities.

Run the commands below from this directory:

```sh
cd examples/docker
```

## Client

Copy the configuration templates:

```sh
cp client.env.example client.env
mkdir -p config
cp records.example.json config/records.json
```

Set `CLOUDFLARE_API_TOKEN` and `IP_URL` in `client.env`. The token needs
**Zone / DNS / Edit** for each configured zone; `IP_URL` is the server's full
HTTPS `/ip` URL.

Edit `config/records.json` with your Zone IDs and existing A record names. Use the
full domain for apex records, not `@`. Keep the IP server's own hostname out of
this list. Files in `config/` and local `*.env` files are ignored by Git.

```sh
docker compose --env-file client.env -f compose.client.yaml pull
docker compose --env-file client.env -f compose.client.yaml run --rm ddns --once --dry-run
docker compose --env-file client.env -f compose.client.yaml up -d
docker compose --env-file client.env -f compose.client.yaml logs -f --tail=50 ddns
```

| Setting | Default | Purpose |
| --- | --- | --- |
| `CLOUDFLARE_API_TOKEN` | Required | Token for the configured zones |
| `IP_URL` | Required | Endpoint returning `{"ip":"<public IPv4>"}` |
| `POLL_INTERVAL_SECONDS` | `300` | Seconds between checks; minimum 30 |
| `DRY_RUN` | `false` | Log proposed changes without writing to Cloudflare |

Record edits are picked up on the next poll. After changing `client.env`, run
the same `up -d` command to recreate the container. `--once` exits nonzero on
failure. An empty records list performs no updates.

The client needs no inbound ports. Its reported address follows outbound routing,
including VPNs. Use an endpoint reachable over IPv4; IPv6 responses are rejected.

## Server

```sh
cp server.env.example server.env
docker compose --env-file server.env -f compose.server.yaml pull
docker compose --env-file server.env -f compose.server.yaml up -d
curl http://localhost:8090/ip
```

| Setting | Default | Purpose |
| --- | --- | --- |
| `HOST_PORT` | `8090` | Published host port |
| `CONTAINER_PORT` | `80` | Nginx HTTP port |
| `BIND_ADDRESS` | `0.0.0.0` | Host interface; use `127.0.0.1` for a host proxy |
| `TRUSTED_PROXY_CIDRS` | Empty | Additional trusted proxy source IPs or CIDRs |
| `REAL_IP_HEADER` | `X-Forwarded-For` | Header supplied by trusted proxies |

The example permits non-root binding to port 80 with a network sysctl and mounts
writable `/tmp`. The server serves HTTP; terminate TLS at your reverse proxy.

### Reverse proxies

Direct requests return the socket peer's IP. Cloudflare's published proxy ranges
are trusted by the image. For another reverse proxy, set `TRUSTED_PROXY_CIDRS`
to its actual source IPs or narrowly scoped CIDRs, separated by commas or spaces.
That proxy must overwrite or correctly append `X-Forwarded-For`.

`REAL_IP_HEADER` also supports `CF-Connecting-IP` or `X-Real-IP` if your proxy
supplies that header. With multiple proxy layers, configure trust at each layer.
Do not trust all Internet addresses or a whole container network to work around
source NAT. Verify the endpoint externally: localhost Docker requests commonly
report a Docker gateway address.

`/ip` sends `Cache-Control: no-store`; configure the CDN or reverse proxy to
bypass caching and browser challenges for this route. With Cloudflare, use
Full (strict) TLS to your reverse proxy and avoid Pseudo IPv4's overwrite mode.
`/healthz` returns `ok`; other routes return 404. Access logging is disabled.

## Image versions

Both examples use `edge`, published from `main`. To use a fixed version, change
the service's `image` to a published release tag or digest, for example:

```yaml
image: ghcr.io/pwshdevs/cloudflare-ddns-client:1.2.3
```

Use `cloudflare-ddns-server` for the server. Then run the matching Compose
command with `pull`, followed by `up -d`. The version above is illustrative; use
a tag that has been published.

Existing local configuration from the former root Compose file must be copied
into this directory: `.env` becomes `client.env`, and `config/records.json`
becomes `examples/docker/config/records.json`. The examples do not read the old
root configuration.
