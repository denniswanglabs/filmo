#!/usr/bin/env bash
# STEP 1 (v2) — contain RAW egress from the AGENT, not the supervisor.
#
# Egress model (verified): ALL legitimate pipeline egress — the OpenShell L7
# gateway (:8080), the host tool-server (:8770), and the gateway-mediated
# target-site fetches (e.g. stripe.com :443) — is made by the supervisor PID1
# running as ROOT (uid 0). The Hermes agent and its children run as the
# unprivileged 'sandbox' user (uid 998). The audit gap is a HIJACKED AGENT
# opening its OWN socket (uid 998) to an arbitrary host (exfil / host:22 pivot /
# C2), bypassing the L7 gateway's allowlist.
#
# So we DROP direct egress that ORIGINATES from uid 998 (the agent), except to
# loopback, DNS, and the L7 gateway (the cooperating path). Egress from uid 0
# (the supervisor's gateway-enforced path) is untouched, so the full pipeline —
# including conversion_read's target-site fetch — keeps working.
#
# Host-driven via nsenter so it survives the container dropping NET_ADMIN (Step 2).
# Runtime-only; re-run after any container restart / nemoclaw recover.
set -eu
C="$(docker ps --filter name=openshell-filmo --filter status=running --format '{{.Names}}' | grep -vE -- '-prehardened|-rollback|-hardened' | head -1)"
[ -z "$C" ] && { echo "FATAL: no filmo container"; exit 1; }
PID="$(docker inspect "$C" --format '{{.State.Pid}}')"
{ [ -z "$PID" ] || [ "$PID" = "0" ]; } && { echo "FATAL: container not running (pid=$PID)"; exit 1; }
GW=172.18.0.1; GWPORT=8080; AGENT_UID=998
ipt() { nsenter -t "$PID" -n iptables "$@"; }

echo ">> applying agent-egress firewall to $C (pid=$PID) via host nsenter"
ipt -F OUTPUT
ipt -N FILMO_AGENT 2>/dev/null || ipt -F FILMO_AGENT
# Only agent-owned (uid 998) traffic is routed into the restrictive chain.
ipt -A OUTPUT -m owner --uid-owner "$AGENT_UID" -j FILMO_AGENT
# (uid 0 / supervisor egress falls straight through OUTPUT = ACCEPT, unchanged.)

# Within the agent chain, allow only the cooperating paths:
ipt -A FILMO_AGENT -o lo -j ACCEPT                                  # loopback
ipt -A FILMO_AGENT -d 127.0.0.0/8 -j ACCEPT                         # embedded DNS resolver / NAT
ipt -A FILMO_AGENT -m state --state ESTABLISHED,RELATED -j ACCEPT   # return traffic
ipt -A FILMO_AGENT -p udp --dport 53 -j ACCEPT                      # DNS (resolver is loopback anyway)
ipt -A FILMO_AGENT -p tcp --dport 53 -j ACCEPT
ipt -A FILMO_AGENT -p tcp -d "$GW" --dport "$GWPORT" -j ACCEPT      # cooperating agent -> L7 gateway
# Everything else from the agent (raw internet, host:22, host:8770 direct, C2) is dropped + logged.
ipt -A FILMO_AGENT -m limit --limit 6/min -j LOG --log-prefix "FILMO_AGENT_DROP " --log-level 6
ipt -A FILMO_AGENT -j DROP

echo ">> applied. OUTPUT + FILMO_AGENT ruleset:"
ipt -S OUTPUT
ipt -S FILMO_AGENT
