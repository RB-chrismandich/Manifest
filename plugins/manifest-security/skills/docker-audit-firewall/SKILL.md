---
name: docker-audit-firewall
description: Use when reviewing/writing host firewall rules (iptables/nftables) for a Docker-published port, or when a compose change adds a `ports:` mapping that replaces app-layer auth (Traefik, reverse-proxy) with a network ACL.
---
# Docker-Published Port Firewall Audit

Docker manages its own iptables rules. Traffic to a **published** container port (`ports:
"host_ip:host_port:container_port"`) is DNAT'd in the `nat` PREROUTING/`DOCKER` chains and then traverses the
**FORWARD** chain (via the `DOCKER-USER` hook) — it does **not** traverse the **INPUT** chain. INPUT only sees traffic
terminating on a host-local process. So an `INPUT` ACCEPT/DROP rule added to "lock down" a published port silently does
nothing, while printing a success message that gives false assurance.

1. **Identify the exposure model.** Read the compose/run config. Is the port *published* (`ports:`) or only on an
   internal Docker network (`expose:` / shared network)? Only published ports hit the host's packet-filter path. If the
   change removes an app-layer control (Traefik TLS + basic-auth + ipallowlist middlewares) and replaces it with a raw
   `ports:` mapping, treat the auth surface as **regressed** until proven otherwise.

