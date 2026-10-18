#!/usr/bin/env bash
# Tests the supervisor's audio logic without real audio: pactl and Soloist
# are stubs. It writes to /data and /run, so run it in a throwaway container:
#   docker run --rm -v "$PWD:/repo:ro" debian:trixie \
#     bash -c 'apt-get update -qq && apt-get install -y -qq jq && /repo/tests/addon/watchdog.sh'
# Scenarios are called by name; EXTRA_ARGS is read by the sourced supervisor.
# Older ShellCheck reports indirectly called functions as SC2317, newer as SC2329.
# shellcheck disable=SC2317,SC2329,SC2034
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
supervisor="${here}/../../spotify_soloist/rootfs/usr/bin/soloist-supervisor"
failed=0

mkdir -p /data/bin
cat >/data/bin/soloist <<'FAKE'
#!/usr/bin/env bash
if [[ "${1:-}" == --version ]]; then
    echo "soloist 1.0 build 4102444800 (20990101) (gtest) (linux/x86_64)"
    exit 0
fi
while true; do
    echo "$(date '+%F %T.000'): ${FAKE_STATE:-playing} spotify:track:abc \"Title\" by \"Artist\" [0:00 / 3:02]"
    sleep 1
done
FAKE
chmod 755 /data/bin/soloist

vol='"volume":{"front-left":{"value":65536,"value_percent":"100%"},"front-right":{"value":65536,"value_percent":"100%"}}'
HDMI="{\"index\":0,\"name\":\"hdmi\",\"state\":\"SUSPENDED\",\"mute\":false,${vol},\"latency\":{\"actual\":0,\"configured\":0}}"
DAC="{\"index\":20,\"name\":\"dac\",\"monitor_source\":\"dac.monitor\",\"state\":\"RUNNING\",\"mute\":false,${vol},\"latency\":{\"actual\":1500,\"configured\":0}}"
STREAM="[{\"index\":7,\"sink\":20,\"corked\":false,\"mute\":false,\"sink_latency_usec\":1200,\"buffer_latency_usec\":34000,${vol},\"properties\":{\"application.process.binary\":\"soloist\"}}]"

# Fresh fixtures and a pactl stub for each scenario.
setup() {
    T="$(mktemp -d)"
    mkdir -p "${T}/bin"
    echo "[${HDMI},${DAC}]" >"${T}/sinks.json"
    echo "[]" >"${T}/inputs.json"
    cat >"${T}/bin/pactl" <<'STUB'
#!/usr/bin/env bash
if [[ "$1" == subscribe ]]; then exec sleep 30; fi
[[ -e "${T}/pactl_fail" ]] && exit 1
case "$*" in
    "-f json list sinks") cat "${T}/sinks.json" ;;
    "-f json list sink-inputs") cat "${T}/inputs.json" ;;
    "-f json info") echo '{"default_sink_name":"hdmi"}' ;;
    move-sink-input*) [[ -e "${T}/move_fail" ]] && exit 1; echo "$*" >>"${T}/moves"
        sed -i 's/"sink":0/"sink":20/' "${T}/inputs.json" ;;
esac
STUB
    chmod 755 "${T}/bin/pactl"
    # parec: one second of zeros, of non-zero bytes, or a failure ("mode").
    cat >"${T}/bin/parec" <<'STUB'
#!/usr/bin/env bash
echo "$*" >>"${T}/parec_args"
case "$(cat "${T}/parec_mode" 2>/dev/null)" in
    audio) head -c 176400 /dev/zero | tr '\0' 'x' ;;
    fail) exit 1 ;;
    *) head -c 176400 /dev/zero ;;
esac
STUB
    chmod 755 "${T}/bin/parec"
    export T PATH="${T}/bin:${PATH}"
    export SOLOIST_RUN_DIR="${T}/run" SOLOIST_WATCH_SECS=1 SOLOIST_POLL_SECS=1
    export SOLOIST_WARN_AFTER_SECS=2 SOLOIST_RESTART_AFTER_SECS=5 SOLOIST_COOLDOWN_SECS=600
    export SOLOIST_FOLLOWUP_SECS=2 SOLOIST_PERIODIC_SECS=4
    export SOLOIST_SOURCE_ONLY=1
    mkdir -p "${T}/run"
    exec 3>&1 >"${T}/log" 2>&1
    # shellcheck source=/dev/null
    source "${here}/bashio-stub.sh"
    EXTRA_ARGS=()
    # shellcheck source=/dev/null
    source "${supervisor}"
}

# Waits up to $2 s for $1 to appear in the log.
wait_log() {
    local i
    for ((i = 0; i < $2 * 10; i++)); do
        grep -q -- "$1" "${T}/log" && return 0
        sleep 0.1
    done
    return 1
}

