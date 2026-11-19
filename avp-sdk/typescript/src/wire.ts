// Generated from Python SDK models. Do not edit.

export type JsonValue = unknown;

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
 * A tool call. `server_side` when the model service runs the tool and
 * returns its result in the same response, as a `ServerResult`.
 */
export interface Call {
  type?: "call";
  id: string;
  name: string;
  arguments: {
    [k: string]: unknown;
  };
  server_side?: boolean;
}
/**
 * A source the model cited. Keeps fields the service added.
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
   * Where the cited part of the text starts.
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
/**
 * An image saved beside the Trajectory. Made by `Recorder.image`.
 */
export interface Image {
  type?: "image";
  path: string;
  media_type: "image/png" | "image/jpeg" | "image/gif" | "image/webp";
}
/**
 * A block of the model's reasoning: readable `text`, or `encrypted_content`
 * when the service returned it encrypted.
 */
export interface Reasoning {
  type?: "reasoning";
  text?: string;
  signature?: string | null;
  encrypted_content?: string | null;
}
/**
 * The result of a server-side `Call`, from the same response.
 */
export interface ServerResult {
  type?: "server_result";
  call_id: string;
  content: string | (Text | Image)[];
  is_error?: boolean;
  structured_content?: unknown;
}
/**
 * Text from the model or a tool.
 */
export interface Text {
  type?: "text";
  text: string;
  citations?: Citation[] | null;
  refusal?: boolean;
}
/**
 * One model response's usage. `prompt_tokens` includes cached and
 * cache-creation tokens; `completion_tokens` includes reasoning tokens.
 * Without `cost_usd`, the Recorder prices the response.
 */
export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens?: number | null;
  cache_creation_input_tokens?: number | null;
  reasoning_output_tokens?: number | null;
  cost_usd?: number | null;
}
export interface RecorderInputs {
  commission: Commission;
  descriptor: AgentDescriptor;
  usage: Usage;
  parts: (Text | Image | Reasoning | Call | ServerResult)[];
  stop_reason: "converged" | "refused" | "error" | "interrupted" | "abandoned";
  error_code:
    | "invalid_commission"
    | "mcp_connect_failed"
    | "auth_error"
    | "rate_limit"
    | "context_limit"
    | "output_invalid"
    | "agent_crash"
    | "unknown";
  [k: string]: unknown;
}
/**
 * Agent configuration.
 */
export interface Agent {
  /**
   * The name of the agent system
   */
  name: string;
  /**
   * The version identifier of the agent system
   */
  version: string;
  /**
   * Default LLM model used for this trajectory
   */
  model_name?: string | null;
  /**
   * Array of tool/function definitions available to the agent. Each element follows OpenAI's function calling schema.
   */
  tool_definitions?:
    | {
        [k: string]: unknown;
      }[]
    | null;
  /**
   * Custom agent configuration details
   */
  extra?: AgentExtra | null;
}
export interface AgentExtra {
  avp?: AgentAvpExtra | null;
  [k: string]: unknown;
}
/**
 * At `agent.extra.avp`: what the run used.
 */
export interface AgentAvpExtra {
  /**
   * The agent's Descriptor, unchanged. Absent on subagent trajectories.
   */
  descriptor?: AgentDescriptor | null;
  /**
   * The service that runs the model in `agent.model_name`.
   */
  model?: AgentModel | null;
  /**
   * For each tool in `agent.tool_definitions`, keyed by its name.
   */
  tools?: {
    [k: string]: AgentTool;
  } | null;
  /**
   * The MCP servers the run used, with their `status`.
   */
  mcp_servers?: McpServer[] | null;
  /**
   * The skills the run used. `source` points to the saved skill directory.
   */
  skills?: DescriptorSkill[] | null;
  /**
   * The subagents available to the run.
   */
  subagents?: Subagent[] | null;
  [k: string]: unknown;
}
/**
 * The service that runs the model in `agent.model_name`.
 */
export interface AgentModel {
  /**
   * The service that runs the model.
   */
  provider: string;
  /**
   * The URL of the service's API. Absent means the service's default.
   */
  base_url?: string | null;
  [k: string]: unknown;
}
/**
 * The Tool fields that ATIF's OpenAI-style tool definition can't hold.
 */
