import { eventDefinition, parseDefinition } from "./validation.js";
import type {
  AgentStopped,
  AssistantMessage,
  ErrorOccurred,
  Event,
  Usage,
} from "./wire.js";
export type {
  AgentDescribed,
  AgentDescribedEvent,
  AgentStarted,
  AgentStartedEvent,
  AgentStopped,
  AgentStoppedEvent,
  AssistantMessage,
  AssistantMessageEvent,
  Citation,
  ErrorOccurred,
  ErrorOccurredEvent,
  Event,
  ImageBlock,
  JsonValue,
  RefusalBlock,
  RunRequested,
  RunRequestedEvent,
  ServerToolResultBlock,
  ServerToolUseBlock,
  Source,
  SubagentInvoked,
  SubagentInvokedEvent,
  SubagentReturned,
  SubagentReturnedEvent,
  SubagentUsage,
  TextBlock,
  ThinkingBlock,
  ToolInvoked,
  ToolInvokedEvent,
  ToolResultBlock,
  ToolReturned,
  ToolReturnedEvent,
  ToolUseBlock,
  Usage,
} from "./wire.js";
export type ContentBlock = AssistantMessage["content"][number];
export type StopReason = AgentStopped["reason"];
export type CostSource = Usage["cost_source"];
export type ErrorCode = ErrorOccurred["error_code"];
export type EventSink = (event: Event) => Promise<void>;

export function parseTrajectoryEvent(received: unknown): Event | undefined {
  const value =
    typeof received === "string"
      ? JSON.parse(received)
      : received instanceof Uint8Array
        ? JSON.parse(Buffer.from(received).toString("utf8"))
        : received;
  if (!value || typeof value !== "object" || typeof value.type !== "string")
    throw new TypeError("event has no string type");
  const name = eventDefinition(value.type);
  return name ? parseDefinition<Event>(name, value) : undefined;
}
