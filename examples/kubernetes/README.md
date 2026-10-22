# Kubernetes examples

Separate Kustomize bases and overlays are provided for the client and server.
Both use the project's `ghcr.io/pwshdevs` images with the `edge` tag, published
from `main`. The endpoint and DNS records are placeholders.

```text
base/client/                 Deployment and records ConfigMap
base/server/                 Deployment and internal HTTP Service
overlays/client-example/     Client image, endpoint and DNS records
overlays/server-example/     Server image and proxy settings
```

Run these commands from the repository root. Copy the example overlays to local
directories beside them; `*-local/` overlays are ignored by Git.

```sh
cp -R examples/kubernetes/overlays/client-example examples/kubernetes/overlays/client-local
cp -R examples/kubernetes/overlays/server-example examples/kubernetes/overlays/server-local
```

To pin a release, change `newTag` under `images` in each local
`kustomization.yaml` to a published version. For the client, edit `records.json` with your Zone IDs and existing
A records, and set `IP_URL` in `settings.yaml`. For the server, configure any
additional trusted proxy addresses in `settings.yaml`; see the
[proxy configuration notes](../docker/README.md#reverse-proxies).

## Apply

Render each overlay before applying it:

```sh
kubectl kustomize examples/kubernetes/overlays/client-local
kubectl kustomize examples/kubernetes/overlays/server-local
```

Create namespace `cloudflare-ddns-client` in the client cluster, then use your
secret manager to create a Secret named `cloudflare-ddns-client` with the key
`api-token`. Its value must be a Cloudflare API token with **Zone / DNS / Edit**
for the configured zones. Secret values are not stored in these examples.

Deploy each service to the appropriate cluster, replacing the context names:

```sh
kubectl --context LOCAL_CLUSTER apply -k examples/kubernetes/overlays/client-local
kubectl --context CLOUD_CLUSTER apply -k examples/kubernetes/overlays/server-local
```

The client belongs on the network whose public IPv4 address you want to publish.
It requires no Service or Ingress. The server belongs on an external network.

## Networking

The server's Service is internal. Add an Ingress to the server overlay, forward to
Service port 80 and terminate TLS at the ingress. Set trusted proxy addresses to
the ingress's actual source addresses.

For direct access, change the Service to `LoadBalancer` with source IP
preservation (typically `externalTrafficPolicy: Local`). Verify the externally
reported IP before using it for DNS updates.

To change the internal server port, patch both the `PORT` environment variable
and the named `http` container port. The Service and health probes use that named
port, so the Service's public port can remain 80.

## Configuration updates

The records ConfigMap has a stable name. Applying record changes updates the
mounted directory; after Kubernetes propagates the update, the next client poll
reads it. Keep the directory mount rather than using `subPath`.

Environment settings live in the overlays; Kubernetes does not read Compose env
files. After rotating the API token Secret, restart the client Deployment:

```sh
kubectl --context LOCAL_CLUSTER -n cloudflare-ddns-client rollout restart deployment/cloudflare-ddns-client
```
