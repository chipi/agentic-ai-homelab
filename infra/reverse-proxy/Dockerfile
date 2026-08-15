# Caddy built with the Tailscale plugin. Each site `bind`s its own tailnet node
# (<name>.tail6d0ed4.ts.net) and auto-serves a real Tailscale-issued cert — no
# domain, no internal CA, no split DNS. Tailnet-only, works for anyone on the
# tailnet. See docs/wip/mac-mini-headless-server.md.
FROM caddy:2-builder AS build
RUN xcaddy build --with github.com/tailscale/caddy-tailscale

FROM caddy:2-alpine
COPY --from=build /usr/bin/caddy /usr/bin/caddy
