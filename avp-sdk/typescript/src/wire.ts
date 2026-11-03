// Generated from spec/v0.1/trajectory.schema.json. Do not edit.

/**
 * One CloudEvents 1.0 event of the trajectory an agent emits. See trajectory.md.
 */
export type Event =
  | RunRequestedEvent
  | AgentDescribedEvent
  | AgentStartedEvent
  | AssistantMessageEvent
  | ToolInvokedEvent
  | ToolReturnedEvent
  | SubagentInvokedEvent
  | SubagentReturnedEvent
  | ErrorOccurredEvent
  | AgentStoppedEvent;
export type JsonValue = unknown;

export interface RunRequestedEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "run_requested";
  data: RunRequested;
}
export interface RunRequested {
  commission?: unknown;
}
export interface AgentDescribedEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "agent_described";
  data: AgentDescribed;
}
export interface AgentDescribed {
  descriptor: AgentDescriptor;
}
/**
 * What an agent comes with before any Commission.
 */
export interface AgentDescriptor {
  /**
   * The AVP version the Descriptor follows.
   */
  avp_version: "0.1";
  /**
   * The agent's name.
   */
  agent_name: string;
  /**
   * The agent's version.
   */
  agent_version: string;
  /**
   * The models the agent can run. Absent means the agent does not say.
   */
  supported_models?: ModelPattern[] | null;
  /**
   * The system prompt the agent comes with.
   */
  system_prompt?: string | null;
  /**
   * The agent's built-in tools, including those that come from its MCP servers.
   */
  tools?: Tool[] | null;
  /**
   * The MCP servers the agent comes with.
   */
  mcp_servers?: McpServer[] | null;
  /**
   * The skills the agent comes with.
   */
  skills?: DescriptorSkill[] | null;
  /**
   * The subagents the agent comes with.
   */
  subagents?: Subagent[] | null;
}
/**
 * Matches the `provider` and `id` of a Commission's Model. `*` matches any characters.
 */
export interface ModelPattern {
  /**
   * A pattern for the model's `provider`, for example `"anthropic"`.
   */
  provider: string;
  /**
   * A pattern for the model's `id`, for example `"claude-*"`.
   */
  id: string;
}
/**
 * An MCP `Tool` object, with one added field. Other MCP fields are kept.
 */
export interface Tool {
  /**
   * The tool's name, as the model calls it.
   */
  name: string;
  /**
   * A display name.
   */
  title?: string | null;
  /**
   * What the tool does, as the model sees it.
   */
  description?: string | null;
  /**
   * A JSON Schema for the tool's input, as the model sees it.
   */
  inputSchema: {
    type: "object";
    [k: string]: unknown;
  };
  /**
   * A JSON Schema for the tool's structured output.
   */
  outputSchema?: {
    type: "object";
    [k: string]: unknown;
  } | null;
  /**
   * The `id` of the MCP server the tool comes from. Absent for any tool that
   * does not come from an MCP server.
   */
  mcp_server_id?: string | null;
  [k: string]: unknown;
}
/**
 * An MCP server the agent comes with. Connection details stay inside the agent.
 */
export interface McpServer {
  /**
   * Identifies the server. A Tool's `mcp_server_id` refers to it.
   */
  id: string;
  /**
   * A display name, when it differs from `id`.
   */
  name?: string | null;
  /**
   * What the server provides.
   */
  description?: string | null;
  /**
   * The result of the agent's attempt to connect.
   */
  status?: ("connected" | "failed" | "needs-auth" | "disabled") | null;
}
/**
 * The frontmatter of a skill's `SKILL.md`, as defined by Agent Skills, with
 * one added field. Other frontmatter fields are kept.
 */
export interface DescriptorSkill {
  /**
   * The skill's name.
   */
  name: string;
  /**
   * What the skill does and when to use it.
   */
  description: string;
  /**
   * A `file:` URI for the directory that contains the skill's `SKILL.md`, as
   * the path appears inside the agent's environment.
   */
  source?: string | null;
  [k: string]: unknown;
}
/**
 * A subagent that ships with the agent. It does not inherit the agent's items.
 */
