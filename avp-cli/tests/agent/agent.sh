#!/bin/sh
# ping, describe, and a run that refuses every Commission:
# run --commission <path> --out <path>
event() {
  printf '{"avp_version": "0.1", "id": "%s", "time": "2026-01-01T00:00:00Z", "run_id": "sh-run", "type": "%s", "data": %s}\n' "$1" "$2" "$3"
}
case "$1" in
  ping) echo '{"type": "pong", "avp_version": "0.1"}' ;;
  describe) echo '{"avp_version": "0.1", "agent_name": "sh-agent", "agent_version": "1.0.0", "supported_models": [{"provider": "anthropic", "id": "*"}]}' ;;
  run)
    {
      event 1 run_requested "{\"commission\": $(cat "$3")}"
      event 2 error_occurred '{"error_code": "invalid_commission", "error_message": "sh-agent refuses every Commission"}'
    } > "$5"
    ;;
  *) exit 2 ;;
esac
