# Caddy with the rate-limit module (per-IP limits in deploy/Caddyfile).
FROM caddy:2.10-builder AS build
RUN xcaddy build --with github.com/mholt/caddy-ratelimit

FROM caddy:2.10
COPY --from=build /usr/bin/caddy /usr/bin/caddy