export interface AgentTool {
  /**
   * The tool's display name.
   */
  title?: string | null;
  /**
   * The shape of the tool's structured result.
   */
  outputSchema?: {
    type: "object";
    [k: string]: unknown;
  } | null;
  /**
   * The tool's MCP annotations.
   */
  annotations?: {
    [k: string]: unknown;
  } | null;
  /**
   * The `id` of the MCP server in `mcp_servers` the tool comes from.
   */
  mcp_server_id?: string | null;
  [k: string]: unknown;
}
/**
 * Audio source specification for audio stored as files or at remote URLs.
 *
 * Added in ATIF-v1.8. Mirrors ``ImageSource`` so that consumers can treat any
 * referenced media the same way, with one addition: ``duration_sec``. Duration
 * is worth recording because several providers bill audio per second and
 * dataset statistics need it, and unlike an image's dimensions it cannot be
 * recovered without decoding the file.
 */
export interface AudioSource {
  /**
   * MIME type of the audio
   */
  media_type:
    | "audio/wav"
    | "audio/mpeg"
    | "audio/mp4"
    | "audio/aac"
    | "audio/ogg"
    | "audio/flac"
    | "audio/webm"
    | "audio/aiff";
  /**
   * Location of the audio. Can be a relative or absolute file path, or a URL.
   */
  path: string;
  /**
   * Optional duration of the audio in seconds. Useful for cost accounting and dataset statistics; omit when unknown.
   */
  duration_sec?: number | null;
}
/**
 * Data for one part of a step's `message` or a result's `content`.
 */
export interface ContentMetadata {
  /**
   * The position of the part in `message` or `content`, from 0. `0` when the value is a string.
   */
  part_index: number;
  /**
   * Sources the model cited in the part.
   */
  citations?: Citation[] | null;
  /**
   * `true` when the part is the model's text declining the task.
   */
  refusal?: boolean | null;
  [k: string]: unknown;
}
/**
 * A single content part within a multimodal message.
 *
 * Used when a message or observation contains mixed content types (text,
 * images, or audio). For text-only content, a plain string can still be used
 * instead of a ContentPart array.
 */
export interface ContentPart {
  /**
   * The type of content
   */
  type: "text" | "image" | "audio";
  /**
   * Text content. Required when type='text'.
   */
  text?: string | null;
  /**
   * Media source (file reference). Required when type='image' or type='audio', and must match that type.
   */
  source?: ImageSource | AudioSource | null;
}
/**
 * Image source specification for images stored as files or at remote URLs.
 */
export interface ImageSource {
  /**
   * MIME type of the image
   */
  media_type: "image/jpeg" | "image/png" | "image/gif" | "image/webp";
  /**
   * Location of the image. Can be a relative or absolute file path, or a URL.
   */
  path: string;
}
/**
 * An ATIF `extra` object. Keeps keys beside `avp`, and reads like a dict.
 */
export interface Extra {
  [k: string]: unknown;
}
/**
 * Aggregate statistics for the entire trajectory.
 */
export interface FinalMetrics {
  /**
   * Sum of all prompt tokens across all steps, including cached tokens
   */
  total_prompt_tokens?: number | null;
  /**
   * Sum of all completion tokens across all steps
   */
  total_completion_tokens?: number | null;
  /**
   * Sum of all cached tokens across all steps
   */
  total_cached_tokens?: number | null;
  /**
   * Total real monetary cost for the entire trajectory, including cost for subagents, if any
   */
  total_cost_usd?: number | null;
  /**
   * Total number of steps. If not equivalent to the number of steps in the trajectory, must be documented in the root-level notes field.
   */
  total_steps?: number | null;
  /**
   * Custom aggregate metrics
   */
  extra?: FinalMetricsExtra | null;
}
export interface FinalMetricsExtra {
  avp?: FinalMetricsAvpExtra | null;
  [k: string]: unknown;
}
/**
 * At `final_metrics.extra.avp`.
 */
export interface FinalMetricsAvpExtra {
  /**
   * The total of `cache_creation_input_tokens`.
   */
  total_cache_creation_input_tokens?: number | null;
  /**
   * The total of `reasoning_output_tokens`.
   */
  total_reasoning_output_tokens?: number | null;
  /**
   * How many model responses were made.
   */
  total_responses?: number | null;
  /**
   * `false` when `total_cost_usd` leaves out responses whose cost is unknown.
   */
  cost_complete?: boolean | null;
  [k: string]: unknown;
}
/**
 * LLM operational and confidence data.
 */
