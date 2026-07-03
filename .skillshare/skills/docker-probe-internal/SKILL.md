---
name: docker-probe-internal
description: Use to test or debug a service that only listens on an internal Docker network (no host port, no public route) when host curl/wget is unavailable or blocked
---
# Containerized Internal-Service Probe

When a sidecar or backend service is reachable only by other containers on a private Docker network (no published port,
no reverse-proxy route), you cannot probe it from the host. Spawn a throwaway container on the same network instead.

1. **Identify the network and service address** — find the compose network name (often `${PROJECT_NAME}_backend` or an
   `external` network) and the service's in-network host:port (the compose service name resolves via Docker DNS, e.g.
   `controld-stats:8080`).
2. **Pick a base image you already have** — reuse the service's own image or a tiny stdlib image (`python:3.13-slim`,
   `alpine`) so no extra pull is needed.
3. **Run a one-shot probe attached to that network** — use the language's stdlib HTTP client to avoid depending on
   curl/wget being installed:

   ```bash
   docker run --rm --network ${PROJECT_NAME}_backend python:3.13-slim \
     python -c "import urllib.request,json; print(json.load(urllib.request.urlopen('http://controld-stats:8080/summary')))"
   ```

4. **Assert on the parsed response, not just status** — print the decoded JSON/body so you can confirm the payload
   shape, not merely that the port is open.
5. **Probe before wiring consumers** — verify the internal service returns valid data standalone before pointing the
   dashboard/app/other service at it. This isolates "is the service healthy" from "is the integration correct."
6. **For deeper debugging, drop into an interactive container** — `docker run --rm -it --network <net> <image> sh` to
   run repeated probes, DNS lookups, or check reachability of multiple in-network hosts.
