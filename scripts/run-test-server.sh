#!/usr/bin/env bash
# shadNet TEST instance — isolated development server (production untouched).
# Development only: separate DB/config on its own container + addresses.
#
#   seats / (expected) console -> 192.168.50.233:31313 (TCP) / :31314 (STUN) / :31315 (WebAPI)
#   BIG-PC host (tests)        -> 172.31.13.23:31313 / :31315   (bridge address)
#
# Usage: run-test-server.sh {start|stop|restart|status|logs}
set -euo pipefail

name="shadnet-test"
tree="/home/crow/Projects/ps4-bloodborne-crossplay/private/test-server"
net_macvlan="steam-headless_session-lan"
net_bridge="shadnet-test-host"
ip_macvlan="192.168.50.233"
ip_bridge="172.31.13.23"

case "${1:-status}" in
start)
    docker network inspect "$net_bridge" >/dev/null 2>&1 || \
        docker network create --subnet 172.31.13.0/24 "$net_bridge" >/dev/null
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker run -d --name "$name" --restart no --hostname "$name" \
        --network "$net_macvlan" --ip "$ip_macvlan" \
        -v /home/crow/shadnet/libs:/srv/libs:ro \
        -v "$tree:/srv" \
        --user 1000:1000 \
        --entrypoint /bin/bash josh5/steam-headless:2 \
        -c 'cd /srv && export LD_LIBRARY_PATH=/srv/libs-full:/srv/libs/usr/lib QT_PLUGIN_PATH=/srv/qtplugins QT_FORCE_STDERR_LOGGING=1 QT_ASSUME_STDERR_HAS_CONSOLE=1 && exec ./shadnet'
    docker network connect --ip "$ip_bridge" "$net_bridge" "$name" 2>/dev/null || true
    sleep 2
    docker ps --filter name="$name" --format '{{.Names}}  {{.Status}}  {{.Networks}}'
    ;;
stop)
    docker stop "$name" >/dev/null && echo "stopped"
    ;;
restart)
    "$0" stop
    "$0" start
    ;;
status)
    docker ps -a --filter name="$name" --format '{{.Names}}  {{.Status}}  {{.Networks}}'
    ;;
logs)
    docker logs --tail 60 "$name" 2>&1
    ;;
*)
    echo "usage: $0 {start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