export interface Metrics {
  /**
   * Total input tokens including cached and non-cached
   */
  prompt_tokens?: number | null;
  /**
   * Total tokens generated by the LLM response
   */
  completion_tokens?: number | null;
  /**
   * Subset of prompt_tokens that were cache hits
   */
  cached_tokens?: number | null;
  /**
   * Monetary cost of the API call in USD
   */
  cost_usd?: number | null;
  /**
   * Token IDs for prompt (input) tokens sent to the LLM, including chat history (if applicable)
   */
  prompt_token_ids?: number[] | null;
  /**
   * Token IDs for completion (response) tokens, enabling RL training without retokenization drift
   */
  completion_token_ids?: number[] | null;
  /**
   * Log probability assigned to each generated token
   */
  logprobs?: number[] | null;
  /**
   * Other metrics
   */
  extra?: MetricsExtra | null;
}
export interface MetricsExtra {
  avp?: MetricsAvpExtra | null;
  [k: string]: unknown;
}
/**
 * At `steps[].metrics.extra.avp`: the usage of one model response.
 */
export interface MetricsAvpExtra {
  /**
   * The input tokens written to the cache. Included in `prompt_tokens`.
   */
  cache_creation_input_tokens?: number | null;
  /**
   * The output tokens the model spent on reasoning. Included in `completion_tokens`.
   */
  reasoning_output_tokens?: number | null;
  /**
   * Where `cost_usd` comes from.
   */
  cost_source?: ("reported" | "computed") | null;
  [k: string]: unknown;
}
/**
 * Environment feedback/result after actions or system events.
 */
export interface Observation {
  /**
   * Array of result objects from tool calls or actions
   */
  results: ObservationResult[];
}
/**
 * A single result within an observation.
 */
export interface ObservationResult {
  /**
   * The `tool_call_id` from the _tool_calls_ array in _StepObject_ that this result corresponds to. If null or omitted, the result comes from an action that doesn't use the standard tool calling format (e.g., agent actions without tool calls or system-initiated operations).
   */
  source_call_id?: string | null;
  /**
   * The output or result from the tool execution. String for text-only content, or array of ContentPart for multimodal content (added in ATIF-v1.6).
   */
  content?: string | ContentPart[] | null;
  /**
   * Array of references to delegated subagent trajectories
   */
  subagent_trajectory_ref?: SubagentTrajectoryRef[] | null;
  /**
   * Custom observation-result-level metadata (e.g., confidence score, retrieval score, source document ID). Added in ATIF-v1.7.
   */
  extra?: ObservationResultExtra | null;
}
/**
 * Reference to a delegated subagent trajectory.
 *
 * A subagent reference is resolved by one of two mechanisms:
 *
 * 1. **Embedded form** — set `trajectory_id` to match the
 *    `Trajectory.trajectory_id` of an entry in the parent's
 *    `subagent_trajectories` array.
 * 2. **File-ref form** — set `trajectory_path` to the location
 *    (file path, S3 URL, etc.) of an external trajectory file.
 *
 * These two mechanisms are the only resolution keys. `session_id`, when
 * present on the ref, is **informational only**: it records the run
 * identity of the delegated subagent for debug / correlation / cross-
 * trajectory search purposes, and MUST NOT be used as a matching key
 * (it is run-scoped and MAY collide across siblings — see
 * `Trajectory.session_id`). A ref therefore MUST set at least one of
 * `trajectory_id` or `trajectory_path`; `session_id` alone is not a
 * resolvable reference.
 */
export interface SubagentTrajectoryRef {
  /**
   * Canonical identifier of the delegated subagent trajectory. Matches `Trajectory.trajectory_id` of an entry in the parent's `subagent_trajectories` array and is the resolution key for embedded references. Added in ATIF-v1.7 to provide a document-unique matching key without overloading `session_id`.
   */
  trajectory_id?: string | null;
  /**
   * Run identity of the delegated subagent trajectory. Informational only: recorded so consumers can correlate this ref back to the subagent's run for debug / search / display purposes. Run-scoped (see `Trajectory.session_id`) and therefore NOT a valid resolution key — consumers MUST resolve via `trajectory_id` (embedded) or `trajectory_path` (external file).
   */
  session_id?: string | null;
  /**
   * Location of the complete subagent trajectory as an external file (file path, S3 URL, database reference, etc.). Resolution key for file-ref references. When both `trajectory_id` and `trajectory_path` are set, consumers MAY choose either; typically `trajectory_id` is preferred when the embedded trajectory is available in-memory.
   */
  trajectory_path?: string | null;
  /**
   * Custom metadata about the subagent execution
   */
  extra?: Extra | null;
}
export interface ObservationResultExtra {
  avp?: ObservationResultAvpExtra | null;
  [k: string]: unknown;
}
/**
 * At `steps[].observation.results[].extra.avp`.
 */
