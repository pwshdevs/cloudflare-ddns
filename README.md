# Cloudflare DDNS

Keep existing Cloudflare A records pointed at a network's public IPv4 address.

The project has two independent containers:

- **Client** — a Python updater that polls an IP endpoint and updates configured
  Cloudflare DNS records.
- **Server** — an Nginx endpoint that returns the caller's IP as JSON.

Run the client on the network you want to publish and the server somewhere
external to that network. The client can also use another endpoint that returns
`{"ip":"<public IPv4>"}`.

## Deployment examples

[Docker Compose](examples/docker/README.md) and
[Kubernetes / Kustomize](examples/kubernetes/README.md) examples are included.
Customize their records, endpoints and proxy settings for your
environment. The workflow builds images; it does not deploy either service.

The client needs a Cloudflare API token with **Zone / DNS / Edit**, scoped to the
zones it manages, and the Zone IDs for those zones. Credentials and DNS records
are supplied at runtime.

## Behavior

The client checks immediately, then every 300 seconds by default. It reloads the
records file on every poll and changes only each record's IP address, preserving
TTL, proxy status and comments. It does not create or delete records.
Missing or ambiguous records are skipped, and failed updates are retried on the
next poll. IPv6 / AAAA records are not supported.

The server provides `GET /ip` and `GET /healthz`. It supports direct connections
and trusted reverse proxies, including Cloudflare. For public use, terminate TLS
at a reverse proxy and disable caching for `/ip`. See the deployment examples for
proxy configuration.

`/ip` allows one request per second per client IP, with five excess requests
allowed in a burst. Further requests receive HTTP 429. `/healthz` is exempt.
Limits apply per server instance and use the original client IP behind trusted
proxies.

Successful `/ip` responses include the service and build identity:

```json
{"ip":"203.0.113.10","service":"cloudflare-ddns-server","version":"edge","revision":"ab6ad19..."}
```

GitHub builds use `edge` or the release version and the full commit SHA.
Local builds default to version `dev` and revision `unknown`; set Docker build
arguments `VERSION` and `REVISION` to override them. The client reads only `ip`.

## Container images

GitHub Actions builds both images for `linux/amd64` and `linux/arm64`:

```text
ghcr.io/pwshdevs/cloudflare-ddns-client
ghcr.io/pwshdevs/cloudflare-ddns-server
```

| Trigger | Result |
| --- | --- |
| Pull request or manual run | Test and build; no publication |
| Push to `main` | Publish `edge` and `sha-<full-commit>` |
| Tag `v1.2.3` | Publish `1.2.3`, `1.2`, `latest` and the SHA tag |
| Tag `v1.2.3-rc.1` | Publish `1.2.3-rc.1` and the SHA tag |

Version tags use `vMAJOR.MINOR.PATCH`, optionally followed by a prerelease suffix.
Deployment examples pull `edge`, built from `main`. Pin a published release tag
or image digest when you need a fixed version.
The workflow authenticates to GHCR with GitHub's built-in `GITHUB_TOKEN`.
After the first publication, set each package's visibility to Public if anonymous
pulls are needed. See [GitHub's container registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Development

Python 3.12 and Docker are sufficient to run the tests and build the images.
The client uses only the Python standard library.

```sh
python -m unittest discover -s tests -v
docker build -t cloudflare-ddns-client:local cloudflare-ddns-client
docker build -t cloudflare-ddns-server:local cloudflare-ddns-server
python tests/smoke_proxy.py cloudflare-ddns-server:local
```

CI runs the client tests, server smoke tests, Compose validation and Kustomize
rendering before building the multi-platform images. Tests do not change DNS.

Cloudflare's trusted proxy ranges are stored in
[cloudflare-proxies.conf](cloudflare-ddns-server/cloudflare-proxies.conf).
Check them against Cloudflare's [IPv4](https://www.cloudflare.com/ips-v4) and
[IPv6](https://www.cloudflare.com/ips-v6) lists when updating the server.
