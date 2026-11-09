#!/bin/sh
# Minimal native ATIF agent that refuses every Commission.
DESCRIPTOR='{"avp_version": "0.1", "agent_name": "sh-agent", "agent_version": "1.0.0", "supported_models": [{"provider": "anthropic", "id": "*"}]}'
case "$1" in
  ping) echo '{"type": "pong", "avp_version": "0.1"}' ;;
  describe) echo "$DESCRIPTOR" ;;
  run)
    RUN_ID=$(sed -n 's/.*"run_id":[[:space:]]*"\([^" ]*\)".*/\1/p' "$3")
    printf '{"schema_version":"ATIF-v1.8","session_id":"%s","agent":{"name":"sh-agent","version":"1.0.0"},"steps":[{"step_id":1,"source":"system","message":"sh-agent refuses every Commission","extra":{"avp":{"error_code":"invalid_commission"}}}],"extra":{"avp":{"complete":true,"stop_reason":"refused"}}}\n' "$RUN_ID" > "$5"
    ;;
  *) exit 2 ;;
esac