export interface Subagent {
  /**
   * Identifies the subagent.
   */
  name: string;
  /**
   * What the subagent does.
   */
  description?: string | null;
  /**
   * The subagent's system prompt.
   */
  system_prompt?: string | null;
  /**
   * The subagent's tools.
   */
  tools?: Tool[] | null;
  /**
   * The subagent's MCP servers.
   */
  mcp_servers?: McpServer[] | null;
  /**
   * The subagent's skills.
   */
  skills?: DescriptorSkill[] | null;
}
export interface AgentStartedEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "agent_started";
  data: AgentStarted;
}
export interface AgentStarted {
  /**
   * The prompt the run starts with.
   */
  prompt: string;
  /**
   * The system prompt the run uses.
   */
  system_prompt?: string | null;
  model: ModelRef;
  /**
   * The tools the run uses.
   */
  tools?: Tool[] | null;
  /**
   * The MCP servers the run uses.
   */
  mcp_servers?: McpServer[] | null;
  /**
   * The skills the run uses.
   */
  skills?: DescriptorSkill[] | null;
  /**
   * The subagents the run uses.
   */
  subagents?: Subagent[] | null;
}
/**
 * A Model without its `credential`, as the Trajectory reports it.
 */
export interface ModelRef {
  /**
   * The service that runs the model, for example `"anthropic"`,
   * `"amazon-bedrock"`, or `"openrouter"`. It decides which API the agent calls
   * and how it authenticates.
   */
  provider: string;
  /**
   * The model's ID at that service, as the agent sends it, for example
   * `"claude-sonnet-4-6"`.
   */
  id: string;
  /**
   * The URL of the service's API. Absent means the service's default.
   */
  base_url?: string | null;
}
export interface AssistantMessageEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "assistant_message";
  data: AssistantMessage;
}
export interface AssistantMessage {
  /**
   * What the model produced: text, reasoning, tool calls, and other blocks.
   */
  content: (
    | TextBlock
    | ThinkingBlock
    | ImageBlock
    | ToolUseBlock
    | ToolResultBlock
    | ServerToolUseBlock
    | ServerToolResultBlock
    | RefusalBlock
  )[];
  model: ModelRef;
  /**
   * The model ID the service says produced the response, when it differs from `model.id`.
   */
  response_model?: string | null;
  /**
   * Why the model stopped, exactly as the service reported it.
   */
  finish_reasons?: string[] | null;
  /**
   * How long the response took, ending at the event's `time`.
   */
  duration_ms: number;
  usage: Usage;
  /**
   * When a subagent made the response, the `invocation_id` of its `subagent_invoked`.
   */
  subagent_invocation_id?: string | null;
}
/**
 * Text from the model.
 */
export interface TextBlock {
  type: "text";
  text: string;
  citations?: Citation[] | null;
  [k: string]: unknown;
}
/**
 * A source the model cited for a text block. Keeps fields the service added.
 */
export interface Citation {
  /**
   * The kind of citation, as the model service names it, such as `url_citation`.
   */
  type: string;
  /**
   * The text cited.
   */
  cited_text?: string | null;
  /**
   * Where the cited part of the block's `text` starts.
   */
  start_index?: number | null;
  /**
   * Where it ends.
   */
  end_index?: number | null;
  /**
   * The service's ID for the source.
   */
  source_id?: string | null;
  /**
   * The source's URL.
   */
  source_url?: string | null;
  /**
   * The source's title.
   */
  source_title?: string | null;
  [k: string]: unknown;
}
/**
 * The model's reasoning.
 */
export interface ThinkingBlock {
  type: "thinking";
  /**
   * The reasoning, or the service's encrypted reasoning when `redacted` is true.
   */
  thinking: string;
  /**
   * The service's token for passing the reasoning back to it.
   */
  signature?: string | null;
  redacted?: boolean | null;
  [k: string]: unknown;
}
/**
 * An image.
 */
export interface ImageBlock {
  type: "image";
  source: Source;
  [k: string]: unknown;
}
/**
 * Where an image's data is. In v0.1 the data is always inline. Keeps fields the service added.
 */
