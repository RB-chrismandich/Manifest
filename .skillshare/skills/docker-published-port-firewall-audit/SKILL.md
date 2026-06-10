---
name: docker-published-port-firewall-audit
description: Use when reviewing or writing host firewall rules (iptables/nftables) meant to restrict access to a Docker-published port, or when a compose change adds a `ports:` mapping that replaces an app-layer auth control (Traefik, reverse-proxy auth) with a network ACL.
---
# Docker-Published Port Firewall Audit

Docker manages its own iptables rules. Traffic to a **published** container port (`ports: "host_ip:host_port:container_port"`) is DNAT'd in the `nat` PREROUTING/`DOCKER` chains and then traverses the **FORWARD** chain (via the `DOCKER-USER` hook) — it does **not** traverse the **INPUT** chain. INPUT only sees traffic terminating on a host-local process. So an `INPUT` ACCEPT/DROP rule added to "lock down" a published port silently does nothing, while printing a success message that gives false assurance.

1. **Identify the exposure model.** Read the compose/run config. Is the port *published* (`ports:`) or only on an internal Docker network (`expose:` / shared network)? Only published ports hit the host's packet-filter path. If the change removes an app-layer control (Traefik TLS + basic-auth + ipallowlist middlewares) and replaces it with a raw `ports:` mapping, treat the auth surface as **regressed** until proven otherwise.

2. **Check which chain the ACL targets.** Grep the deploy/provisioning script for `iptables`/`nft` rules guarding that port. If the rules are `-I INPUT`/`-A INPUT` (or an nft `input` hook), they are on the wrong chain for Docker-published traffic. The correct hook is **`DOCKER-USER`** (traversed before Docker's own FORWARD rules):
   ```
   iptables -I DOCKER-USER -p tcp --dport <port> -s <allowed-cidr> -j RETURN
   iptables -I DOCKER-USER -p tcp --dport <port> -j DROP
   ```
   Verify the RETURN/ACCEPT for the allowlisted source is inserted **above** the DROP (rule order matters; `-I` prepends).

3. **Verify the control is testable, not just present.** A single-`/32` source-IP filter over plaintext HTTP is defense-in-depth, not authentication — it's spoofable on a shared segment and carries no transport encryption. Flag any design where the *sole* remaining control is source-IP on the wrong chain.

4. **Audit the fail-open path.** If the rule-install commands suppress stderr (`2>/dev/null`) and only warn when the `iptables` binary is missing, a privilege failure (no root, no NOPASSWD sudo) leaves the port published with no filter **and no warning**. Require the deploy to surface install failures and `exit 1` (or refuse to start the container) rather than print a green checkmark.

5. **Prefer eliminating the exposure.** When only an internal client needs the service, the strongest fix is to **not publish** the port at all — put both containers on a shared internal Docker network and reach the service by container name/IP. Recommend this over any host-level ACL when the topology allows it.
