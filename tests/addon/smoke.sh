#!/usr/bin/env bash
# Starts the add-on image with a stubbed config and checks that the
# supervisor downloads Soloist and that Soloist opens its WebSocket API.
# Usage: tests/addon/smoke.sh <image>
set -euo pipefail

image="$1"
name="soloist-smoke-$$"
stub="$(cd "$(dirname "$0")" && pwd)/bashio-stub.sh"

# shellcheck disable=SC2064 # expand name now
trap "docker rm -f '${name}' >/dev/null 2>&1 || true" EXIT

# The s6 service is what starts the supervisor inside Home Assistant.
for f in run finish type; do
    docker run --rm --entrypoint test "${image}" -f "/etc/s6-overlay/s6-rc.d/soloist/${f}" ||
        { echo "Missing s6 service file: ${f}" >&2; exit 1; }
done
docker run --rm --entrypoint test "${image}" -x /etc/s6-overlay/s6-rc.d/soloist/run ||
    { echo "s6 run script is not executable" >&2; exit 1; }

docker run -d --name "${name}" -v "${stub}:/stub.sh:ro" --entrypoint bash "${image}" \
    -c 'source /stub.sh; source /usr/bin/soloist-supervisor' >/dev/null

for _ in $(seq 1 60); do
    if docker logs "${name}" 2>&1 | grep -q "websocket server listening on 127.0.0.1:9090"; then
        docker logs "${name}" 2>&1
        docker exec "${name}" /data/bin/soloist ctl status -D /data/state
        echo "Smoke test passed"
        exit 0
    fi
    sleep 5
done

docker logs "${name}" 2>&1
echo "Smoke test failed: Soloist did not open its WebSocket API" >&2
exit 1
