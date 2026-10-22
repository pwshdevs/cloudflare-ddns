#!/bin/sh
set -eu
case "$PORT" in ''|*[!0-9]*) echo "PORT must be an integer from 1 to 65535" >&2; exit 1;; esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "PORT must be an integer from 1 to 65535" >&2; exit 1
fi
case "$REAL_IP_HEADER" in X-Forwarded-For|CF-Connecting-IP|X-Real-IP) ;; *)
    echo "REAL_IP_HEADER must be X-Forwarded-For, CF-Connecting-IP, or X-Real-IP" >&2; exit 1;;
esac
cp /etc/nginx/cloudflare-proxies.conf /tmp/trusted-proxies.conf
# Trust additional immediate proxies only when explicitly configured by the operator.
for cidr in $(printf '%s' "${TRUSTED_PROXY_CIDRS:-}" | tr ',' ' '); do
    case "$cidr" in *[!0-9a-fA-F:./]*) echo "Invalid TRUSTED_PROXY_CIDRS entry" >&2; exit 1;; esac
    case "$cidr" in */0) echo "Refusing to trust the entire Internet" >&2; exit 1;; esac
    printf 'set_real_ip_from %s;\n' "$cidr" >> /tmp/trusted-proxies.conf
done
envsubst '${PORT} ${REAL_IP_HEADER}' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf
exec nginx -c /tmp/nginx.conf -g 'daemon off;'