export interface ObservationResultAvpExtra {
  /**
   * How long the tool took, in milliseconds, ending at `finished_at`.
   */
  duration_ms?: number | null;
  /**
   * When the result arrived, as an RFC 3339 timestamp.
   */
  finished_at?: string | null;
  /**
   * `true` when the call failed.
   */
  is_error?: boolean | null;
  structured_content?: unknown;
  /**
   * Data for parts of `content`.
   */
  content_metadata?: ContentMetadata[] | null;
  [k: string]: unknown;
}
/**
 * Data for one block of the model's reasoning. Keeps fields the service added.
 */
export interface ReasoningMetadata {
  /**
   * Where the block's text starts in `reasoning_content`.
   */
  start?: number | null;
  /**
   * Where it ends. When `start` and `end` are absent, the block is all of `reasoning_content`.
   */
  end?: number | null;
  /**
   * The service's token for passing the reasoning back to it.
   */
  signature?: string | null;
  /**
   * The service's encrypted reasoning, when it returned the block encrypted.
   */
  encrypted_content?: string | null;
  [k: string]: unknown;
}
/**
 * A single step in the trajectory.
 */
export interface Step {
  /**
   * Ordinal index of the turn (starting from 1)
   */
  step_id: number;
  /**
   * ISO 8601 timestamp indicating when this step occurred
   */
  timestamp?: string | null;
  /**
   * The originator of this step
   */
  source: "system" | "user" | "agent";
  /**
   * The specific LLM model used for this turn. Omission implies the model defined in the root-level agent config.
   */
  model_name?: string | null;
  /**
   * Qualitative or quantitative measure of effort
   */
  reasoning_effort?: string | number | null;
  /**
   * The dialogue message. String for text-only content, or array of ContentPart for multimodal content (added in ATIF-v1.6).
   */
  message: string | ContentPart[];
  /**
   * The agent's explicit internal reasoning
   */
  reasoning_content?: string | null;
  /**
   * Array of structured objects for the agent's actions
   */
  tool_calls?: ToolCall[] | null;
  /**
   * Environment feedback/result after actions or system events
   */
  observation?: Observation | null;
  /**
   * LLM operational and confidence data for this step
   */
  metrics?: Metrics | null;
  /**
   * Indicates whether this step was copied from a previous trajectory for context (e.g., during continuation after summarization). Steps marked as copied context should not be included in training data as they represent previously-trained interactions. Added in ATIF-v1.5.
   */
  is_copied_context?: boolean | null;
  /**
   * Number of LLM inferences this step represents. When >1, metrics are aggregated across multiple LLM calls. When 1, the step represents exactly one inference. When 0 on a `source: 'agent'` step, the step represents a deterministic (non-LLM) dispatch; `metrics` and `reasoning_content` MUST be absent in that case. When null, the producer did not track this (backward-compatible default). Added in ATIF-v1.7.
   */
  llm_call_count?: number | null;
  /**
   * Custom step-level metadata
   */
  extra?: StepExtra | null;
}
/**
 * A tool call within a step.
 */
export interface ToolCall {
  /**
   * Unique identifier for this specific tool call
   */
  tool_call_id: string;
  /**
   * The name of the function or tool being invoked
   */
  function_name: string;
  /**
   * Arguments passed to the function (can be empty dict)
   */
  arguments: {
    [k: string]: unknown;
  };
  /**
   * Custom tool-call-level metadata (e.g., timeout, retry count, tool version). Added in ATIF-v1.7.
   */
  extra?: ToolCallExtra | null;
}
export interface ToolCallExtra {
  avp?: ToolCallAvpExtra | null;
  [k: string]: unknown;
}
/**
 * At `steps[].tool_calls[].extra.avp`.
 */
export interface ToolCallAvpExtra {
  /**
   * `true` when the model service ran the tool, not the agent.
   */
  server_side?: boolean | null;
  [k: string]: unknown;
}
export interface StepExtra {
  avp?: StepAvpExtra | null;
  [k: string]: unknown;
}
/**
 * At `steps[].extra.avp`.
 */