export interface Source {
  type: "base64";
  /**
   * The image's media type, such as `image/png`.
   */
  media_type: string;
  /**
   * The image, base64-encoded.
   */
  data: string;
  [k: string]: unknown;
}
/**
 * A call to a tool the agent runs.
 */
export interface ToolUseBlock {
  type: "tool_use";
  id: string;
  name: string;
  input: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
/**
 * The result of a `tool_use` call, matched by `tool_use_id`.
 */
export interface ToolResultBlock {
  type: "tool_result";
  tool_use_id: string;
  content: string | (TextBlock | ImageBlock)[];
  /**
   * A result meant for programs, such as MCP's `structuredContent`.
   */
  structured_content?: {
    [k: string]: unknown;
  } | null;
  is_error?: boolean | null;
  [k: string]: unknown;
}
/**
 * A call to a tool the model service runs itself, such as web search.
 */
export interface ServerToolUseBlock {
  type: "server_tool_use";
  id: string;
  name: string;
  input: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
/**
 * The result of a `server_tool_use` call.
 */
export interface ServerToolResultBlock {
  type: "server_tool_result";
  tool_use_id: string;
  name: string;
  content: unknown;
  is_error?: boolean | null;
  [k: string]: unknown;
}
/**
 * The model's text when it declined.
 */
export interface RefusalBlock {
  type: "refusal";
  refusal: string;
  [k: string]: unknown;
}
/**
 * Token counts and cost for one model response.
 */
export interface Usage {
  /**
   * All input tokens, including those read from and written to the cache.
   */
  input_tokens: number;
  /**
   * All output tokens, including reasoning tokens.
   */
  output_tokens: number;
  /**
   * The input tokens read from the cache. Included in `input_tokens`.
   */
  cache_read_input_tokens?: number | null;
  /**
   * The input tokens written to the cache. Included in `input_tokens`.
   */
  cache_creation_input_tokens?: number | null;
  /**
   * The output tokens the model spent on reasoning. Included in `output_tokens`.
   */
  reasoning_output_tokens?: number | null;
  /**
   * The cost in US dollars, after any cache discount.
   */
  cost_usd: number;
  /**
   * Where `cost_usd` comes from.
   */
  cost_source: "computed" | "reported" | "unknown";
}
export interface ToolInvokedEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "tool_invoked";
  data: ToolInvoked;
}
export interface ToolInvoked {
  /**
   * Identifies the call: the `id` of its `tool_use` content block.
   */
  tool_call_id: string;
  /**
   * The name the agent called the tool by.
   */
  tool_name: string;
  /**
   * The arguments, as in the `tool_use` block's `input`.
   */
  tool_input: {
    [k: string]: unknown;
  };
  /**
   * The `id` of the MCP server that runs the tool.
   */
  mcp_server_id?: string | null;
  /**
   * When a subagent made the call, the `invocation_id` of its `subagent_invoked`.
   */
  subagent_invocation_id?: string | null;
}
export interface ToolReturnedEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "tool_returned";
  data: ToolReturned;
}
export interface ToolReturned {
  /**
   * As in the matching `tool_invoked`.
   */
  tool_call_id: string;
  /**
   * As in the matching `tool_invoked`.
   */
  tool_name: string;
  /**
   * How long the tool took, ending at the event's `time`.
   */
  duration_ms: number;
  tool_result: ToolResultBlock;
  /**
   * As in the matching `tool_invoked`.
   */
  subagent_invocation_id?: string | null;
}
export interface SubagentInvokedEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "subagent_invoked";
  data: SubagentInvoked;
}
export interface SubagentInvoked {
  /**
   * The subagent's `name`, as in `agent_started`'s `subagents`.
   */
  subagent_name: string;
  /**
   * Identifies this run of the subagent. When a tool call started it, the call's `tool_call_id`.
   */
  invocation_id: string;
  /**
   * When another subagent started this one, the `invocation_id` of its `subagent_invoked`.
   */
  subagent_invocation_id?: string | null;
  /**
   * The input the subagent was given.
   */
  subagent_input: {
    [k: string]: unknown;
  };
}
export interface SubagentReturnedEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "subagent_returned";
  data: SubagentReturned;
}
export interface SubagentReturned {
  /**
   * As in the matching `subagent_invoked`.
   */
  subagent_name: string;
  /**
   * As in the matching `subagent_invoked`.
   */
  invocation_id: string;
  /**
   * As in the matching `subagent_invoked`.
   */
  subagent_invocation_id?: string | null;
  /**
   * How long the subagent ran, ending at the event's `time`.
   */
  duration_ms: number;
  /**
   * Why the subagent stopped.
   */
  subagent_reason:
    "converged" | "refused" | "error" | "interrupted" | "abandoned";
  /**
   * The subagent's final text, or the error message when `subagent_reason` is `error`.
   */
  subagent_result_text: string;
  /**
   * The subagent's totals, when the agent can't record its responses as events of their own.
   */
  subagent_usage?: SubagentUsage | null;
}
/**
 * A subagent's totals. A field is absent when the agent couldn't measure it.
 */
