#!/usr/bin/env python3
"""Dependency-free stdio MCP fixture: initialize, ping, list tools, and call tools.

`Avptest_Fail` fails the two ways an MCP tool can: a result flagged `isError`
(`mode: "result"`), or a JSON-RPC error (`mode: "protocol"`). Either way the
message is the given text, so a case can find it in the recorded result.

This deliberately implements only the subset used by AVP's integration tests.
Run directly with Python; no package installation, network, or persistent state.
The real SDK clients in the adapter tests validate interoperability.
"""

import json
import sys

VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
TOOLS = [
    {
        "name": "Avptest_Echo",
        "description": "Echo the given text unchanged.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "Avptest_Add",
        "description": "Return the sum of two integers.",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    },
    {
        "name": "Avptest_Fail",
        "description": "Fail with the given message: as a tool error result (mode "
        "'result') or as a protocol error (mode 'protocol').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "mode": {"type": "string", "enum": ["result", "protocol"]},
            },
            "required": ["message", "mode"],
            "additionalProperties": False,
        },
    },
]


def error(code, message):
    return {"error": {"code": code, "message": message}}


def respond(method, params):
    if method == "initialize":
        requested = params.get("protocolVersion")
        return {
            "result": {
                "protocolVersion": requested if requested in VERSIONS else VERSIONS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "avptest", "version": "0.1.0"},
            }
        }
    if method == "ping":
        return {"result": {}}
    if method == "tools/list":
        return {"result": {"tools": TOOLS}}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        if not isinstance(args, dict):
            return error(-32602, "arguments must be an object")
        if name == "Avptest_Echo" and set(args) == {"text"} and isinstance(args["text"], str):
            text = args["text"]
        elif (
            name == "Avptest_Add"
            and set(args) == {"a", "b"}
            and all(type(v) is int for v in args.values())
        ):
            # Not bare JSON: Gemini CLI parses a JSON text result into
            # `structuredContent`, which must be an object, and fails the call.
            text = f"sum: {args['a'] + args['b']}"
        elif (
            name == "Avptest_Fail"
            and set(args) == {"message", "mode"}
            and isinstance(args["message"], str)
            and args["mode"] in ("result", "protocol")
        ):
            if args["mode"] == "protocol":
                return error(-32000, args["message"])
            return {
                "result": {"content": [{"type": "text", "text": args["message"]}], "isError": True}
            }
        else:
            return error(-32602, "Unknown tool or invalid arguments")
        return {"result": {"content": [{"type": "text", "text": text}], "isError": False}}
    return error(-32601, "Method not found")


def main():
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = {"id": None, **error(-32700, "Parse error")}
        else:
            if (
                not isinstance(request, dict)
                or request.get("jsonrpc") != "2.0"
                or not isinstance(request.get("method"), str)
            ):
                response = {"id": None, **error(-32600, "Invalid request")}
            elif "id" not in request:
                continue  # Initialized/cancelled notifications have no response.
            else:
                params = request.get("params", {})
                result = (
                    respond(request["method"], params)
                    if isinstance(params, dict)
                    else error(-32602, "params must be an object")
                )
                response = {"id": request["id"], **result}
        print(json.dumps({"jsonrpc": "2.0", **response}), flush=True)


if __name__ == "__main__":
    main()
