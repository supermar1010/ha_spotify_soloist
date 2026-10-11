# shellcheck shell=bash
# Minimal stand-in for bashio, so the supervisor runs outside the Supervisor.
# Override options with environment variables, e.g. CHECK=0 HOUR=13.
declare -A CFG=(
    [device_name]="CI Smoke Test"
    [api_key]="not-a-real-key"
    [websocket_port]=9090
    [update_check_interval_hours]="${CHECK:-12}"
    [update_hour]="${HOUR:-4}"
    [reset_pairing]=false
    [verbose]=false
)
bashio::config() { echo "${CFG[$1]:-}"; }
bashio::config.has_value() { [[ -n "${CFG[$1]:-}" ]]; }
bashio::config.true() { [[ "${CFG[$1]:-}" == true ]]; }
bashio::log.info() { echo "[INFO] $*"; }
bashio::log.debug() { echo "[DEBUG] $*"; }
bashio::log.warning() { echo "[WARN] $*"; }
bashio::log.error() { echo "[ERROR] $*"; }
bashio::exit.nok() {
    echo "[FATAL] $*"
    exit 1
}
