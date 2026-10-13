/**
 * Trace, span, and event identifiers for the CloudEvents envelope.
 *
 * Mirrors `avp.envelope` (Python) and `avp::ids` (Rust): W3C trace-context
 * lowercase hex for `trace_id` (32) and `span_id` (16), a UUID for the
 * CloudEvents `id`.
 */
import { randomBytes, randomUUID } from "node:crypto";

/** `parent_span_id` of a root span. */
export const ZERO_SPAN_ID = "0000000000000000";

/** CloudEvents `source` of every agent-emitted event. */
export const SOURCE_AGENT = "avp://agent";

function nonZeroHex(bytes: number): string {
  for (;;) {
    const hex = randomBytes(bytes).toString("hex");
    if (/[^0]/.test(hex)) return hex;
  }
}

export function newTraceId(): string {
  return nonZeroHex(16);
}

export function newSpanId(): string {
  return nonZeroHex(8);
}

export function newEventId(): string {
  return randomUUID();
}

/** Current UTC time, RFC 3339 with a `Z` suffix. */
export function nowIso(): string {
  return new Date().toISOString();
}