2. **Check which chain the ACL targets.** Grep the deploy/provisioning script for `iptables`/`nft` rules guarding that
   port. If the rules are `-I INPUT`/`-A INPUT` (or an nft `input` hook), they are on the wrong chain for
   Docker-published traffic. The correct hook is **`DOCKER-USER`** (traversed before Docker's own FORWARD rules):

   ```text
   # -I prepends, so insert the DROP first, then the RETURN on top of it
   iptables -I DOCKER-USER -p tcp -m conntrack --ctstate DNAT --ctorigdstport <host_port> --ctdir ORIGINAL -j DROP
   iptables -I DOCKER-USER -p tcp -m conntrack --ctstate DNAT --ctorigdstport <host_port> --ctdir ORIGINAL \
     -s <allowed-cidr> -j RETURN
   # Same pair for IPv6 unless the port is published IPv4-only (ports: "0.0.0.0:<host>:<container>")
   ip6tables -I DOCKER-USER -p tcp -m conntrack --ctstate DNAT --ctorigdstport <host_port> --ctdir ORIGINAL -j DROP
   ip6tables -I DOCKER-USER -p tcp -m conntrack --ctstate DNAT --ctorigdstport <host_port> --ctdir ORIGINAL \
     -s <allowed-cidr6> -j RETURN   # omit this RETURN if no IPv6 source is allowed
   ```

   Resulting chain order (`iptables -L DOCKER-USER -n --line-numbers`): **1 = RETURN** for the allowlisted
   source, **2 = DROP** for everyone else. The RETURN must sit **above** the DROP. Each `-I` prepends to the top,
   so the rule inserted *last* ends up *first* — issuing RETURN then DROP (both `-I`) leaves DROP on top and blocks
   the allowlisted source too. Flag any script that does that. With `-A` (append) the order is the reverse:
   RETURN first, then DROP — but `-A` lands after Docker's own trailing `-j RETURN` in DOCKER-USER, so prefer
   `-I`. DOCKER-USER sees packets after DNAT, so a bare `--dport` matches the *container* port of **every**
   forwarded container — a DROP on `--dport 443` also blocks unrelated containers listening on 443 internally,
   even when the host and container port numbers are equal. Scope the rule to the published host port with
   conntrack's pre-DNAT `--ctorigdstport <host_port>` and flag any DOCKER-USER rule that uses a bare `--dport`.
   Pair it with `--ctstate DNAT`: DOCKER-USER also sees container egress and other routed traffic, and without the
   DNAT discriminator a rule for published port 443 also drops containers' outbound HTTPS.

   **Scope of this rule pair:** it filters only NAT-published traffic that is forwarded through DOCKER-USER.
   It does **not** cover (a) routed/direct-routing networks (`gateway_mode_ipv4`/`gateway_mode_ipv6=routed`, or
   clients reaching the container IP directly), which are not DNAT; or (b) IPv6 connections the default userland
   proxy accepts in a host process when the bridge is IPv4-only, which never traverse IPv6 DOCKER-USER. An
   `ip6tables` pair covers only IPv6 that is NAT-published on an IPv6-enabled bridge.

   **Verify these preconditions before approving the ACL** (from the config/script, or ask for the output):
   - `/etc/docker/daemon.json`: `firewall-backend`, `userland-proxy`, `ipv6`, `ip6tables`, `allow-direct-routing`;
   - `docker info --format '{{.FirewallBackend}}'`: the backend actually in use (daemon.json may omit it);
   - `docker network inspect <net>`: `com.docker.network.bridge.gateway_mode_ipv4` / `_ipv6`,
     `com.docker.network.bridge.trusted_host_interfaces`, and `EnableIPv6`;
   - `ss -ltnp` on the host: no `[::]:<host_port>` listener unless the IPv6 pair is installed on an IPv6 bridge.

   Approve only when Docker uses the `iptables` firewall backend (the default; with `firewall-backend: nftables`
   there is no DOCKER-USER chain, so these rules filter nothing), the traffic is NAT-published on a bridge (no
   routed gateway mode, no direct routing, no `trusted_host_interfaces` — that option lets those interfaces reach
   published container ports directly, without DNAT), and IPv6 is covered according to the bridge's IPv6 setting
   (`EnableIPv6` / daemon `ipv6`): on an **IPv6-enabled bridge**, a wildcard publication is NAT-published over IPv6
   too, so require the `ip6tables` pair (`userland-proxy: false` does not help there); on an **IPv4-only bridge**,
   require `userland-proxy: false` or an IPv4-only publication address (`ports: "0.0.0.0:<host>:<container>"`)
   so the proxy cannot accept IPv6 on the host. If any precondition is non-default or unknown,
   report the ACL as **unverified — needs manual review** and name the uncovered path; never call it complete.
   The fix for those paths is to publish IPv4-only, disable the userland proxy, or filter on the path that actually
   carries the traffic. See Docker's
   [port publishing and direct routing](https://docs.docker.com/engine/network/port-publishing/).
   Add `--ctorigdst <host_ip>` / `-i <ext_if>` only when the port is published on
   that specific address (`ports: "IP:host:container"`) or when every published address/interface gets its own rule
   pair: on a wildcard publication (address-unspecified, or `0.0.0.0`/`::`), one interface/address qualifier leaves
   the other paths unfiltered and `--ctorigdst 0.0.0.0` matches nothing — both fail open, so flag them.
   Add `--ctdir ORIGINAL`: conntrack's original-tuple match applies to both directions of a flow, so without it the
   container's reply packets also match the DROP (and fail the `-s` RETURN), breaking allowlisted connections
   whenever the rule is not pinned to the ingress interface. See Docker's
   [match the original IP and ports](https://docs.docker.com/engine/network/firewall-iptables/#match-the-original-ip-and-ports).

3. **Verify the control is testable, not just present.** The primary check is behavioral: from a host that is
   **not** on the allowlist, connect to the published port over **both IPv4 and IPv6** (e.g.
   `nc -vz -w3 <host_ipv4> <port>` and `nc -6 -vz -w3 <host_ipv6> <port>`) and confirm both are refused, then
   confirm an allowlisted source still connects. Rule listings (`iptables`/`ip6tables -L DOCKER-USER`,
   `docker port`, `ss -ltn`) are supporting evidence only — they cannot prove there is no unfiltered path, so never
   report the ACL as effective from them alone; if the reachability test cannot be run, report it as unverified.
   A single-`/32` source-IP filter over plaintext HTTP is
   defense-in-depth, not authentication — it's spoofable on a shared segment and carries no transport encryption. Flag
   any design where the *sole* remaining control is source-IP on the wrong chain.

4. **Audit the fail-open path.** If the rule-install commands suppress stderr (`2>/dev/null`) and only warn when the
   `iptables` binary is missing, a privilege failure (no root, no NOPASSWD sudo) leaves the port published with no
   filter **and no warning**. Require the deploy to surface install failures and `exit 1` (or refuse to start the
   container) rather than print a green checkmark.

5. **Prefer eliminating the exposure.** When only an internal client needs the service, the strongest fix is to **not
   publish** the port at all — put both containers on a shared internal Docker network and reach the service by
   container name/IP. Recommend this over any host-level ACL when the topology allows it.