count() { grep -c -- "$1" "${T}/log"; }

# Each scenario runs in a subshell; its exit status is the verdict.
run() {
    local name="$1" rc
    ( "$name" )
    rc=$?
    if ((rc == 0)); then
        echo "PASS ${name}"
    else
        echo "FAIL ${name}"
        failed=1
    fi
}

# Defined as shell functions so scenarios can share the log of the watcher.
finish() {
    local log
    log="$(cat "${T}/log")"
    kill "$(jobs -p)" 2>/dev/null
    stop_soloist
    # shellcheck disable=SC2001
    echo "${log}" | sed 's/^/    | /' >&3
}

scenario_warns_then_restarts_once() {
    setup
    start_soloist
    watch_audio dac &
    wait_log "no audio stream" 8 || { finish; return 1; }
    [[ ! -e "${RESTART_FLAG}" ]] || { finish; return 1; }
    wait_log "restarting it as a last resort" 10 || { finish; return 1; }
    [[ -e "${RESTART_FLAG}" ]] || { finish; return 1; }
    # No second warning or restart while the condition persists.
    rm -f "${RESTART_FLAG}"
    sleep 7
    [[ ! -e "${RESTART_FLAG}" ]] || { finish; return 1; }
    (($(count "reports playing but") == 1)) || { finish; return 1; }
    (($(count "last resort") == 1)) || { finish; return 1; }
    grep -q "Audio (no Soloist stream)" "${T}/log" || { finish; return 1; }
    ! grep -q "Audio (Soloist started playing)\|signal=" "${T}/log" || { finish; return 1; }
    stop_soloist
    kill "$(jobs -p)" 2>/dev/null
}

scenario_cooldown_blocks_second_restart() {
    setup
    start_soloist
    watch_audio dac &
    wait_log "last resort" 12 || { finish; return 1; }
    rm -f "${RESTART_FLAG}"
    # A stream appears and goes away again: re-armed, but still cooling down.
    echo "${STREAM}" >"${T}/inputs.json"
    sleep 3
    echo "[]" >"${T}/inputs.json"
    sleep 9
    [[ ! -e "${RESTART_FLAG}" ]] || { finish; return 1; }
    (($(count "reports playing but") == 2)) || { finish; return 1; }
    (($(count "last resort") == 1)) || { finish; return 1; }
    stop_soloist
    kill "$(jobs -p)" 2>/dev/null
}

scenario_no_action_when_pactl_fails() {
    setup
    touch "${T}/pactl_fail"
    start_soloist
    watch_audio dac &
    sleep 9
    ! grep -q "no audio stream" "${T}/log" || { finish; return 1; }
    [[ ! -e "${RESTART_FLAG}" ]] || { finish; return 1; }
    stop_soloist
    kill "$(jobs -p)" 2>/dev/null
}

scenario_no_action_when_stream_exists() {
    setup
    echo "${STREAM}" >"${T}/inputs.json"
    start_soloist
    watch_audio dac &
    sleep 9
    ! grep -q "no audio stream" "${T}/log" || { finish; return 1; }
    [[ ! -e "${RESTART_FLAG}" ]] || { finish; return 1; }
    stop_soloist
    kill "$(jobs -p)" 2>/dev/null
}

scenario_no_action_when_not_playing() {
    setup
    export FAKE_STATE=paused
    start_soloist
    watch_audio dac &
    sleep 9
    ! grep -q "no audio stream" "${T}/log" || { finish; return 1; }
    [[ ! -e "${RESTART_FLAG}" ]] || { finish; return 1; }
    stop_soloist
    kill "$(jobs -p)" 2>/dev/null
}

scenario_snapshot_on_playing() {
    export SOLOIST_VERBOSE=true
    setup
    echo "${STREAM}" >"${T}/inputs.json"
    start_soloist
    wait_log "Audio (Soloist started playing)" 5 || { finish; return 1; }
    sleep 1
    # Soloist's own line is passed through, and the snapshot has the details.
    grep -q ": playing spotify:track:abc" "${T}/log" || { finish; return 1; }
    grep -q "default sink hdmi" "${T}/log" || { finish; return 1; }
    grep -q "sink dac (#20) state=RUNNING mute=false volume=100% latency=1500us" "${T}/log" || { finish; return 1; }
    grep -q "Soloist stream #7 on dac corked=false mute=false volume=100%" "${T}/log" || { finish; return 1; }
    # Only once, not for every "playing" line.
    (($(count "Soloist started playing") == 1)) || { finish; return 1; }
    stop_soloist
}