export interface SubagentUsage {
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_input_tokens?: number | null;
  cache_creation_input_tokens?: number | null;
  reasoning_output_tokens?: number | null;
  cost_usd?: number | null;
  cost_source?: ("computed" | "reported" | "unknown") | null;
  /**
   * How many model responses the subagent made.
   */
  responses?: number | null;
}
export interface ErrorOccurredEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "error_occurred";
  data: ErrorOccurred;
}
export interface ErrorOccurred {
  /**
   * What kind of error. A code this version doesn't know reads as `unknown`.
   */
  error_code:
    | "invalid_commission"
    | "mcp_connect_failed"
    | "auth_error"
    | "rate_limit"
    | "context_limit"
    | "output_invalid"
    | "agent_crash"
    | "unknown";
  /**
   * What went wrong, for a person to read.
   */
  error_message: string;
  /**
   * When the error happened in a subagent, the `invocation_id` of its `subagent_invoked`.
   */
  subagent_invocation_id?: string | null;
}
export interface AgentStoppedEvent {
  /**
   * The AVP version the event follows.
   */
  avp_version: "0.1";
  /**
   * Identifies the event.
   */
  id: string;
  /**
   * When the event happened, as an RFC 3339 timestamp.
   */
  time: string;
  /**
   * The run's ID, the same on every event of the run.
   */
  run_id: string;
  /**
   * The agent's own annotations. AVP gives them no meaning.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
  type: "agent_stopped";
  data: AgentStopped;
}
export interface AgentStopped {
  /**
   * Why the run stopped.
   */
  reason: "converged" | "refused" | "error" | "interrupted" | "abandoned";
  output?: unknown;
}
/**
 * Settings for the agent whose `agent_name` is their key in `agents`.
 *
 */
export interface AgentSettings {
  /**
   * The `agent_version` the Commission was written for.
   */
  version?: string | null;
  /**
   * The built-in tools the run may use, by name. Covers only tools without an
   * `mcp_server_id`.
   */
  enabled_tools?: string[] | null;
  /**
   * The built-in subagents the run may use, by name.
   */
  enabled_subagents?: string[] | null;
  /**
   * The built-in skills the run may use, by name.
   */
  enabled_skills?: string[] | null;
  /**
   * The built-in MCP servers the run may use, by `id`.
   */
  enabled_mcp_servers?: string[] | null;
}
/**
 * What one run should do: the task and the settings for the run.
 */
