#!/usr/bin/env bash
# STEP 2 — drop container privileges via faithful commit + recreate.
# Removes the dangerous capabilities (SYS_ADMIN, SYS_PTRACE, SYSLOG, NET_ADMIN)
# and restores the DEFAULT docker apparmor profile, while preserving the gateway's
# exact network/mounts/env/labels/entrypoint so the supervisor + conduct keep working.
# The egress firewall (Step 1) is host-managed via nsenter, so dropping NET_ADMIN
# does NOT lose it. PID1 (the openshell supervisor) stays root (it needs root to set
# up the ssh-socket relay); the agent (hermes) already runs as the unprivileged
# 'sandbox' user (uid 998).
#
# The OLD container is RENAMED (not deleted) to <name>-prehardened for rollback.
set -eu
C="$(docker ps -a --filter name=openshell-filmo --format '{{.Names}}' | grep -v -- '-prehardened' | head -1)"
[ -z "$C" ] && { echo "FATAL: no filmo container"; exit 1; }
echo ">> hardening caps on $C"

# 1. Snapshot the live rootfs to a new image
IMG="filmo-hardened:$(date -u +%Y%m%dT%H%M%SZ)"
docker commit "$C" "$IMG" >/dev/null
echo ">> committed rootfs -> $IMG"

# 2. Extract the exact spec to reproduce
NET="$(docker inspect "$C" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}')"
SHM="$(docker inspect "$C" --format '{{.HostConfig.ShmSize}}')"
echo ">> network=$NET shm=$SHM"

# Build run-arg arrays (no eval; arrays preserve word boundaries safely)
ARGS=(-d --name "$C" --network "$NET" --restart unless-stopped --shm-size "$SHM")
while IFS= read -r h; do [ -n "$h" ] && ARGS+=(--add-host "$h"); done < <(docker inspect "$C" --format '{{range .HostConfig.ExtraHosts}}{{println .}}{{end}}')
while IFS= read -r e; do [ -n "$e" ] && ARGS+=(--env "$e"); done < <(docker inspect "$C" --format '{{range .Config.Env}}{{println .}}{{end}}')
while IFS= read -r l; do [ -n "$l" ] && ARGS+=(--label "$l"); done < <(docker inspect "$C" --format '{{range $k,$v := .Config.Labels}}{{$k}}={{$v}}{{println}}{{end}}')
while IFS= read -r b; do [ -n "$b" ] && ARGS+=(-v "$b"); done < <(docker inspect "$C" --format '{{range .HostConfig.Binds}}{{println .}}{{end}}')
# OpenShell's supervisor REQUIRES SYS_ADMIN+NET_ADMIN to build the agent's inner
# netns + relay proxy (= the agent's containment). We test-DROP the two the audit
# flagged as droppable — SYS_PTRACE (cross-user /proc policy checks) and SYSLOG
# (dmesg bypass-detection monitor) — plus ADD no-new-privileges (blocks setuid
# escalation). Conduct-test after; if the conduct or the relay's 403 enforcement
# breaks, roll back. apparmor stays unconfined (docker-default blocks the
# netns/mount ops SYS_ADMIN needs).
ARGS+=(--cap-add SYS_ADMIN --cap-add NET_ADMIN)
ARGS+=(--security-opt no-new-privileges)
ARGS+=(--entrypoint /opt/openshell/bin/openshell-sandbox)

# 3. Stop + rename the old container (rollback handle)
docker stop "$C" >/dev/null
docker rename "$C" "${C}-prehardened"
echo ">> old container preserved as ${C}-prehardened (stopped)"

# 4. Recreate hardened
docker run "${ARGS[@]}" "$IMG" >/dev/null
echo ">> recreated $C hardened"
sleep 3
docker inspect "$C" --format 'User={{.Config.User}} CapAdd={{.HostConfig.CapAdd}} CapDrop={{.HostConfig.CapDrop}} SecOpt={{.HostConfig.SecurityOpt}} Net={{.HostConfig.NetworkMode}}'
echo ">> NOTE: re-apply Step 1 egress firewall now (new netns): /root/filmo-sandbox/apply-egress-firewall.sh"
