#!/bin/sh
case "$1" in
  ping) echo '{"type": "pong", "avp_version": "0.1"}' ;;
  describe) echo '{"avp_version": "0.1", "agent_name": "sh-agent", "agent_version": "1.0.0", "supported_models": [{"provider": "anthropic", "id": "*"}]}' ;;
  *) exit 2 ;;
esac
