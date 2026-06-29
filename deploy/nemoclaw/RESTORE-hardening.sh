#!/usr/bin/env bash
# One-command rollback of the filmo sandbox hardening.
# Restores the container to its ORIGINAL (pre-hardening) posture.
# Safe to run repeatedly. Uses host nsenter so it works even after NET_ADMIN drop.
#
# Usage: /root/filmo-sandbox/RESTORE-hardening.sh [all|net|caps]
#   net  = remove the in-netns agent-egress firewall (Step 1) -> all-ACCEPT
#   caps = restore the ORIGINAL root+caps+apparmor container (Step 2/3)
#   all  = both (default)
set -u
MODE="${1:-all}"
C="$(docker ps --filter name=openshell-filmo --filter status=running --format '{{.Names}}' | grep -vE -- '-prehardened|-rollback|-hardened' | head -1)"
SNAP="$(ls -1dt /root/filmo-sandbox/hardening-snapshot-* 2>/dev/null | head -1)"
echo "container=$C  snapshot=$SNAP  mode=$MODE"
[ -z "$C" ] && { echo "FATAL: no filmo container found"; exit 1; }

restore_net() {
  echo ">> Step1 rollback: flush agent-egress firewall back to ACCEPT (via nsenter)"
  PID="$(docker inspect "$C" --format '{{.State.Pid}}' 2>/dev/null)"
  if [ -n "$PID" ] && [ "$PID" != "0" ]; then
    nsenter -t "$PID" -n iptables -F OUTPUT 2>/dev/null
    nsenter -t "$PID" -n iptables -F FILMO_AGENT 2>/dev/null
    nsenter -t "$PID" -n iptables -X FILMO_AGENT 2>/dev/null
    nsenter -t "$PID" -n iptables -F FILMO_EGRESS 2>/dev/null   # legacy chain name
    nsenter -t "$PID" -n iptables -X FILMO_EGRESS 2>/dev/null
    nsenter -t "$PID" -n iptables -P OUTPUT ACCEPT 2>/dev/null
    echo "   OUTPUT policy now: $(nsenter -t "$PID" -n iptables -S OUTPUT 2>/dev/null | head -1)"
  else
    echo "   (container not running; firewall is netns-scoped and already gone)"
  fi
  echo ">> Step1 rollback done (egress = all-ACCEPT)"
}

restore_caps() {
  echo ">> Step2/3 rollback: restore ORIGINAL container posture"
  PRE="$(docker ps -a --filter name=openshell-filmo --format '{{.Names}}' | grep -- '-prehardened' | head -1)"
  if [ -n "$PRE" ]; then
    echo "   found preserved original container: $PRE"
    docker stop "$C" 2>/dev/null && docker rename "$C" "${C}-hardened-rollback-$(date +%s)" 2>/dev/null
    docker rename "$PRE" "$C" 2>/dev/null
    docker start "$C" 2>/dev/null
    echo "   restored $C from $PRE; re-warming gateway"
  else
    echo "   no -prehardened container; recreating via gateway recover"
  fi
  /usr/bin/nemoclaw filmo recover || echo "   recover non-zero; see $SNAP/container-inspect.json"
  echo ">> Step2/3 rollback issued"
}

case "$MODE" in
  net)  restore_net ;;
  caps) restore_caps ;;
  all)  restore_net; restore_caps ;;
  *) echo "usage: $0 [all|net|caps]"; exit 2 ;;
esac
echo "RESTORE COMPLETE. Verify: docker inspect $C --format CapAdd={{.HostConfig.CapAdd}}; nemoclaw filmo exec -- echo ok"