export interface Commission {
  /**
   * The AVP version the Commission follows.
   */
  avp_version: "0.1";
  /**
   * The run's ID, chosen by the supervisor.
   */
  run_id: string;
  model: Model;
  /**
   * The system prompt for the run. It replaces the agent's own.
   */
  system_prompt?: string | null;
  /**
   * The first user message of the run.
   */
  prompt: string;
  /**
   * The supervisor that wrote the Commission.
   */
  supervisor?: Supervisor | null;
  /**
   * MCP servers to add for the run.
   */
  mcp_servers?: (McpServerHttp | McpServerStdio)[] | null;
  /**
   * Skills to add for the run.
   */
  skills?: CommissionSkill[] | null;
  /**
   * Settings for specific agents, keyed by `agent_name`.
   */
  agents?: {
    [k: string]: AgentSettings;
  } | null;
  /**
   * A JSON Schema for the agent's final output. Its `type` is `"object"`.
   */
  output_schema?: {
    type: "object";
    [k: string]: unknown;
  } | null;
  /**
   * An ID that groups related runs, such as the turns of one conversation.
   */
  thread_id?: string | null;
  /**
   * Labels for the run.
   */
  tags?: string[] | null;
  /**
   * Key-value data for the supervisor's own use.
   */
  meta?: {
    [k: string]: unknown;
  } | null;
}
/**
 * A model as one service offers it, named with models.dev provider and model IDs.
 */
export interface Model {
  /**
   * The service that runs the model, for example `"anthropic"`,
   * `"amazon-bedrock"`, or `"openrouter"`. It decides which API the agent calls
   * and how it authenticates.
   */
  provider: string;
  /**
   * The model's ID at that service, as the agent sends it, for example
   * `"claude-sonnet-4-6"`.
   */
  id: string;
  /**
   * The URL of the service's API. Absent means the service's default.
   */
  base_url?: string | null;
  /**
   * The API key for the service. Absent means the agent uses whatever
   * credential its environment has for the service. A `proxy` credential is the
   * key alone; the proxy adds it as `provider`'s API expects.
   */
  credential?: ProxySecret | EnvSecret | null;
}
/**
 * A secret that a proxy outside the agent holds and adds to its requests.
 */
export interface ProxySecret {
  /**
   * The name of a credential that a proxy outside the agent holds. The proxy
   * adds it to the agent's matching requests, so the agent never receives its
   * value.
   */
  proxy: string;
}
/**
 * A secret in a variable of the agent's environment.
 */
export interface EnvSecret {
  /**
   * The name of a variable in the agent's environment that holds the secret,
   * for example `"TEST_DB_PASSWORD"`.
   */
  env: string;
}
/**
 * The supervisor that wrote the Commission.
 */
export interface Supervisor {
  /**
   * The supervisor's name, for example `"avp-cli"`.
   */
  name: string;
  /**
   * The supervisor's version.
   */
  version?: string | null;
}
/**
 * An MCP server the agent connects to over Streamable HTTP.
 */
export interface McpServerHttp {
  /**
   * Identifies the server.
   */
  id: string;
  /**
   * A display name, when it differs from `id`.
   */
  name?: string | null;
  /**
   * What the server provides.
   */
  description?: string | null;
  type: "http";
  /**
   * The server's URL.
   */
  url: string;
  /**
   * HTTP headers to send with each request. A Secret reference's secret is
   * the header's entire value.
   */
  headers?: {
    [k: string]: string | ProxySecret | EnvSecret;
  } | null;
}
/**
 * An MCP server the agent starts as a local program and talks to over stdio.
 */
export interface McpServerStdio {
  /**
   * Identifies the server.
   */
  id: string;
  /**
   * A display name, when it differs from `id`.
   */
  name?: string | null;
  /**
   * What the server provides.
   */
  description?: string | null;
  type: "stdio";
  /**
   * The program and its arguments, for example `["npx", "-y", "@example/db-mcp"]`.
   *
   * @minItems 1
   */
  command: [string, ...string[]];
  /**
   * Environment variables to set for the program, on top of those the
   * agent's MCP client gives it.
   */
  env?: {
    [k: string]: string | EnvSecret;
  } | null;
}
/**
 * A skill directory, as defined by Agent Skills, carried in the Commission.
 */
export interface CommissionSkill {
  /**
   * The skill's name. Equals the `name` in the frontmatter of its `SKILL.md`.
   */
  name: string;
  /**
   * The skill's files: each key is a path relative to the skill directory,
   * and each value is the file's UTF-8 content. Includes `"SKILL.md"`.
   */
  files: {
    [k: string]: string;
  };
}