scenario_output_appeared_and_disappeared() {
    setup
    echo "[${HDMI}]" >"${T}/sinks.json"
    watch_audio dac &
    sleep 2
    echo "[${HDMI},${DAC}]" >"${T}/sinks.json"
    wait_log "Output dac appeared" 5 || { finish; return 1; }
    echo "[${HDMI}]" >"${T}/sinks.json"
    wait_log "Output dac disappeared" 5 || { finish; return 1; }
    kill "$(jobs -p)" 2>/dev/null
}

scenario_move_failure_is_logged() {
    setup
    echo "${STREAM//\"sink\":20/\"sink\":0}" >"${T}/inputs.json"
    touch "${T}/move_fail"
    watch_audio dac &
    wait_log "\[WARN\] Could not move stream 7 to dac" 5 || { finish; return 1; }
    rm "${T}/move_fail"
    wait_log "Moved playback to dac" 5 || { finish; return 1; }
    kill "$(jobs -p)" 2>/dev/null
}

# Verbose scenarios set SOLOIST_VERBOSE before setup, which reads it on source.
scenario_verbose_off_adds_nothing() {
    export SOLOIST_VERBOSE=false
    setup
    echo "${STREAM//\"sink\":20/\"sink\":0}" >"${T}/inputs.json"
    echo audio >"${T}/parec_mode"
    echo "[${HDMI}]" >"${T}/sinks.json"
    start_soloist
    watch_audio dac &
    sleep 2
    echo "[${HDMI},${DAC}]" >"${T}/sinks.json"
    wait_log "Moved playback to dac" 5 || { finish; return 1; }
    wait_log "Output dac appeared" 5 || { finish; return 1; }
    sleep 4
    # Playing, an appearing output and a move log no snapshot without verbose.
    grep -q ": playing spotify:track:abc" "${T}/log" || { finish; return 1; }
    ! grep -q "Audio (\|signal=\|latency=[0-9]*us buffer" "${T}/log" || { finish; return 1; }
    [[ ! -e "${T}/parec_args" ]] || { finish; return 1; }
    stop_soloist
    kill "$(jobs -p)" 2>/dev/null
}

scenario_verbose_signal_and_latency() {
    export SOLOIST_VERBOSE=true
    setup
    echo "${STREAM}" >"${T}/inputs.json"
    echo audio >"${T}/parec_mode"
    log_audio_snapshot test
    grep -q "Soloist stream #7 on dac corked=false mute=false volume=100% sink_latency=1200us buffer_latency=34000us signal=audio$" "${T}/log" || { finish; return 1; }
    grep -q -- "-d dac.monitor" "${T}/parec_args" || { finish; return 1; }
    echo zeros >"${T}/parec_mode"
    log_audio_snapshot test
    grep -q "signal=silent$" "${T}/log" || { finish; return 1; }
    echo fail >"${T}/parec_mode"
    log_audio_snapshot test
    grep -q "signal=?$" "${T}/log" || { finish; return 1; }
    # A corked stream is not probed.
    echo "${STREAM//\"corked\":false/\"corked\":true}" >"${T}/inputs.json"
    : >"${T}/log"
    log_audio_snapshot test
    grep -q "corked=true" "${T}/log" || { finish; return 1; }
    ! grep -q "signal=" "${T}/log" || { finish; return 1; }
    finish
}

scenario_verbose_followup_and_periodic() {
    export SOLOIST_VERBOSE=true
    setup
    echo "${STREAM}" >"${T}/inputs.json"
    start_soloist
    watch_audio dac &
    wait_log "Audio (2 s after Soloist started playing)" 6 || { finish; return 1; }
    # The follow-up is logged once; periodic snapshots come while playing.
    wait_log "Audio (while playing)" 10 || { finish; return 1; }
    (($(count "s after Soloist started playing") == 1)) || { finish; return 1; }
    finish
}

scenario_verbose_no_periodic_when_paused() {
    export SOLOIST_VERBOSE=true
    setup
    export FAKE_STATE=paused
    echo "${STREAM}" >"${T}/inputs.json"
    start_soloist
    watch_audio dac &
    sleep 10
    ! grep -q "while playing\|s after" "${T}/log" || { finish; return 1; }
    stop_soloist
    kill "$(jobs -p)" 2>/dev/null
}

scenario_verbose_followup_after_move() {
    export SOLOIST_VERBOSE=true
    setup
    echo "${STREAM//\"sink\":20/\"sink\":0}" >"${T}/inputs.json"
    watch_audio dac &
    wait_log "Audio (2 s after move)" 8 || { finish; return 1; }
    finish
}

for s in $(declare -F | awk '$3 ~ /^scenario_/ { print $3 }'); do
    run "${s}"
done
exit "${failed}"
