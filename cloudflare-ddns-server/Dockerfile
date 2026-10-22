FROM nginx:stable-alpine
ARG VERSION=dev
ARG REVISION=unknown
COPY nginx.conf.template cloudflare-proxies.conf /etc/nginx/
COPY start.sh /start.sh
ENV PORT=80 REAL_IP_HEADER=X-Forwarded-For
ENV SERVER_VERSION=${VERSION} SERVER_REVISION=${REVISION}
USER 65532:65532
EXPOSE 80
ENTRYPOINT ["sh", "/start.sh"]