export interface StepAvpExtra {
  /**
   * How long the model response took, in milliseconds.
   */
  duration_ms?: number | null;
  /**
   * Why the model stopped, exactly as the service reported it.
   */
  finish_reasons?: string[] | null;
  /**
   * Data for parts of `message`.
   */
  message_metadata?: ContentMetadata[] | null;
  /**
   * Data for blocks of the model's reasoning.
   */
  reasoning_metadata?: ReasoningMetadata[] | null;
  /**
   * What kind of error a system step records.
   */
  error_code?: string | null;
  [k: string]: unknown;
}
/**
 * Agent Trajectory in ATIF (Agent Trajectory Interchange Format).
 */
export interface Trajectory {
  /**
   * String defining ATIF compatibility
   */
  schema_version?:
    | "ATIF-v1.0"
    | "ATIF-v1.1"
    | "ATIF-v1.2"
    | "ATIF-v1.3"
    | "ATIF-v1.4"
    | "ATIF-v1.5"
    | "ATIF-v1.6"
    | "ATIF-v1.7"
    | "ATIF-v1.8";
  /**
   * Identifier for the agent run this trajectory belongs to. Scoped to the run, NOT to an individual trajectory document: multiple Trajectory objects MAY share the same `session_id` when they represent the same logical run (e.g., a parent trajectory and its embedded subagents, or a trajectory and its continuation segments linked via `continued_trajectory_ref`). Therefore `session_id`s within a parent's `subagent_trajectories` array are NOT required to be unique. Use `trajectory_id` when a per-trajectory-document unique identifier is required (e.g., for `SubagentTrajectoryRef` resolution). Optional since ATIF-v1.7; producers SHOULD set this on root trajectories for run-level traceability, and MAY omit it on embedded subagents that inherit the parent's run identity.
   */
  session_id?: string | null;
  /**
   * Canonical per-trajectory-document identifier, distinct from `session_id`. Unlike `session_id` (which is run-scoped and MAY be shared), `trajectory_id` uniquely identifies THIS trajectory object. Used to resolve `SubagentTrajectoryRef` entries against the root's `subagent_trajectories` array without overloading `session_id`'s run-scoped semantics. Optional on standalone trajectories, but REQUIRED on any trajectory embedded in a parent's `subagent_trajectories` array. `trajectory_id`s within a single parent's `subagent_trajectories` array MUST be unique. Added in ATIF-v1.7.
   */
  trajectory_id?: string | null;
  agent: Agent;
  /**
   * Array of step objects representing the complete interaction history
   *
   * @minItems 1
   */
  steps: [Step, ...Step[]];
  /**
   * Custom information, design notes, or explanations
   */
  notes?: string | null;
  /**
   * Summary metrics for the entire trajectory
   */
  final_metrics?: FinalMetrics | null;
  /**
   * Reference to the continuation trajectory file if this trajectory is continued in another file
   */
  continued_trajectory_ref?: string | null;
  /**
   * Custom root-level metadata
   */
  extra?: TrajectoryExtra | null;
  /**
   * Array of embedded subagent trajectories. Each element is a complete, independently-valid ATIF Trajectory with its own schema_version, agent, and step_id sequence starting at 1. Enables single-file storage of multi-agent workflows: when a SubagentTrajectoryRef.trajectory_path is null, consumers resolve the reference by matching SubagentTrajectoryRef.trajectory_id against Trajectory.trajectory_id of entries in this array. Uniqueness rules: every embedded subagent MUST set `trajectory_id`, and `trajectory_id`s within this array MUST be unique. `session_id`, by contrast, is run-scoped and MAY collide across siblings (or match the parent) when all trajectories belong to the same logical run; embedded subagents MAY also omit `session_id` entirely to inherit the parent's run identity. Added in ATIF-v1.7.
   */
  subagent_trajectories?: Trajectory[] | null;
}
export interface TrajectoryExtra {
  avp?: TrajectoryAvpExtra | null;
  [k: string]: unknown;
}
/**
 * At the trajectory's `extra.avp`, and on each embedded subagent trajectory.
 */
export interface TrajectoryAvpExtra {
  /**
   * The AVP version the Trajectory follows.
   */
  avp_version: "0.1";
  commission?: unknown;
  /**
   * When the run started, as an RFC 3339 timestamp.
   */
  started_at?: string | null;
  /**
   * When the run stopped, as an RFC 3339 timestamp.
   */
  stopped_at: string;
  /**
   * Why the run stopped.
   */
  stop_reason: "converged" | "refused" | "error" | "interrupted" | "abandoned";
  output?: unknown;
  [k: string]: unknown;
}
