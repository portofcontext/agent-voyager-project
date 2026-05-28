#![allow(clippy::redundant_closure_call)]
#![allow(clippy::needless_lifetimes)]
#![allow(clippy::match_single_binding)]
#![allow(clippy::clone_on_copy)]

#[doc = r" Error types."]
pub mod error {
    #[doc = r" Error from a `TryFrom` or `FromStr` implementation."]
    pub struct ConversionError(::std::borrow::Cow<'static, str>);
    impl ::std::error::Error for ConversionError {}
    impl ::std::fmt::Display for ConversionError {
        fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> Result<(), ::std::fmt::Error> {
            ::std::fmt::Display::fmt(&self.0, f)
        }
    }
    impl ::std::fmt::Debug for ConversionError {
        fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> Result<(), ::std::fmt::Error> {
            ::std::fmt::Debug::fmt(&self.0, f)
        }
    }
    impl From<&'static str> for ConversionError {
        fn from(value: &'static str) -> Self {
            Self(value.into())
        }
    }
    impl From<String> for ConversionError {
        fn from(value: String) -> Self {
            Self(value.into())
        }
    }
}
#[doc = "Payload of avp.agent_described events.\n\nThe agent's published Descriptor, emitted between `run_requested`\nand `agent_started`. `avp.descriptor` SHOULD be consistent with what\n`<agent> describe` prints to stdout for the same agent build;\npre-flight describe MAY omit MCP-surfaced tool entries (those whose\n`avp.mcp_server_id` is set) and per-server `mcp_servers[].status`,\nboth of which require a startup dial."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentDescribedData\","]
#[doc = "  \"description\": \"Payload of avp.agent_described events.\\n\\nThe agent's published Descriptor, emitted between `run_requested`\\nand `agent_started`. `avp.descriptor` SHOULD be consistent with what\\n`<agent> describe` prints to stdout for the same agent build;\\npre-flight describe MAY omit MCP-surfaced tool entries (those whose\\n`avp.mcp_server_id` is set) and per-server `mcp_servers[].status`,\\nboth of which require a startup dial.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.descriptor\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.descriptor\": {"]
#[doc = "      \"$ref\": \"#/$defs/AgentDescriptor\""]
#[doc = "    },"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct AgentDescribedData {
    #[serde(rename = "avp.descriptor")]
    pub avp_descriptor: AgentDescriptor,
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "Second event of the trajectory. The agent's \"whoami\":\nself-published manifest of everything triggerable without supervisor\nconfiguration. Carries the same JSON `<agent> describe` prints to\nstdout for this agent build."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentDescribedEvent\","]
#[doc = "  \"description\": \"Second event of the trajectory. The agent's \\\"whoami\\\":\\nself-published manifest of everything triggerable without supervisor\\nconfiguration. Carries the same JSON `<agent> describe` prints to\\nstdout for this agent build.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/AgentDescribedData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.agent_described\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.agent_described\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct AgentDescribedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<AgentDescribedEventAvpCorrelationId>,
    pub data: AgentDescribedData,
    #[serde(default = "defaults::agent_described_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::agent_described_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::agent_described_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<AgentDescribedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::agent_described_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`AgentDescribedEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AgentDescribedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for AgentDescribedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentDescribedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: AgentDescribedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentDescribedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentDescribedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentDescribedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentDescribedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentDescribedEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`AgentDescribedEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AgentDescribedEventSubject(::std::string::String);
impl ::std::ops::Deref for AgentDescribedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentDescribedEventSubject> for ::std::string::String {
    fn from(value: AgentDescribedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentDescribedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentDescribedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentDescribedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentDescribedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentDescribedEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Self-description of an AVP agent: the static surface it ships with.\n\nIdentity, capabilities, supported models, system prompt, baked-in user\nprompt (for autonomous agents), MCP servers, tools, skills, subagents.\nProvenance inside the agent doesn't matter on the wire: an SDK preset\ntool (`Grep`), a runtime-bundled skill, and a hand-coded tool are all\njust \"what's in the agent\" to a Descriptor consumer.\n\nTwo views, normatively consistent:\n\n  1. **Pre-flight**: `<agent> describe` prints the Descriptor as JSON.\n  2. **On the wire**: `agent_described.data[\"avp.descriptor\"]` carries\n     the same payload during a run.\n\nThe pre-flight view MAY omit MCP-surfaced `tools[]` entries (those\nwhose `avp.mcp_server_id` is set) and per-server `mcp_servers[].status`,\nsince both require the agent to dial its MCP servers and run\n`tools/list` — work the agent only needs to do at run-time. Every\nother field MUST be identical between the two views.\n\nAnything that varies per invocation (per-call prompt, run_id, thread_id,\nadditional supervisor-managed assets) belongs on the Commission, not\nhere."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentDescriptor\","]
#[doc = "  \"description\": \"Self-description of an AVP agent: the static surface it ships with.\\n\\nIdentity, capabilities, supported models, system prompt, baked-in user\\nprompt (for autonomous agents), MCP servers, tools, skills, subagents.\\nProvenance inside the agent doesn't matter on the wire: an SDK preset\\ntool (`Grep`), a runtime-bundled skill, and a hand-coded tool are all\\njust \\\"what's in the agent\\\" to a Descriptor consumer.\\n\\nTwo views, normatively consistent:\\n\\n  1. **Pre-flight**: `<agent> describe` prints the Descriptor as JSON.\\n  2. **On the wire**: `agent_described.data[\\\"avp.descriptor\\\"]` carries\\n     the same payload during a run.\\n\\nThe pre-flight view MAY omit MCP-surfaced `tools[]` entries (those\\nwhose `avp.mcp_server_id` is set) and per-server `mcp_servers[].status`,\\nsince both require the agent to dial its MCP servers and run\\n`tools/list` — work the agent only needs to do at run-time. Every\\nother field MUST be identical between the two views.\\n\\nAnything that varies per invocation (per-call prompt, run_id, thread_id,\\nadditional supervisor-managed assets) belongs on the Commission, not\\nhere.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"agent_name\","]
#[doc = "    \"agent_version\","]
#[doc = "    \"spec_version\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"agent_name\": {"]
#[doc = "      \"title\": \"Agent Name\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"agent_version\": {"]
#[doc = "      \"title\": \"Agent Version\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"capabilities\": {"]
#[doc = "      \"title\": \"Capabilities\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"default_model\": {"]
#[doc = "      \"title\": \"Default Model\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"mcp_servers\": {"]
#[doc = "      \"title\": \"Mcp Servers\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/McpServerDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"prompt\": {"]
#[doc = "      \"title\": \"Prompt\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"skills\": {"]
#[doc = "      \"title\": \"Skills\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/SkillDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"spec_version\": {"]
#[doc = "      \"title\": \"Spec Version\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"0.1\""]
#[doc = "    },"]
#[doc = "    \"subagents\": {"]
#[doc = "      \"title\": \"Subagents\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/SubagentDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"supported_models\": {"]
#[doc = "      \"title\": \"Supported Models\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"system_prompt\": {"]
#[doc = "      \"title\": \"System Prompt\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"tools\": {"]
#[doc = "      \"title\": \"Tools\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/ToolDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct AgentDescriptor {
    pub agent_name: AgentName,
    pub agent_version: AgentVersion,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub capabilities: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub default_model: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub mcp_servers: ::std::option::Option<::std::vec::Vec<McpServerDecl>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub skills: ::std::option::Option<::std::vec::Vec<SkillDecl>>,
    pub spec_version: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subagents: ::std::option::Option<::std::vec::Vec<SubagentDecl>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub supported_models: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub system_prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tools: ::std::option::Option<::std::vec::Vec<ToolDecl>>,
}
#[doc = "`AgentName`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Agent Name\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AgentName(::std::string::String);
impl ::std::ops::Deref for AgentName {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentName> for ::std::string::String {
    fn from(value: AgentName) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentName {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentName {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentName {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Payload of avp.agent_started events."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentStartedData\","]
#[doc = "  \"description\": \"Payload of avp.agent_started events.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.mcp_servers\": {"]
#[doc = "      \"title\": \"Avp.Mcp Servers\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/McpServerDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.operation.name\": {"]
#[doc = "      \"title\": \"Avp.Operation.Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"enum\": ["]
#[doc = "            \"invoke_agent\","]
#[doc = "            \"chat\""]
#[doc = "          ]"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.prompt\": {"]
#[doc = "      \"title\": \"Avp.Prompt\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.provider.name\": {"]
#[doc = "      \"title\": \"Avp.Provider.Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.request.model\": {"]
#[doc = "      \"title\": \"Avp.Request.Model\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.session_id\": {"]
#[doc = "      \"title\": \"Avp.Session Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.skills\": {"]
#[doc = "      \"title\": \"Avp.Skills\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/SkillDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.subagents\": {"]
#[doc = "      \"title\": \"Avp.Subagents\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/SubagentDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.system_prompt\": {"]
#[doc = "      \"title\": \"Avp.System Prompt\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.tags\": {"]
#[doc = "      \"title\": \"Avp.Tags\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.thread_id\": {"]
#[doc = "      \"title\": \"Avp.Thread Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.tools\": {"]
#[doc = "      \"title\": \"Avp.Tools\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/ToolDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct AgentStartedData {
    #[serde(
        rename = "avp.mcp_servers",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_servers: ::std::option::Option<::std::vec::Vec<McpServerDecl>>,
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(
        rename = "avp.operation.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_operation_name: ::std::option::Option<AgentStartedDataAvpOperationName>,
    #[serde(
        rename = "avp.prompt",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_prompt: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.provider.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_provider_name: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.request.model",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_request_model: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.session_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_session_id: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.skills",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_skills: ::std::option::Option<::std::vec::Vec<SkillDecl>>,
    #[serde(
        rename = "avp.subagents",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_subagents: ::std::option::Option<::std::vec::Vec<SubagentDecl>>,
    #[serde(
        rename = "avp.system_prompt",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_system_prompt: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.tags",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tags: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(
        rename = "avp.thread_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_thread_id: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.tools",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tools: ::std::option::Option<::std::vec::Vec<ToolDecl>>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`AgentStartedDataAvpOperationName`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"invoke_agent\","]
#[doc = "    \"chat\""]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum AgentStartedDataAvpOperationName {
    #[serde(rename = "invoke_agent")]
    InvokeAgent,
    #[serde(rename = "chat")]
    Chat,
}
impl ::std::fmt::Display for AgentStartedDataAvpOperationName {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::InvokeAgent => f.write_str("invoke_agent"),
            Self::Chat => f.write_str("chat"),
        }
    }
}
impl ::std::str::FromStr for AgentStartedDataAvpOperationName {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "invoke_agent" => Ok(Self::InvokeAgent),
            "chat" => Ok(Self::Chat),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for AgentStartedDataAvpOperationName {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentStartedDataAvpOperationName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentStartedDataAvpOperationName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`AgentStartedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentStartedEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/AgentStartedData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.agent_started\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.agent_started\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct AgentStartedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<AgentStartedEventAvpCorrelationId>,
    pub data: AgentStartedData,
    #[serde(default = "defaults::agent_started_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::agent_started_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::agent_started_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<AgentStartedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::agent_started_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`AgentStartedEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AgentStartedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for AgentStartedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentStartedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: AgentStartedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentStartedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentStartedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentStartedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentStartedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentStartedEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`AgentStartedEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AgentStartedEventSubject(::std::string::String);
impl ::std::ops::Deref for AgentStartedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentStartedEventSubject> for ::std::string::String {
    fn from(value: AgentStartedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentStartedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentStartedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentStartedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentStartedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentStartedEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Payload of avp.agent_stopped events. Terminator of the trajectory.\n\nCarries `avp.reason` (why the run ended) and an optional `avp.output`\npayload. The agent does NOT publish cumulative totals on this event.\nPer-turn deltas live on each `assistant_message`; consumers reduce\nthe stream to compute totals."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentStoppedData\","]
#[doc = "  \"description\": \"Payload of avp.agent_stopped events. Terminator of the trajectory.\\n\\nCarries `avp.reason` (why the run ended) and an optional `avp.output`\\npayload. The agent does NOT publish cumulative totals on this event.\\nPer-turn deltas live on each `assistant_message`; consumers reduce\\nthe stream to compute totals.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.reason\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.output\": {"]
#[doc = "      \"title\": \"Avp.Output\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {},"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.reason\": {"]
#[doc = "      \"$ref\": \"#/$defs/StopReason\""]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct AgentStoppedData {
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(
        rename = "avp.output",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_output: ::std::option::Option<::serde_json::Value>,
    #[serde(rename = "avp.reason")]
    pub avp_reason: StopReason,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`AgentStoppedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentStoppedEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/AgentStoppedData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.agent_stopped\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.agent_stopped\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct AgentStoppedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<AgentStoppedEventAvpCorrelationId>,
    pub data: AgentStoppedData,
    #[serde(default = "defaults::agent_stopped_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::agent_stopped_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::agent_stopped_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<AgentStoppedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::agent_stopped_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`AgentStoppedEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AgentStoppedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for AgentStoppedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentStoppedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: AgentStoppedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentStoppedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentStoppedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentStoppedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentStoppedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentStoppedEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`AgentStoppedEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AgentStoppedEventSubject(::std::string::String);
impl ::std::ops::Deref for AgentStoppedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentStoppedEventSubject> for ::std::string::String {
    fn from(value: AgentStoppedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentStoppedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentStoppedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentStoppedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentStoppedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentStoppedEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`AgentVersion`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Agent Version\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AgentVersion(::std::string::String);
impl ::std::ops::Deref for AgentVersion {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentVersion> for ::std::string::String {
    fn from(value: AgentVersion) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentVersion {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentVersion {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentVersion {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentVersion {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentVersion {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Payload of avp.assistant_message events.\n\nCarries the full content the model produced this turn under\n`avp.content` (a `list[AVPContentBlock]`) plus per-turn token / cost\ndeltas. Reconstructing a provider message array is a direct read of\n`avp.content` per turn, paired with the `avp.tool_result` blocks from\nintervening `tool_returned` events to form the user-role tool-result\nmessages.\n\nRefusal metadata: when the provider declined the turn, the refusal\ntext appears as a `RefusalBlock` (or `TextBlock` for providers that\ndon't typify it) inside `avp.content`, the upstream finish-reason\nstring surfaces on `avp.response.finish_reasons`, and the\nprovider's safety category (when given, free-form because every\nprovider names them differently) surfaces on `avp.refusal.category`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AssistantMessageData\","]
#[doc = "  \"description\": \"Payload of avp.assistant_message events.\\n\\nCarries the full content the model produced this turn under\\n`avp.content` (a `list[AVPContentBlock]`) plus per-turn token / cost\\ndeltas. Reconstructing a provider message array is a direct read of\\n`avp.content` per turn, paired with the `avp.tool_result` blocks from\\nintervening `tool_returned` events to form the user-role tool-result\\nmessages.\\n\\nRefusal metadata: when the provider declined the turn, the refusal\\ntext appears as a `RefusalBlock` (or `TextBlock` for providers that\\ndon't typify it) inside `avp.content`, the upstream finish-reason\\nstring surfaces on `avp.response.finish_reasons`, and the\\nprovider's safety category (when given, free-form because every\\nprovider names them differently) surfaces on `avp.refusal.category`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.content\","]
#[doc = "    \"avp.cost_usd\","]
#[doc = "    \"avp.duration_ms\","]
#[doc = "    \"avp.step\","]
#[doc = "    \"avp.usage\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.content\": {"]
#[doc = "      \"title\": \"Avp.Content\","]
#[doc = "      \"type\": \"array\","]
#[doc = "      \"items\": {"]
#[doc = "        \"oneOf\": ["]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/TextBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/ThinkingBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/ImageBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/AudioBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/VideoBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/DocumentBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/ToolUseBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/ToolResultBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/ServerToolUseBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/ServerToolResultBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/RefusalBlock\""]
#[doc = "          }"]
#[doc = "        ],"]
#[doc = "        \"discriminator\": {"]
#[doc = "          \"mapping\": {"]
#[doc = "            \"audio\": \"#/$defs/AudioBlock\","]
#[doc = "            \"document\": \"#/$defs/DocumentBlock\","]
#[doc = "            \"image\": \"#/$defs/ImageBlock\","]
#[doc = "            \"refusal\": \"#/$defs/RefusalBlock\","]
#[doc = "            \"server_tool_result\": \"#/$defs/ServerToolResultBlock\","]
#[doc = "            \"server_tool_use\": \"#/$defs/ServerToolUseBlock\","]
#[doc = "            \"text\": \"#/$defs/TextBlock\","]
#[doc = "            \"thinking\": \"#/$defs/ThinkingBlock\","]
#[doc = "            \"tool_result\": \"#/$defs/ToolResultBlock\","]
#[doc = "            \"tool_use\": \"#/$defs/ToolUseBlock\","]
#[doc = "            \"video\": \"#/$defs/VideoBlock\""]
#[doc = "          },"]
#[doc = "          \"propertyName\": \"type\""]
#[doc = "        }"]
#[doc = "      }"]
#[doc = "    },"]
#[doc = "    \"avp.cost.source\": {"]
#[doc = "      \"title\": \"Avp.Cost.Source\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"enum\": ["]
#[doc = "            \"computed\","]
#[doc = "            \"reported\","]
#[doc = "            \"unknown\""]
#[doc = "          ]"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.cost_usd\": {"]
#[doc = "      \"title\": \"Avp.Cost Usd\","]
#[doc = "      \"type\": \"number\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.duration_ms\": {"]
#[doc = "      \"title\": \"Avp.Duration Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.provider.name\": {"]
#[doc = "      \"title\": \"Avp.Provider.Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.refusal.category\": {"]
#[doc = "      \"title\": \"Avp.Refusal.Category\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.request.model\": {"]
#[doc = "      \"title\": \"Avp.Request.Model\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.response.finish_reasons\": {"]
#[doc = "      \"title\": \"Avp.Response.Finish Reasons\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.response.model\": {"]
#[doc = "      \"title\": \"Avp.Response.Model\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.response.time_to_first_chunk\": {"]
#[doc = "      \"title\": \"Avp.Response.Time To First Chunk\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"number\","]
#[doc = "          \"minimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.step\": {"]
#[doc = "      \"title\": \"Avp.Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.usage\": {"]
#[doc = "      \"$ref\": \"#/$defs/Usage\""]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct AssistantMessageData {
    #[serde(rename = "avp.content")]
    pub avp_content: ::std::vec::Vec<AvpContentItem>,
    #[serde(
        rename = "avp.cost.source",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_cost_source: ::std::option::Option<AssistantMessageDataAvpCostSource>,
    #[serde(rename = "avp.cost_usd")]
    pub avp_cost_usd: f64,
    #[serde(rename = "avp.duration_ms")]
    pub avp_duration_ms: u64,
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(
        rename = "avp.provider.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_provider_name: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.refusal.category",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_refusal_category: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.request.model",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_request_model: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.response.finish_reasons",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_response_finish_reasons: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(
        rename = "avp.response.model",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_response_model: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.response.time_to_first_chunk",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_response_time_to_first_chunk: ::std::option::Option<f64>,
    #[serde(rename = "avp.step")]
    pub avp_step: u64,
    #[serde(rename = "avp.usage")]
    pub avp_usage: Usage,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`AssistantMessageDataAvpCostSource`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"computed\","]
#[doc = "    \"reported\","]
#[doc = "    \"unknown\""]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum AssistantMessageDataAvpCostSource {
    #[serde(rename = "computed")]
    Computed,
    #[serde(rename = "reported")]
    Reported,
    #[serde(rename = "unknown")]
    Unknown,
}
impl ::std::fmt::Display for AssistantMessageDataAvpCostSource {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Computed => f.write_str("computed"),
            Self::Reported => f.write_str("reported"),
            Self::Unknown => f.write_str("unknown"),
        }
    }
}
impl ::std::str::FromStr for AssistantMessageDataAvpCostSource {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "computed" => Ok(Self::Computed),
            "reported" => Ok(Self::Reported),
            "unknown" => Ok(Self::Unknown),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for AssistantMessageDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AssistantMessageDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AssistantMessageDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`AssistantMessageEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AssistantMessageEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/AssistantMessageData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.assistant_message\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.assistant_message\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct AssistantMessageEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<AssistantMessageEventAvpCorrelationId>,
    pub data: AssistantMessageData,
    #[serde(default = "defaults::assistant_message_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::assistant_message_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::assistant_message_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<AssistantMessageEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::assistant_message_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`AssistantMessageEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AssistantMessageEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for AssistantMessageEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AssistantMessageEventAvpCorrelationId> for ::std::string::String {
    fn from(value: AssistantMessageEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AssistantMessageEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AssistantMessageEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AssistantMessageEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AssistantMessageEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AssistantMessageEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`AssistantMessageEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AssistantMessageEventSubject(::std::string::String);
impl ::std::ops::Deref for AssistantMessageEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AssistantMessageEventSubject> for ::std::string::String {
    fn from(value: AssistantMessageEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AssistantMessageEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AssistantMessageEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AssistantMessageEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AssistantMessageEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AssistantMessageEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Audio content. OpenAI `input_audio` (input) and `audio` (output),\nGemini `inline_data` audio, Bedrock `audio`. `transcript` carries\nOpenAI's output-audio transcript when present."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AudioBlock\","]
#[doc = "  \"description\": \"Audio content. OpenAI `input_audio` (input) and `audio` (output),\\nGemini `inline_data` audio, Bedrock `audio`. `transcript` carries\\nOpenAI's output-audio transcript when present.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"source\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"oneOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/Base64Source\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/UrlSource\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/FileSource\""]
#[doc = "        }"]
#[doc = "      ],"]
#[doc = "      \"discriminator\": {"]
#[doc = "        \"mapping\": {"]
#[doc = "          \"base64\": \"#/$defs/Base64Source\","]
#[doc = "          \"file\": \"#/$defs/FileSource\","]
#[doc = "          \"url\": \"#/$defs/UrlSource\""]
#[doc = "        },"]
#[doc = "        \"propertyName\": \"type\""]
#[doc = "      }"]
#[doc = "    },"]
#[doc = "    \"transcript\": {"]
#[doc = "      \"title\": \"Transcript\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"audio\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"audio\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct AudioBlock {
    pub source: Source,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub transcript: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::audio_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "`AvpContentItem`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"oneOf\": ["]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/TextBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ThinkingBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ImageBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/AudioBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/VideoBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/DocumentBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolUseBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolResultBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ServerToolUseBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ServerToolResultBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/RefusalBlock\""]
#[doc = "    }"]
#[doc = "  ],"]
#[doc = "  \"discriminator\": {"]
#[doc = "    \"mapping\": {"]
#[doc = "      \"audio\": \"#/$defs/AudioBlock\","]
#[doc = "      \"document\": \"#/$defs/DocumentBlock\","]
#[doc = "      \"image\": \"#/$defs/ImageBlock\","]
#[doc = "      \"refusal\": \"#/$defs/RefusalBlock\","]
#[doc = "      \"server_tool_result\": \"#/$defs/ServerToolResultBlock\","]
#[doc = "      \"server_tool_use\": \"#/$defs/ServerToolUseBlock\","]
#[doc = "      \"text\": \"#/$defs/TextBlock\","]
#[doc = "      \"thinking\": \"#/$defs/ThinkingBlock\","]
#[doc = "      \"tool_result\": \"#/$defs/ToolResultBlock\","]
#[doc = "      \"tool_use\": \"#/$defs/ToolUseBlock\","]
#[doc = "      \"video\": \"#/$defs/VideoBlock\""]
#[doc = "    },"]
#[doc = "    \"propertyName\": \"type\""]
#[doc = "  }"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(tag = "type")]
pub enum AvpContentItem {
    #[serde(rename = "text")]
    TextBlock(TextBlock),
    #[serde(rename = "thinking")]
    ThinkingBlock(ThinkingBlock),
    #[serde(rename = "image")]
    ImageBlock(ImageBlock),
    #[serde(rename = "audio")]
    AudioBlock(AudioBlock),
    #[serde(rename = "video")]
    VideoBlock(VideoBlock),
    #[serde(rename = "document")]
    DocumentBlock(DocumentBlock),
    #[serde(rename = "tool_use")]
    ToolUseBlock(ToolUseBlock),
    #[serde(rename = "tool_result")]
    ToolResultBlock(ToolResultBlock),
    #[serde(rename = "server_tool_use")]
    ServerToolUseBlock(ServerToolUseBlock),
    #[serde(rename = "server_tool_result")]
    ServerToolResultBlock(ServerToolResultBlock),
    #[serde(rename = "refusal")]
    RefusalBlock(RefusalBlock),

}
impl ::std::convert::From<TextBlock> for AvpContentItem {
    fn from(value: TextBlock) -> Self {
        Self::TextBlock(value)
    }
}
impl ::std::convert::From<ThinkingBlock> for AvpContentItem {
    fn from(value: ThinkingBlock) -> Self {
        Self::ThinkingBlock(value)
    }
}
impl ::std::convert::From<ImageBlock> for AvpContentItem {
    fn from(value: ImageBlock) -> Self {
        Self::ImageBlock(value)
    }
}
impl ::std::convert::From<AudioBlock> for AvpContentItem {
    fn from(value: AudioBlock) -> Self {
        Self::AudioBlock(value)
    }
}
impl ::std::convert::From<VideoBlock> for AvpContentItem {
    fn from(value: VideoBlock) -> Self {
        Self::VideoBlock(value)
    }
}
impl ::std::convert::From<DocumentBlock> for AvpContentItem {
    fn from(value: DocumentBlock) -> Self {
        Self::DocumentBlock(value)
    }
}
impl ::std::convert::From<ToolUseBlock> for AvpContentItem {
    fn from(value: ToolUseBlock) -> Self {
        Self::ToolUseBlock(value)
    }
}
impl ::std::convert::From<ToolResultBlock> for AvpContentItem {
    fn from(value: ToolResultBlock) -> Self {
        Self::ToolResultBlock(value)
    }
}
impl ::std::convert::From<ServerToolUseBlock> for AvpContentItem {
    fn from(value: ServerToolUseBlock) -> Self {
        Self::ServerToolUseBlock(value)
    }
}
impl ::std::convert::From<ServerToolResultBlock> for AvpContentItem {
    fn from(value: ServerToolResultBlock) -> Self {
        Self::ServerToolResultBlock(value)
    }
}
impl ::std::convert::From<RefusalBlock> for AvpContentItem {
    fn from(value: RefusalBlock) -> Self {
        Self::RefusalBlock(value)
    }
}
#[doc = "`AvpSubagentInvocationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Avp.Subagent.Invocation Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AvpSubagentInvocationId(::std::string::String);
impl ::std::ops::Deref for AvpSubagentInvocationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AvpSubagentInvocationId> for ::std::string::String {
    fn from(value: AvpSubagentInvocationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AvpSubagentInvocationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AvpSubagentInvocationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AvpSubagentInvocationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AvpSubagentInvocationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AvpSubagentInvocationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`AvpToolCallId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Avp.Tool.Call Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AvpToolCallId(::std::string::String);
impl ::std::ops::Deref for AvpToolCallId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AvpToolCallId> for ::std::string::String {
    fn from(value: AvpToolCallId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AvpToolCallId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AvpToolCallId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AvpToolCallId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AvpToolCallId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AvpToolCallId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Agent → supervisor event. Each event is a CloudEvent 1.0 envelope carrying a typed `data` payload. The `type` field is the discriminator (reverse-DNS, `avp.*` namespace). Attribute names inside `data` follow OpenTelemetry GenAI semantic conventions and OTel span identification (`trace_id`, `span_id`, `parent_span_id`); AVP-specific attributes are namespaced `avp.*`. See spec/v0.1/trajectory.md."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"$id\": \"https://avp.dev/schema/v0.1/trajectory.schema.json\","]
#[doc = "  \"title\": \"AVP v0.1 Trajectory (Event)\","]
#[doc = "  \"description\": \"Agent → supervisor event. Each event is a CloudEvent 1.0 envelope carrying a typed `data` payload. The `type` field is the discriminator (reverse-DNS, `avp.*` namespace). Attribute names inside `data` follow OpenTelemetry GenAI semantic conventions and OTel span identification (`trace_id`, `span_id`, `parent_span_id`); AVP-specific attributes are namespaced `avp.*`. See spec/v0.1/trajectory.md.\","]
#[doc = "  \"oneOf\": ["]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/RunRequestedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/AgentDescribedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/AgentStartedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/AgentStoppedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/AssistantMessageEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolInvokedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolReturnedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/SubagentInvokedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/SubagentReturnedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ErrorOccurredEvent\""]
#[doc = "    }"]
#[doc = "  ],"]
#[doc = "  \"discriminator\": {"]
#[doc = "    \"mapping\": {"]
#[doc = "      \"avp.agent_described\": \"#/$defs/AgentDescribedEvent\","]
#[doc = "      \"avp.agent_started\": \"#/$defs/AgentStartedEvent\","]
#[doc = "      \"avp.agent_stopped\": \"#/$defs/AgentStoppedEvent\","]
#[doc = "      \"avp.assistant_message\": \"#/$defs/AssistantMessageEvent\","]
#[doc = "      \"avp.error_occurred\": \"#/$defs/ErrorOccurredEvent\","]
#[doc = "      \"avp.run_requested\": \"#/$defs/RunRequestedEvent\","]
#[doc = "      \"avp.subagent_invoked\": \"#/$defs/SubagentInvokedEvent\","]
#[doc = "      \"avp.subagent_returned\": \"#/$defs/SubagentReturnedEvent\","]
#[doc = "      \"avp.tool_invoked\": \"#/$defs/ToolInvokedEvent\","]
#[doc = "      \"avp.tool_returned\": \"#/$defs/ToolReturnedEvent\""]
#[doc = "    },"]
#[doc = "    \"propertyName\": \"type\""]
#[doc = "  }"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(tag = "type")]
pub enum AvpV01TrajectoryEvent {
    #[serde(rename = "avp.run_requested")]
    RunRequestedEvent(RunRequestedEvent),
    #[serde(rename = "avp.agent_described")]
    AgentDescribedEvent(AgentDescribedEvent),
    #[serde(rename = "avp.agent_started")]
    AgentStartedEvent(AgentStartedEvent),
    #[serde(rename = "avp.agent_stopped")]
    AgentStoppedEvent(AgentStoppedEvent),
    #[serde(rename = "avp.assistant_message")]
    AssistantMessageEvent(AssistantMessageEvent),
    #[serde(rename = "avp.tool_invoked")]
    ToolInvokedEvent(ToolInvokedEvent),
    #[serde(rename = "avp.tool_returned")]
    ToolReturnedEvent(ToolReturnedEvent),
    #[serde(rename = "avp.subagent_invoked")]
    SubagentInvokedEvent(SubagentInvokedEvent),
    #[serde(rename = "avp.subagent_returned")]
    SubagentReturnedEvent(SubagentReturnedEvent),
    #[serde(rename = "avp.error_occurred")]
    ErrorOccurredEvent(ErrorOccurredEvent),

}
impl ::std::convert::From<RunRequestedEvent> for AvpV01TrajectoryEvent {
    fn from(value: RunRequestedEvent) -> Self {
        Self::RunRequestedEvent(value)
    }
}
impl ::std::convert::From<AgentDescribedEvent> for AvpV01TrajectoryEvent {
    fn from(value: AgentDescribedEvent) -> Self {
        Self::AgentDescribedEvent(value)
    }
}
impl ::std::convert::From<AgentStartedEvent> for AvpV01TrajectoryEvent {
    fn from(value: AgentStartedEvent) -> Self {
        Self::AgentStartedEvent(value)
    }
}
impl ::std::convert::From<AgentStoppedEvent> for AvpV01TrajectoryEvent {
    fn from(value: AgentStoppedEvent) -> Self {
        Self::AgentStoppedEvent(value)
    }
}
impl ::std::convert::From<AssistantMessageEvent> for AvpV01TrajectoryEvent {
    fn from(value: AssistantMessageEvent) -> Self {
        Self::AssistantMessageEvent(value)
    }
}
impl ::std::convert::From<ToolInvokedEvent> for AvpV01TrajectoryEvent {
    fn from(value: ToolInvokedEvent) -> Self {
        Self::ToolInvokedEvent(value)
    }
}
impl ::std::convert::From<ToolReturnedEvent> for AvpV01TrajectoryEvent {
    fn from(value: ToolReturnedEvent) -> Self {
        Self::ToolReturnedEvent(value)
    }
}
impl ::std::convert::From<SubagentInvokedEvent> for AvpV01TrajectoryEvent {
    fn from(value: SubagentInvokedEvent) -> Self {
        Self::SubagentInvokedEvent(value)
    }
}
impl ::std::convert::From<SubagentReturnedEvent> for AvpV01TrajectoryEvent {
    fn from(value: SubagentReturnedEvent) -> Self {
        Self::SubagentReturnedEvent(value)
    }
}
impl ::std::convert::From<ErrorOccurredEvent> for AvpV01TrajectoryEvent {
    fn from(value: ErrorOccurredEvent) -> Self {
        Self::ErrorOccurredEvent(value)
    }
}
#[doc = "Inline base64-encoded media. Anthropic `source.type=base64`, Gemini\n`inline_data`, Bedrock `source.bytes`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Base64Source\","]
#[doc = "  \"description\": \"Inline base64-encoded media. Anthropic `source.type=base64`, Gemini\\n`inline_data`, Bedrock `source.bytes`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\","]
#[doc = "    \"media_type\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"data\": {"]
#[doc = "      \"title\": \"Data\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"media_type\": {"]
#[doc = "      \"title\": \"Media Type\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"base64\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"base64\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Base64Source {
    pub data: ::std::string::String,
    pub media_type: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::base64_source_type")]
    pub type_: ::std::string::String,
}
#[doc = "Span-anchored attribution on a text or document block. Unifies\nAnthropic citations (`char_location`, `page_location`,\n`content_block_location`), OpenAI annotations (`url_citation`,\n`file_citation`, `file_path`), and Gemini grounding chunks. `type`\ncarries the provider's raw citation kind verbatim so downstream\nconsumers can normalize without re-deriving it."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Citation\","]
#[doc = "  \"description\": \"Span-anchored attribution on a text or document block. Unifies\\nAnthropic citations (`char_location`, `page_location`,\\n`content_block_location`), OpenAI annotations (`url_citation`,\\n`file_citation`, `file_path`), and Gemini grounding chunks. `type`\\ncarries the provider's raw citation kind verbatim so downstream\\nconsumers can normalize without re-deriving it.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"type\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"cited_text\": {"]
#[doc = "      \"title\": \"Cited Text\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"end_index\": {"]
#[doc = "      \"title\": \"End Index\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\","]
#[doc = "          \"minimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"source_id\": {"]
#[doc = "      \"title\": \"Source Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"source_title\": {"]
#[doc = "      \"title\": \"Source Title\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"source_url\": {"]
#[doc = "      \"title\": \"Source Url\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"start_index\": {"]
#[doc = "      \"title\": \"Start Index\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\","]
#[doc = "          \"minimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Citation {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub cited_text: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub end_index: ::std::option::Option<u64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub source_id: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub source_title: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub source_url: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub start_index: ::std::option::Option<u64>,
    #[serde(rename = "type")]
    pub type_: ::std::string::String,
}
#[doc = "Supervisor's declaration of the supervisor-managed environment slice.\n\nManaged asset entries (`mcp_servers`, `skills`) carry inline connection\nmaterial; no resolver round-trip is needed. The agent dials MCP servers\nand injects skill content directly from these fields at startup.\n\nAnything the agent provides on its own (in-process tools, baked-in\nskills) is invisible to AVP and the Commission entirely. The agent's own\ncontribution surfaces in `agent_described.data[\"avp.descriptor\"]` so\nconsumers can audit what the agent showed up with. The agent's runtime\nlayer merges its internal contribution with the Commission-managed assets\ninto one bag the loop dispatches against; collisions on `id` are a\nstartup error."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Commission\","]
#[doc = "  \"description\": \"Supervisor's declaration of the supervisor-managed environment slice.\\n\\nManaged asset entries (`mcp_servers`, `skills`) carry inline connection\\nmaterial; no resolver round-trip is needed. The agent dials MCP servers\\nand injects skill content directly from these fields at startup.\\n\\nAnything the agent provides on its own (in-process tools, baked-in\\nskills) is invisible to AVP and the Commission entirely. The agent's own\\ncontribution surfaces in `agent_described.data[\\\"avp.descriptor\\\"]` so\\nconsumers can audit what the agent showed up with. The agent's runtime\\nlayer merges its internal contribution with the Commission-managed assets\\ninto one bag the loop dispatches against; collisions on `id` are a\\nstartup error.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"run_id\","]
#[doc = "    \"schema_version\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"enabled_builtin_mcp_servers\": {"]
#[doc = "      \"title\": \"Enabled Builtin Mcp Servers\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"enabled_builtin_skills\": {"]
#[doc = "      \"title\": \"Enabled Builtin Skills\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"enabled_builtin_subagents\": {"]
#[doc = "      \"title\": \"Enabled Builtin Subagents\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"enabled_builtin_tools\": {"]
#[doc = "      \"title\": \"Enabled Builtin Tools\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"mcp_servers\": {"]
#[doc = "      \"title\": \"Mcp Servers\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"oneOf\": ["]
#[doc = "              {"]
#[doc = "                \"$ref\": \"#/$defs/McpServerHttp\""]
#[doc = "              },"]
#[doc = "              {"]
#[doc = "                \"$ref\": \"#/$defs/McpServerStdio\""]
#[doc = "              }"]
#[doc = "            ],"]
#[doc = "            \"discriminator\": {"]
#[doc = "              \"mapping\": {"]
#[doc = "                \"http\": \"#/$defs/McpServerHttp\","]
#[doc = "                \"stdio\": \"#/$defs/McpServerStdio\""]
#[doc = "              },"]
#[doc = "              \"propertyName\": \"type\""]
#[doc = "            }"]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"meta\": {"]
#[doc = "      \"title\": \"Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"model\": {"]
#[doc = "      \"title\": \"Model\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"output_schema\": {"]
#[doc = "      \"title\": \"Output Schema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"prompt\": {"]
#[doc = "      \"title\": \"Prompt\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"run_id\": {"]
#[doc = "      \"title\": \"Run Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"schema_version\": {"]
#[doc = "      \"title\": \"Schema Version\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"0.1\""]
#[doc = "    },"]
#[doc = "    \"skills\": {"]
#[doc = "      \"title\": \"Skills\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/Skill\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"supervisor\": {"]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/SupervisorPreamble\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"system_prompt\": {"]
#[doc = "      \"title\": \"System Prompt\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"tags\": {"]
#[doc = "      \"title\": \"Tags\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"thread_id\": {"]
#[doc = "      \"title\": \"Thread Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Commission {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub enabled_builtin_mcp_servers: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub enabled_builtin_skills: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub enabled_builtin_subagents: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub enabled_builtin_tools: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub mcp_servers: ::std::option::Option<::std::vec::Vec<CommissionMcpServersItem>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub meta: ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub model: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub output_schema:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub prompt: ::std::option::Option<::std::string::String>,
    pub run_id: RunId,
    pub schema_version: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub skills: ::std::option::Option<::std::vec::Vec<Skill>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub supervisor: ::std::option::Option<SupervisorPreamble>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub system_prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tags: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub thread_id: ::std::option::Option<::std::string::String>,
}
#[doc = "`CommissionMcpServersItem`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"oneOf\": ["]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/McpServerHttp\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/McpServerStdio\""]
#[doc = "    }"]
#[doc = "  ],"]
#[doc = "  \"discriminator\": {"]
#[doc = "    \"mapping\": {"]
#[doc = "      \"http\": \"#/$defs/McpServerHttp\","]
#[doc = "      \"stdio\": \"#/$defs/McpServerStdio\""]
#[doc = "    },"]
#[doc = "    \"propertyName\": \"type\""]
#[doc = "  }"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(tag = "type")]
pub enum CommissionMcpServersItem {
    #[serde(rename = "http")]
    Http(McpServerHttp),
    #[serde(rename = "stdio")]
    Stdio(McpServerStdio),

}
impl ::std::convert::From<McpServerHttp> for CommissionMcpServersItem {
    fn from(value: McpServerHttp) -> Self {
        Self::Http(value)
    }
}
impl ::std::convert::From<McpServerStdio> for CommissionMcpServersItem {
    fn from(value: McpServerStdio) -> Self {
        Self::Stdio(value)
    }
}
#[doc = "`Content`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Content\","]
#[doc = "  \"anyOf\": ["]
#[doc = "    {"]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"type\": \"array\","]
#[doc = "      \"items\": {"]
#[doc = "        \"oneOf\": ["]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/TextBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/ImageBlock\""]
#[doc = "          },"]
#[doc = "          {"]
#[doc = "            \"$ref\": \"#/$defs/DocumentBlock\""]
#[doc = "          }"]
#[doc = "        ],"]
#[doc = "        \"discriminator\": {"]
#[doc = "          \"mapping\": {"]
#[doc = "            \"document\": \"#/$defs/DocumentBlock\","]
#[doc = "            \"image\": \"#/$defs/ImageBlock\","]
#[doc = "            \"text\": \"#/$defs/TextBlock\""]
#[doc = "          },"]
#[doc = "          \"propertyName\": \"type\""]
#[doc = "        }"]
#[doc = "      }"]
#[doc = "    }"]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(untagged)]
pub enum Content {
    String(::std::string::String),
    Array(::std::vec::Vec<ContentArrayItem>),
}
impl ::std::convert::From<::std::vec::Vec<ContentArrayItem>> for Content {
    fn from(value: ::std::vec::Vec<ContentArrayItem>) -> Self {
        Self::Array(value)
    }
}
#[doc = "`ContentArrayItem`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"oneOf\": ["]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/TextBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ImageBlock\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/DocumentBlock\""]
#[doc = "    }"]
#[doc = "  ],"]
#[doc = "  \"discriminator\": {"]
#[doc = "    \"mapping\": {"]
#[doc = "      \"document\": \"#/$defs/DocumentBlock\","]
#[doc = "      \"image\": \"#/$defs/ImageBlock\","]
#[doc = "      \"text\": \"#/$defs/TextBlock\""]
#[doc = "    },"]
#[doc = "    \"propertyName\": \"type\""]
#[doc = "  }"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(tag = "type")]
pub enum ContentArrayItem {
    #[serde(rename = "text")]
    TextBlock(TextBlock),
    #[serde(rename = "image")]
    ImageBlock(ImageBlock),
    #[serde(rename = "document")]
    DocumentBlock(DocumentBlock),

}
impl ::std::convert::From<TextBlock> for ContentArrayItem {
    fn from(value: TextBlock) -> Self {
        Self::TextBlock(value)
    }
}
impl ::std::convert::From<ImageBlock> for ContentArrayItem {
    fn from(value: ImageBlock) -> Self {
        Self::ImageBlock(value)
    }
}
impl ::std::convert::From<DocumentBlock> for ContentArrayItem {
    fn from(value: DocumentBlock) -> Self {
        Self::DocumentBlock(value)
    }
}
#[doc = "Document / file content (typically PDFs). Anthropic `document`\n(with citation support), OpenAI `input_file`, Gemini `file_data`,\nBedrock `document`. `title` is the document name used as the\ncitation target; `context` is supplementary metadata Anthropic\nsurfaces alongside the document for the model."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"DocumentBlock\","]
#[doc = "  \"description\": \"Document / file content (typically PDFs). Anthropic `document`\\n(with citation support), OpenAI `input_file`, Gemini `file_data`,\\nBedrock `document`. `title` is the document name used as the\\ncitation target; `context` is supplementary metadata Anthropic\\nsurfaces alongside the document for the model.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"source\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"citations\": {"]
#[doc = "      \"title\": \"Citations\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/Citation\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"context\": {"]
#[doc = "      \"title\": \"Context\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"oneOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/Base64Source\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/UrlSource\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/FileSource\""]
#[doc = "        }"]
#[doc = "      ],"]
#[doc = "      \"discriminator\": {"]
#[doc = "        \"mapping\": {"]
#[doc = "          \"base64\": \"#/$defs/Base64Source\","]
#[doc = "          \"file\": \"#/$defs/FileSource\","]
#[doc = "          \"url\": \"#/$defs/UrlSource\""]
#[doc = "        },"]
#[doc = "        \"propertyName\": \"type\""]
#[doc = "      }"]
#[doc = "    },"]
#[doc = "    \"title\": {"]
#[doc = "      \"title\": \"Title\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"document\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"document\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct DocumentBlock {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub citations: ::std::option::Option<::std::vec::Vec<Citation>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub context: ::std::option::Option<::std::string::String>,
    pub source: Source,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub title: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::document_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ErrorCode`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ErrorCode\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"rate_limit\","]
#[doc = "    \"context_limit\","]
#[doc = "    \"auth_error\","]
#[doc = "    \"agent_crash\","]
#[doc = "    \"unsupported_model\","]
#[doc = "    \"commission_collision\","]
#[doc = "    \"mcp_connect_failed\","]
#[doc = "    \"unknown\""]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum ErrorCode {
    #[serde(rename = "rate_limit")]
    RateLimit,
    #[serde(rename = "context_limit")]
    ContextLimit,
    #[serde(rename = "auth_error")]
    AuthError,
    #[serde(rename = "agent_crash")]
    AgentCrash,
    #[serde(rename = "unsupported_model")]
    UnsupportedModel,
    #[serde(rename = "commission_collision")]
    CommissionCollision,
    #[serde(rename = "mcp_connect_failed")]
    McpConnectFailed,
    #[serde(rename = "unknown")]
    Unknown,
}
impl ::std::fmt::Display for ErrorCode {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::RateLimit => f.write_str("rate_limit"),
            Self::ContextLimit => f.write_str("context_limit"),
            Self::AuthError => f.write_str("auth_error"),
            Self::AgentCrash => f.write_str("agent_crash"),
            Self::UnsupportedModel => f.write_str("unsupported_model"),
            Self::CommissionCollision => f.write_str("commission_collision"),
            Self::McpConnectFailed => f.write_str("mcp_connect_failed"),
            Self::Unknown => f.write_str("unknown"),
        }
    }
}
impl ::std::str::FromStr for ErrorCode {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "rate_limit" => Ok(Self::RateLimit),
            "context_limit" => Ok(Self::ContextLimit),
            "auth_error" => Ok(Self::AuthError),
            "agent_crash" => Ok(Self::AgentCrash),
            "unsupported_model" => Ok(Self::UnsupportedModel),
            "commission_collision" => Ok(Self::CommissionCollision),
            "mcp_connect_failed" => Ok(Self::McpConnectFailed),
            "unknown" => Ok(Self::Unknown),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for ErrorCode {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ErrorCode {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ErrorCode {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`ErrorOccurredData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ErrorOccurredData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.error.code\","]
#[doc = "    \"avp.error.message\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.error.code\": {"]
#[doc = "      \"$ref\": \"#/$defs/ErrorCode\""]
#[doc = "    },"]
#[doc = "    \"avp.error.message\": {"]
#[doc = "      \"title\": \"Avp.Error.Message\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ErrorOccurredData {
    #[serde(rename = "avp.error.code")]
    pub avp_error_code: ErrorCode,
    #[serde(rename = "avp.error.message")]
    pub avp_error_message: ::std::string::String,
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`ErrorOccurredEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ErrorOccurredEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/ErrorOccurredData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.error_occurred\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.error_occurred\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ErrorOccurredEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<ErrorOccurredEventAvpCorrelationId>,
    pub data: ErrorOccurredData,
    #[serde(default = "defaults::error_occurred_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::error_occurred_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::error_occurred_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ErrorOccurredEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::error_occurred_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ErrorOccurredEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ErrorOccurredEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for ErrorOccurredEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ErrorOccurredEventAvpCorrelationId> for ::std::string::String {
    fn from(value: ErrorOccurredEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ErrorOccurredEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ErrorOccurredEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ErrorOccurredEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ErrorOccurredEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ErrorOccurredEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`ErrorOccurredEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ErrorOccurredEventSubject(::std::string::String);
impl ::std::ops::Deref for ErrorOccurredEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ErrorOccurredEventSubject> for ::std::string::String {
    fn from(value: ErrorOccurredEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ErrorOccurredEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ErrorOccurredEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ErrorOccurredEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ErrorOccurredEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ErrorOccurredEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Provider-hosted file reference. OpenAI Files API `file_id`, Anthropic\nFiles API `file_id`, Gemini `file_data.file_uri` (Files API URI)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"FileSource\","]
#[doc = "  \"description\": \"Provider-hosted file reference. OpenAI Files API `file_id`, Anthropic\\nFiles API `file_id`, Gemini `file_data.file_uri` (Files API URI).\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"file_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"file_id\": {"]
#[doc = "      \"title\": \"File Id\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"file\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"file\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct FileSource {
    pub file_id: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::file_source_type")]
    pub type_: ::std::string::String,
}
#[doc = "`Id`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct Id(::std::string::String);
impl ::std::ops::Deref for Id {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<Id> for ::std::string::String {
    fn from(value: Id) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for Id {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for Id {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for Id {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Id {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for Id {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Image content. Anthropic `image`, OpenAI `image_url` /\n`input_image`, Gemini `inline_data` / `file_data` image, Bedrock\n`image`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ImageBlock\","]
#[doc = "  \"description\": \"Image content. Anthropic `image`, OpenAI `image_url` /\\n`input_image`, Gemini `inline_data` / `file_data` image, Bedrock\\n`image`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"source\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"oneOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/Base64Source\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/UrlSource\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/FileSource\""]
#[doc = "        }"]
#[doc = "      ],"]
#[doc = "      \"discriminator\": {"]
#[doc = "        \"mapping\": {"]
#[doc = "          \"base64\": \"#/$defs/Base64Source\","]
#[doc = "          \"file\": \"#/$defs/FileSource\","]
#[doc = "          \"url\": \"#/$defs/UrlSource\""]
#[doc = "        },"]
#[doc = "        \"propertyName\": \"type\""]
#[doc = "      }"]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"image\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"image\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ImageBlock {
    pub source: Source,
    #[serde(rename = "type", skip_serializing, default = "defaults::image_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "MCP server descriptor in `AgentDescriptor.mcp_servers` and\n`agent_started.data[\"avp.mcp_servers\"]`: identity + terminal dial status.\n\nConnection material (URLs, auth, command-lines) stays inside the agent\nprocess and is NOT carried on the descriptor wire. The descriptor\nrecords the server's id, optional display name, optional description,\nand the terminal dial status when known. The tools the server surfaces\nare enumerated in the sibling `tools[]` list with `avp.mcp_server_id`\nset to this server's `id`; only `status: \"connected\"` servers\ncontribute tools.\n\n`id` is the agent's correlation key for this server across the wire\n(descriptor entry, tool entry's `avp.mcp_server_id`). It is intentionally\nlooser than `Commission.McpServerRef.id`: the descriptor enumerates BOTH\nCommission-resolved servers (where `id` is the supervisor-authored slug)\nAND agent-baked-in / environment-resident servers (where `id` is whatever\nthe environment names them, e.g. `\"claude.ai Dashboard Builder\"`). Forcing\na slug here would either lose fidelity or require every agent to invent\nthe same slugification rule. Commission-authored ids stay slug-clean by\nvirtue of `Commission.McpServerRef.id`'s pattern; descriptor ids must\nonly be non-empty.\n\n`name` is the display name when the environment provides one distinct\nfrom `id` (typical for Commission-resolved servers: `id` is the\nCommission slug, `name` is the human-readable label from the resolved\nconfig). For environment-resident servers whose only identifier is\nthe display name, `id` carries that string and `name` is omitted.\n\n`status` records the dial outcome at startup. Pre-flight `<agent> describe`\nMAY omit it (no dial has happened); on-the-wire `agent_described` and\n`agent_started` populate it. Values mirror the Claude Agent SDK's\n`McpServerStatus.status` enum."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerDecl\","]
#[doc = "  \"description\": \"MCP server descriptor in `AgentDescriptor.mcp_servers` and\\n`agent_started.data[\\\"avp.mcp_servers\\\"]`: identity + terminal dial status.\\n\\nConnection material (URLs, auth, command-lines) stays inside the agent\\nprocess and is NOT carried on the descriptor wire. The descriptor\\nrecords the server's id, optional display name, optional description,\\nand the terminal dial status when known. The tools the server surfaces\\nare enumerated in the sibling `tools[]` list with `avp.mcp_server_id`\\nset to this server's `id`; only `status: \\\"connected\\\"` servers\\ncontribute tools.\\n\\n`id` is the agent's correlation key for this server across the wire\\n(descriptor entry, tool entry's `avp.mcp_server_id`). It is intentionally\\nlooser than `Commission.McpServerRef.id`: the descriptor enumerates BOTH\\nCommission-resolved servers (where `id` is the supervisor-authored slug)\\nAND agent-baked-in / environment-resident servers (where `id` is whatever\\nthe environment names them, e.g. `\\\"claude.ai Dashboard Builder\\\"`). Forcing\\na slug here would either lose fidelity or require every agent to invent\\nthe same slugification rule. Commission-authored ids stay slug-clean by\\nvirtue of `Commission.McpServerRef.id`'s pattern; descriptor ids must\\nonly be non-empty.\\n\\n`name` is the display name when the environment provides one distinct\\nfrom `id` (typical for Commission-resolved servers: `id` is the\\nCommission slug, `name` is the human-readable label from the resolved\\nconfig). For environment-resident servers whose only identifier is\\nthe display name, `id` carries that string and `name` is omitted.\\n\\n`status` records the dial outcome at startup. Pre-flight `<agent> describe`\\nMAY omit it (no dial has happened); on-the-wire `agent_described` and\\n`agent_started` populate it. Values mirror the Claude Agent SDK's\\n`McpServerStatus.status` enum.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"description\": {"]
#[doc = "      \"title\": \"Description\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"status\": {"]
#[doc = "      \"title\": \"Status\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"enum\": ["]
#[doc = "            \"connected\","]
#[doc = "            \"failed\","]
#[doc = "            \"needs-auth\","]
#[doc = "            \"pending\","]
#[doc = "            \"disabled\""]
#[doc = "          ]"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct McpServerDecl {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub description: ::std::option::Option<::std::string::String>,
    pub id: Id,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub name: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub status: ::std::option::Option<McpServerDeclStatus>,
}
#[doc = "`McpServerDeclStatus`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"connected\","]
#[doc = "    \"failed\","]
#[doc = "    \"needs-auth\","]
#[doc = "    \"pending\","]
#[doc = "    \"disabled\""]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum McpServerDeclStatus {
    #[serde(rename = "connected")]
    Connected,
    #[serde(rename = "failed")]
    Failed,
    #[serde(rename = "needs-auth")]
    NeedsAuth,
    #[serde(rename = "pending")]
    Pending,
    #[serde(rename = "disabled")]
    Disabled,
}
impl ::std::fmt::Display for McpServerDeclStatus {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Connected => f.write_str("connected"),
            Self::Failed => f.write_str("failed"),
            Self::NeedsAuth => f.write_str("needs-auth"),
            Self::Pending => f.write_str("pending"),
            Self::Disabled => f.write_str("disabled"),
        }
    }
}
impl ::std::str::FromStr for McpServerDeclStatus {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "connected" => Ok(Self::Connected),
            "failed" => Ok(Self::Failed),
            "needs-auth" => Ok(Self::NeedsAuth),
            "pending" => Ok(Self::Pending),
            "disabled" => Ok(Self::Disabled),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for McpServerDeclStatus {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for McpServerDeclStatus {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for McpServerDeclStatus {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "Inline HTTP MCP server entry in Commission.mcp_servers."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerHttp\","]
#[doc = "  \"description\": \"Inline HTTP MCP server entry in Commission.mcp_servers.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\","]
#[doc = "    \"type\","]
#[doc = "    \"url\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"headers\": {"]
#[doc = "      \"title\": \"Headers\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9_-]+$\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"http\""]
#[doc = "    },"]
#[doc = "    \"url\": {"]
#[doc = "      \"title\": \"Url\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct McpServerHttp {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub headers: ::std::option::Option<
        ::std::collections::HashMap<::std::string::String, ::std::string::String>,
    >,
    pub id: Id,
    #[serde(rename = "type", skip_serializing, default)]
    pub type_: ::std::string::String,
    pub url: Url,
}
#[doc = "Inline stdio MCP server entry in Commission.mcp_servers."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerStdio\","]
#[doc = "  \"description\": \"Inline stdio MCP server entry in Commission.mcp_servers.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"command\","]
#[doc = "    \"id\","]
#[doc = "    \"type\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"args\": {"]
#[doc = "      \"title\": \"Args\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"command\": {"]
#[doc = "      \"title\": \"Command\","]
#[doc = "      \"type\": \"array\","]
#[doc = "      \"items\": {"]
#[doc = "        \"type\": \"string\""]
#[doc = "      },"]
#[doc = "      \"minItems\": 1"]
#[doc = "    },"]
#[doc = "    \"env\": {"]
#[doc = "      \"title\": \"Env\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": {"]
#[doc = "            \"type\": \"string\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9_-]+$\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"stdio\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct McpServerStdio {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub args: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    pub command: ::std::vec::Vec<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub env: ::std::option::Option<
        ::std::collections::HashMap<::std::string::String, ::std::string::String>,
    >,
    pub id: Id,
    #[serde(rename = "type", skip_serializing, default)]
    pub type_: ::std::string::String,
}
#[doc = "`Name`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Name\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct Name(::std::string::String);
impl ::std::ops::Deref for Name {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<Name> for ::std::string::String {
    fn from(value: Name) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for Name {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for Name {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for Name {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Name {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for Name {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`ParentSpanId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Parent Span Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"maxLength\": 16,"]
#[doc = "  \"minLength\": 16,"]
#[doc = "  \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ParentSpanId(::std::string::String);
impl ::std::ops::Deref for ParentSpanId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ParentSpanId> for ::std::string::String {
    fn from(value: ParentSpanId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ParentSpanId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() > 16usize {
            return Err("longer than 16 characters".into());
        }
        if value.chars().count() < 16usize {
            return Err("shorter than 16 characters".into());
        }
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| ::regress::Regex::new("^[0-9a-f]{16}$").unwrap());
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[0-9a-f]{16}$\"".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ParentSpanId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ParentSpanId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ParentSpanId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ParentSpanId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Structured refusal distinct from generated text. OpenAI assistant\nmessage `refusal` field and Responses `output_refusal` item. Other\nproviders emit refusals as plain text plus a finish reason; this\nblock represents only providers that ship a typed refusal."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RefusalBlock\","]
#[doc = "  \"description\": \"Structured refusal distinct from generated text. OpenAI assistant\\nmessage `refusal` field and Responses `output_refusal` item. Other\\nproviders emit refusals as plain text plus a finish reason; this\\nblock represents only providers that ship a typed refusal.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"refusal\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"refusal\": {"]
#[doc = "      \"title\": \"Refusal\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"refusal\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"refusal\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct RefusalBlock {
    pub refusal: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::refusal_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "`RunId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Run Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct RunId(::std::string::String);
impl ::std::ops::Deref for RunId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<RunId> for ::std::string::String {
    fn from(value: RunId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for RunId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for RunId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for RunId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for RunId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for RunId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Payload of avp.run_requested events.\n\nAnchors the trajectory. When relaying a Commission, carries the full\nsnapshot under `avp.commission` plus `avp.supervisor.*` for attribution,\nmaking the trajectory self-contained for audit. Without a Commission\n(library-invocation path), those fields are absent — per spec §2.1,\nabsence (not `\"unknown\"`) is the canonical signal."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RunRequestedData\","]
#[doc = "  \"description\": \"Payload of avp.run_requested events.\\n\\nAnchors the trajectory. When relaying a Commission, carries the full\\nsnapshot under `avp.commission` plus `avp.supervisor.*` for attribution,\\nmaking the trajectory self-contained for audit. Without a Commission\\n(library-invocation path), those fields are absent — per spec §2.1,\\nabsence (not `\\\"unknown\\\"`) is the canonical signal.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.commission\": {"]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/Commission\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.supervisor.name\": {"]
#[doc = "      \"title\": \"Avp.Supervisor.Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.supervisor.version\": {"]
#[doc = "      \"title\": \"Avp.Supervisor.Version\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct RunRequestedData {
    #[serde(
        rename = "avp.commission",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_commission: ::std::option::Option<Commission>,
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(
        rename = "avp.supervisor.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_supervisor_name: ::std::option::Option<RunRequestedDataAvpSupervisorName>,
    #[serde(
        rename = "avp.supervisor.version",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_supervisor_version: ::std::option::Option<::std::string::String>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`RunRequestedDataAvpSupervisorName`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct RunRequestedDataAvpSupervisorName(::std::string::String);
impl ::std::ops::Deref for RunRequestedDataAvpSupervisorName {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<RunRequestedDataAvpSupervisorName> for ::std::string::String {
    fn from(value: RunRequestedDataAvpSupervisorName) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for RunRequestedDataAvpSupervisorName {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for RunRequestedDataAvpSupervisorName {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for RunRequestedDataAvpSupervisorName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for RunRequestedDataAvpSupervisorName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for RunRequestedDataAvpSupervisorName {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "First event of the trajectory. The agent is the sole producer on the\nwire (spec §8 conformance #1), so `source` is `avp://agent`. Supervisor\nattribution, when a Commission is in use, lives inside `data` as\n`avp.supervisor.*` plus the full `avp.commission` snapshot — that's what\nmakes the trajectory self-contained for audit without resort to the\nenvelope's `source` field."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RunRequestedEvent\","]
#[doc = "  \"description\": \"First event of the trajectory. The agent is the sole producer on the\\nwire (spec §8 conformance #1), so `source` is `avp://agent`. Supervisor\\nattribution, when a Commission is in use, lives inside `data` as\\n`avp.supervisor.*` plus the full `avp.commission` snapshot — that's what\\nmakes the trajectory self-contained for audit without resort to the\\nenvelope's `source` field.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/RunRequestedData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.run_requested\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.run_requested\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct RunRequestedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<RunRequestedEventAvpCorrelationId>,
    pub data: RunRequestedData,
    #[serde(default = "defaults::run_requested_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::run_requested_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::run_requested_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<RunRequestedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::run_requested_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`RunRequestedEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct RunRequestedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for RunRequestedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<RunRequestedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: RunRequestedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for RunRequestedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for RunRequestedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for RunRequestedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for RunRequestedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for RunRequestedEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`RunRequestedEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct RunRequestedEventSubject(::std::string::String);
impl ::std::ops::Deref for RunRequestedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<RunRequestedEventSubject> for ::std::string::String {
    fn from(value: RunRequestedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for RunRequestedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for RunRequestedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for RunRequestedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for RunRequestedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for RunRequestedEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Result of a provider-executed built-in tool. Pairs with\n`ServerToolUseBlock`. Anthropic `web_search_tool_result`, OpenAI\nResponses `*_call_output`, Gemini `code_execution_result`.\n`content` is provider-shaped (search-result rows, code stdout,\ncomputer-use screenshots, ...)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ServerToolResultBlock\","]
#[doc = "  \"description\": \"Result of a provider-executed built-in tool. Pairs with\\n`ServerToolUseBlock`. Anthropic `web_search_tool_result`, OpenAI\\nResponses `*_call_output`, Gemini `code_execution_result`.\\n`content` is provider-shaped (search-result rows, code stdout,\\ncomputer-use screenshots, ...).\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"content\","]
#[doc = "    \"name\","]
#[doc = "    \"tool_use_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"content\": {"]
#[doc = "      \"title\": \"Content\""]
#[doc = "    },"]
#[doc = "    \"is_error\": {"]
#[doc = "      \"title\": \"Is Error\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"boolean\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"tool_use_id\": {"]
#[doc = "      \"title\": \"Tool Use Id\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"server_tool_result\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"server_tool_result\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ServerToolResultBlock {
    pub content: ::serde_json::Value,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub is_error: ::std::option::Option<bool>,
    pub name: ::std::string::String,
    pub tool_use_id: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::server_tool_result_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "Built-in tool executed by the provider rather than the agent.\nAnthropic `server_tool_use` (web_search, code_execution), OpenAI\nResponses `web_search_call` / `file_search_call` / `computer_call` /\n`code_interpreter_call`, Gemini `executable_code` / `google_search`.\n`name` carries the tool kind (e.g. \"web_search\", \"code_interpreter\",\n\"computer_use\", \"google_search\"). Distinct from `tool_use` because\nthe agent never dispatches these; they are observability of a\nprovider-side action."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ServerToolUseBlock\","]
#[doc = "  \"description\": \"Built-in tool executed by the provider rather than the agent.\\nAnthropic `server_tool_use` (web_search, code_execution), OpenAI\\nResponses `web_search_call` / `file_search_call` / `computer_call` /\\n`code_interpreter_call`, Gemini `executable_code` / `google_search`.\\n`name` carries the tool kind (e.g. \\\"web_search\\\", \\\"code_interpreter\\\",\\n\\\"computer_use\\\", \\\"google_search\\\"). Distinct from `tool_use` because\\nthe agent never dispatches these; they are observability of a\\nprovider-side action.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\","]
#[doc = "    \"input\","]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"input\": {"]
#[doc = "      \"title\": \"Input\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"server_tool_use\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"server_tool_use\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ServerToolUseBlock {
    pub id: ::std::string::String,
    pub input: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    pub name: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::server_tool_use_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "Inline skill entry in Commission.skills."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Skill\","]
#[doc = "  \"description\": \"Inline skill entry in Commission.skills.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"files\","]
#[doc = "    \"id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"files\": {"]
#[doc = "      \"title\": \"Files\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": {"]
#[doc = "        \"type\": \"string\""]
#[doc = "      }"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9_-]+$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Skill {
    pub files: ::std::collections::HashMap<::std::string::String, ::std::string::String>,
    pub id: Id,
}
#[doc = "Skill descriptor in `AgentDescriptor.skills` and\n`agent_started.data[\"avp.skills\"]`: name plus optional metadata about each\nskill the agent ships with or has loaded for the run.\n\nReplaces the v0.1-prototype `list[str]` shape (names-only) with a\nstructured decl matching `ToolDecl` / `SubagentDecl`. Description\ncomes from the SKILL.md frontmatter when the agent surfaces it\n(e.g. via `ClaudeSDKClient.get_context_usage()` which returns a\n`skills` breakdown including frontmatter); `version` is the skill's\nown version when known; `avp.source` is the SKILL.md path / URI.\n\nAll fields except `name` are optional so agents that only know\nthe name (Commission-declared without enrichment) still emit valid\ndecls."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SkillDecl\","]
#[doc = "  \"description\": \"Skill descriptor in `AgentDescriptor.skills` and\\n`agent_started.data[\\\"avp.skills\\\"]`: name plus optional metadata about each\\nskill the agent ships with or has loaded for the run.\\n\\nReplaces the v0.1-prototype `list[str]` shape (names-only) with a\\nstructured decl matching `ToolDecl` / `SubagentDecl`. Description\\ncomes from the SKILL.md frontmatter when the agent surfaces it\\n(e.g. via `ClaudeSDKClient.get_context_usage()` which returns a\\n`skills` breakdown including frontmatter); `version` is the skill's\\nown version when known; `avp.source` is the SKILL.md path / URI.\\n\\nAll fields except `name` are optional so agents that only know\\nthe name (Commission-declared without enrichment) still emit valid\\ndecls.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.source\": {"]
#[doc = "      \"title\": \"Avp.Source\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"description\": {"]
#[doc = "      \"title\": \"Description\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"version\": {"]
#[doc = "      \"title\": \"Version\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct SkillDecl {
    #[serde(
        rename = "avp.source",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_source: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub description: ::std::option::Option<::std::string::String>,
    pub name: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub version: ::std::option::Option<::std::string::String>,
}
#[doc = "`Source`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Source\","]
#[doc = "  \"oneOf\": ["]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/Base64Source\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/UrlSource\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/FileSource\""]
#[doc = "    }"]
#[doc = "  ],"]
#[doc = "  \"discriminator\": {"]
#[doc = "    \"mapping\": {"]
#[doc = "      \"base64\": \"#/$defs/Base64Source\","]
#[doc = "      \"file\": \"#/$defs/FileSource\","]
#[doc = "      \"url\": \"#/$defs/UrlSource\""]
#[doc = "    },"]
#[doc = "    \"propertyName\": \"type\""]
#[doc = "  }"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(tag = "type")]
pub enum Source {
    #[serde(rename = "base64")]
    Base64Source(Base64Source),
    #[serde(rename = "url")]
    UrlSource(UrlSource),
    #[serde(rename = "file")]
    FileSource(FileSource),

}
impl ::std::convert::From<Base64Source> for Source {
    fn from(value: Base64Source) -> Self {
        Self::Base64Source(value)
    }
}
impl ::std::convert::From<UrlSource> for Source {
    fn from(value: UrlSource) -> Self {
        Self::UrlSource(value)
    }
}
impl ::std::convert::From<FileSource> for Source {
    fn from(value: FileSource) -> Self {
        Self::FileSource(value)
    }
}
#[doc = "`SpanId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Span Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"maxLength\": 16,"]
#[doc = "  \"minLength\": 16,"]
#[doc = "  \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct SpanId(::std::string::String);
impl ::std::ops::Deref for SpanId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SpanId> for ::std::string::String {
    fn from(value: SpanId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SpanId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() > 16usize {
            return Err("longer than 16 characters".into());
        }
        if value.chars().count() < 16usize {
            return Err("shorter than 16 characters".into());
        }
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| ::regress::Regex::new("^[0-9a-f]{16}$").unwrap());
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[0-9a-f]{16}$\"".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SpanId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SpanId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SpanId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SpanId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Why a run terminated. v0.1 keeps the enum tight: model said done,\nmodel declined, agent crashed, or operator interrupted. Cap-driven\nstop reasons (turn / token / cost / duration limits) are not part of\nv0.1; agents that need bounded execution wire it externally\n(subprocess timeouts, supervisor SIGKILL)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"StopReason\","]
#[doc = "  \"description\": \"Why a run terminated. v0.1 keeps the enum tight: model said done,\\nmodel declined, agent crashed, or operator interrupted. Cap-driven\\nstop reasons (turn / token / cost / duration limits) are not part of\\nv0.1; agents that need bounded execution wire it externally\\n(subprocess timeouts, supervisor SIGKILL).\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"converged\","]
#[doc = "    \"error\","]
#[doc = "    \"interrupted\","]
#[doc = "    \"refused\""]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum StopReason {
    #[serde(rename = "converged")]
    Converged,
    #[serde(rename = "error")]
    Error,
    #[serde(rename = "interrupted")]
    Interrupted,
    #[serde(rename = "refused")]
    Refused,
}
impl ::std::fmt::Display for StopReason {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Converged => f.write_str("converged"),
            Self::Error => f.write_str("error"),
            Self::Interrupted => f.write_str("interrupted"),
            Self::Refused => f.write_str("refused"),
        }
    }
}
impl ::std::str::FromStr for StopReason {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "converged" => Ok(Self::Converged),
            "error" => Ok(Self::Error),
            "interrupted" => Ok(Self::Interrupted),
            "refused" => Ok(Self::Refused),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for StopReason {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for StopReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for StopReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "Subagent descriptor in `agent_started.data[\"avp.subagents\"]`: what the\nparent model sees when deciding whether to delegate. Same MCP-shaped\ntriple (`name`, `description`, `inputSchema`) tools use, so adapters\ncan render subagents to the model's tool list with no translation.\n\n`description` is optional to match `ToolDecl`: when surfacing a\nagent-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)\nthe agent has authoritative knowledge of the name but not the prose\ndescription. Honest-null beats authored-prose-that-drifts."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentDecl\","]
#[doc = "  \"description\": \"Subagent descriptor in `agent_started.data[\\\"avp.subagents\\\"]`: what the\\nparent model sees when deciding whether to delegate. Same MCP-shaped\\ntriple (`name`, `description`, `inputSchema`) tools use, so adapters\\ncan render subagents to the model's tool list with no translation.\\n\\n`description` is optional to match `ToolDecl`: when surfacing a\\nagent-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)\\nthe agent has authoritative knowledge of the name but not the prose\\ndescription. Honest-null beats authored-prose-that-drifts.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.agent_type\": {"]
#[doc = "      \"title\": \"Avp.Agent Type\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"description\": {"]
#[doc = "      \"title\": \"Description\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"inputSchema\": {"]
#[doc = "      \"title\": \"Inputschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct SubagentDecl {
    #[serde(
        rename = "avp.agent_type",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_agent_type: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub description: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "inputSchema",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub input_schema:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    pub name: ::std::string::String,
}
#[doc = "Parent agent delegates to a declared subagent.\n\nThe event's `span_id` IS the subagent's frame span. Events emitted by\nthe subagent's sub-loop set `parent_span_id` to this frame (or chain\nthrough descendants of it), so the trajectory reconstructs as a nested\ntree. The subagent's declared name surfaces on `avp.subagent.name`;\nthe event type itself signals an `invoke_agent`-style operation, so no\nseparate operation-name field is carried on the wire.\n\n`avp.subagent.run_id` is reserved for future use when the subagent runs\nas a separate commissioned trajectory. Absent for in-process subagents."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentInvokedData\","]
#[doc = "  \"description\": \"Parent agent delegates to a declared subagent.\\n\\nThe event's `span_id` IS the subagent's frame span. Events emitted by\\nthe subagent's sub-loop set `parent_span_id` to this frame (or chain\\nthrough descendants of it), so the trajectory reconstructs as a nested\\ntree. The subagent's declared name surfaces on `avp.subagent.name`;\\nthe event type itself signals an `invoke_agent`-style operation, so no\\nseparate operation-name field is carried on the wire.\\n\\n`avp.subagent.run_id` is reserved for future use when the subagent runs\\nas a separate commissioned trajectory. Absent for in-process subagents.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.step\","]
#[doc = "    \"avp.subagent.input\","]
#[doc = "    \"avp.subagent.invocation_id\","]
#[doc = "    \"avp.subagent.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.step\": {"]
#[doc = "      \"title\": \"Avp.Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.subagent.description\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Description\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.subagent.input\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Input\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    },"]
#[doc = "    \"avp.subagent.invocation_id\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Invocation Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"avp.subagent.name\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.subagent.run_id\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Run Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct SubagentInvokedData {
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(rename = "avp.step")]
    pub avp_step: u64,
    #[serde(
        rename = "avp.subagent.description",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_subagent_description: ::std::option::Option<::std::string::String>,
    #[serde(rename = "avp.subagent.input")]
    pub avp_subagent_input: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    #[serde(rename = "avp.subagent.invocation_id")]
    pub avp_subagent_invocation_id: AvpSubagentInvocationId,
    #[serde(rename = "avp.subagent.name")]
    pub avp_subagent_name: ::std::string::String,
    #[serde(
        rename = "avp.subagent.run_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_subagent_run_id: ::std::option::Option<SubagentInvokedDataAvpSubagentRunId>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`SubagentInvokedDataAvpSubagentRunId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct SubagentInvokedDataAvpSubagentRunId(::std::string::String);
impl ::std::ops::Deref for SubagentInvokedDataAvpSubagentRunId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentInvokedDataAvpSubagentRunId> for ::std::string::String {
    fn from(value: SubagentInvokedDataAvpSubagentRunId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentInvokedDataAvpSubagentRunId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentInvokedDataAvpSubagentRunId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentInvokedDataAvpSubagentRunId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentInvokedDataAvpSubagentRunId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentInvokedDataAvpSubagentRunId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`SubagentInvokedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentInvokedEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/SubagentInvokedData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.subagent_invoked\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.subagent_invoked\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SubagentInvokedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<SubagentInvokedEventAvpCorrelationId>,
    pub data: SubagentInvokedData,
    #[serde(default = "defaults::subagent_invoked_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::subagent_invoked_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::subagent_invoked_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<SubagentInvokedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::subagent_invoked_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`SubagentInvokedEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct SubagentInvokedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for SubagentInvokedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentInvokedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: SubagentInvokedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentInvokedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentInvokedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentInvokedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentInvokedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentInvokedEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`SubagentInvokedEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct SubagentInvokedEventSubject(::std::string::String);
impl ::std::ops::Deref for SubagentInvokedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentInvokedEventSubject> for ::std::string::String {
    fn from(value: SubagentInvokedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentInvokedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentInvokedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentInvokedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentInvokedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentInvokedEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Closes the subagent's frame. `span_id` matches the corresponding\n`subagent_invoked` event so consumers can pair them.\n\n`avp.subagent.reason` is a `StopReason`; on the error path,\n`reason = error` and `avp.subagent.result.text` carries the error\nstring. The paired `tool_returned` mirrors this: `is_error = true`\nwhen `reason = error`, with the same `Error: ...` content.\n\n`avp.subagent.usage` is OPTIONAL and intended only for the in-process\nfallback: parent agents whose SDK black-boxes the child loop (no\nper-turn AssistantMessages exposed to the parent) carry the child's\ntotals here as the only signal the supervisor receives of the child's\nspend. Agents that emit the child's per-turn events into the parent's\ntrajectory with proper span parentage (`parent_span_id` = this event's\n`span_id`) MUST omit this field; the supervisor reconstructs from the\nraw stream. Managed subagents (separate `run_id`, separate trajectory)\nMUST also omit it; the supervisor reads the child's trajectory."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentReturnedData\","]
#[doc = "  \"description\": \"Closes the subagent's frame. `span_id` matches the corresponding\\n`subagent_invoked` event so consumers can pair them.\\n\\n`avp.subagent.reason` is a `StopReason`; on the error path,\\n`reason = error` and `avp.subagent.result.text` carries the error\\nstring. The paired `tool_returned` mirrors this: `is_error = true`\\nwhen `reason = error`, with the same `Error: ...` content.\\n\\n`avp.subagent.usage` is OPTIONAL and intended only for the in-process\\nfallback: parent agents whose SDK black-boxes the child loop (no\\nper-turn AssistantMessages exposed to the parent) carry the child's\\ntotals here as the only signal the supervisor receives of the child's\\nspend. Agents that emit the child's per-turn events into the parent's\\ntrajectory with proper span parentage (`parent_span_id` = this event's\\n`span_id`) MUST omit this field; the supervisor reconstructs from the\\nraw stream. Managed subagents (separate `run_id`, separate trajectory)\\nMUST also omit it; the supervisor reads the child's trajectory.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.duration_ms\","]
#[doc = "    \"avp.step\","]
#[doc = "    \"avp.subagent.invocation_id\","]
#[doc = "    \"avp.subagent.name\","]
#[doc = "    \"avp.subagent.reason\","]
#[doc = "    \"avp.subagent.result.text\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.duration_ms\": {"]
#[doc = "      \"title\": \"Avp.Duration Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.step\": {"]
#[doc = "      \"title\": \"Avp.Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.subagent.invocation_id\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Invocation Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"avp.subagent.name\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.subagent.reason\": {"]
#[doc = "      \"$ref\": \"#/$defs/StopReason\""]
#[doc = "    },"]
#[doc = "    \"avp.subagent.result.structured\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Result.Structured\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {},"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.subagent.result.text\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Result.Text\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.subagent.usage\": {"]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/SubagentUsage\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct SubagentReturnedData {
    #[serde(rename = "avp.duration_ms")]
    pub avp_duration_ms: u64,
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(rename = "avp.step")]
    pub avp_step: u64,
    #[serde(rename = "avp.subagent.invocation_id")]
    pub avp_subagent_invocation_id: AvpSubagentInvocationId,
    #[serde(rename = "avp.subagent.name")]
    pub avp_subagent_name: ::std::string::String,
    #[serde(rename = "avp.subagent.reason")]
    pub avp_subagent_reason: StopReason,
    #[serde(
        rename = "avp.subagent.result.structured",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_subagent_result_structured: ::std::option::Option<::serde_json::Value>,
    #[serde(rename = "avp.subagent.result.text")]
    pub avp_subagent_result_text: ::std::string::String,
    #[serde(
        rename = "avp.subagent.usage",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_subagent_usage: ::std::option::Option<SubagentUsage>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`SubagentReturnedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentReturnedEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/SubagentReturnedData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.subagent_returned\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.subagent_returned\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SubagentReturnedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<SubagentReturnedEventAvpCorrelationId>,
    pub data: SubagentReturnedData,
    #[serde(default = "defaults::subagent_returned_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::subagent_returned_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::subagent_returned_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<SubagentReturnedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::subagent_returned_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`SubagentReturnedEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct SubagentReturnedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for SubagentReturnedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentReturnedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: SubagentReturnedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentReturnedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentReturnedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentReturnedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentReturnedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentReturnedEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`SubagentReturnedEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct SubagentReturnedEventSubject(::std::string::String);
impl ::std::ops::Deref for SubagentReturnedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentReturnedEventSubject> for ::std::string::String {
    fn from(value: SubagentReturnedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentReturnedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentReturnedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentReturnedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentReturnedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentReturnedEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Narrow totals carrier for the in-process subagent rollup.\n\nUsed ONLY on `subagent_returned.data[\"avp.subagent.usage\"]` when the\nparent agent's SDK does not expose the child's per-turn events (e.g.\nClaude Agent SDK's Task tool). `extra=\"allow\"` so SDK-specific fields\n(total_tokens, tool_uses, duration_ms) round-trip verbatim."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentUsage\","]
#[doc = "  \"description\": \"Narrow totals carrier for the in-process subagent rollup.\\n\\nUsed ONLY on `subagent_returned.data[\\\"avp.subagent.usage\\\"]` when the\\nparent agent's SDK does not expose the child's per-turn events (e.g.\\nClaude Agent SDK's Task tool). `extra=\\\"allow\\\"` so SDK-specific fields\\n(total_tokens, tool_uses, duration_ms) round-trip verbatim.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"cost_usd\","]
#[doc = "    \"tokens_input\","]
#[doc = "    \"tokens_output\","]
#[doc = "    \"turns\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"cost_usd\": {"]
#[doc = "      \"title\": \"Cost Usd\","]
#[doc = "      \"type\": \"number\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"tokens_input\": {"]
#[doc = "      \"title\": \"Tokens Input\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"tokens_output\": {"]
#[doc = "      \"title\": \"Tokens Output\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"turns\": {"]
#[doc = "      \"title\": \"Turns\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct SubagentUsage {
    pub cost_usd: f64,
    pub tokens_input: u64,
    pub tokens_output: u64,
    pub turns: u64,
}
#[doc = "Identifies the supervisor that is requesting the run.\n\nCarried inside `Commission.supervisor` and projected onto the\n`run_requested` event's `data` (`avp.supervisor.name` +\n`avp.supervisor.version`) so a trajectory consumer can attribute the\nrun to the originating supervisor without an out-of-band lookup. The\nevent's `source` is `avp://agent` (the agent is the sole producer on\nthe wire); supervisor attribution lives inside `data`.\n\n`name` SHOULD be a stable identifier for the supervisor implementation\nor instance (e.g. `\"avp-cli\"`, `\"acme.scheduler\"`).\n`version` is optional but recommended; it travels with the trajectory\nand lets auditors correlate a run with the exact supervisor build\nthat requested it."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SupervisorPreamble\","]
#[doc = "  \"description\": \"Identifies the supervisor that is requesting the run.\\n\\nCarried inside `Commission.supervisor` and projected onto the\\n`run_requested` event's `data` (`avp.supervisor.name` +\\n`avp.supervisor.version`) so a trajectory consumer can attribute the\\nrun to the originating supervisor without an out-of-band lookup. The\\nevent's `source` is `avp://agent` (the agent is the sole producer on\\nthe wire); supervisor attribution lives inside `data`.\\n\\n`name` SHOULD be a stable identifier for the supervisor implementation\\nor instance (e.g. `\\\"avp-cli\\\"`, `\\\"acme.scheduler\\\"`).\\n`version` is optional but recommended; it travels with the trajectory\\nand lets auditors correlate a run with the exact supervisor build\\nthat requested it.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"version\": {"]
#[doc = "      \"title\": \"Version\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SupervisorPreamble {
    pub name: Name,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub version: ::std::option::Option<::std::string::String>,
}
#[doc = "Plain text content. Anthropic `text`, OpenAI `text` /\n`output_text` / `input_text`, Gemini text part, Bedrock `text`,\nCohere `text`, Mistral `text`. `citations` carries Anthropic citations,\nOpenAI annotations, and Gemini grounding spans anchored into this text."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"TextBlock\","]
#[doc = "  \"description\": \"Plain text content. Anthropic `text`, OpenAI `text` /\\n`output_text` / `input_text`, Gemini text part, Bedrock `text`,\\nCohere `text`, Mistral `text`. `citations` carries Anthropic citations,\\nOpenAI annotations, and Gemini grounding spans anchored into this text.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"text\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"citations\": {"]
#[doc = "      \"title\": \"Citations\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/Citation\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"text\": {"]
#[doc = "      \"title\": \"Text\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"text\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"text\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct TextBlock {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub citations: ::std::option::Option<::std::vec::Vec<Citation>>,
    pub text: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::text_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "Reasoning / chain-of-thought emitted by the model.\n\nAnthropic extended thinking, OpenAI o-series `reasoning` items,\nGemini `thought` parts, Bedrock `reasoningContent`, Mistral thinking.\n`signature` is the opaque blob the provider requires echoed back on\nthe next turn for continued reasoning: Anthropic's cryptographic\nsignature, OpenAI's `encrypted_content`, or Gemini's\n`thought_signature`. `redacted` flags blocks whose plaintext is\nunavailable (encrypted-only form)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ThinkingBlock\","]
#[doc = "  \"description\": \"Reasoning / chain-of-thought emitted by the model.\\n\\nAnthropic extended thinking, OpenAI o-series `reasoning` items,\\nGemini `thought` parts, Bedrock `reasoningContent`, Mistral thinking.\\n`signature` is the opaque blob the provider requires echoed back on\\nthe next turn for continued reasoning: Anthropic's cryptographic\\nsignature, OpenAI's `encrypted_content`, or Gemini's\\n`thought_signature`. `redacted` flags blocks whose plaintext is\\nunavailable (encrypted-only form).\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"thinking\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"redacted\": {"]
#[doc = "      \"title\": \"Redacted\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"boolean\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"signature\": {"]
#[doc = "      \"title\": \"Signature\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"thinking\": {"]
#[doc = "      \"title\": \"Thinking\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"thinking\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"thinking\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ThinkingBlock {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub redacted: ::std::option::Option<bool>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub signature: ::std::option::Option<::std::string::String>,
    pub thinking: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::thinking_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "Tool descriptor used by `AgentDescriptor.tools` and\n`agent_started.data[\"avp.tools\"]`.\n\nMCP-shaped: `name` plus optional `description` and `inputSchema`. The\ndecl describes a single tool's model-facing identity. Dispatch is\ndiscriminated by `avp.mcp_server_id`: when set, the tool is sourced\nfrom the MCP server with that `id` in `mcp_servers[]`; when absent,\nthe tool runs locally in the agent's process. The per-invocation\ndiscriminator `avp.tool.dispatch_target` on `tool_invoked` mirrors\npresence of this field."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolDecl\","]
#[doc = "  \"description\": \"Tool descriptor used by `AgentDescriptor.tools` and\\n`agent_started.data[\\\"avp.tools\\\"]`.\\n\\nMCP-shaped: `name` plus optional `description` and `inputSchema`. The\\ndecl describes a single tool's model-facing identity. Dispatch is\\ndiscriminated by `avp.mcp_server_id`: when set, the tool is sourced\\nfrom the MCP server with that `id` in `mcp_servers[]`; when absent,\\nthe tool runs locally in the agent's process. The per-invocation\\ndiscriminator `avp.tool.dispatch_target` on `tool_invoked` mirrors\\npresence of this field.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.mcp_server_id\": {"]
#[doc = "      \"title\": \"Avp.Mcp Server Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"description\": {"]
#[doc = "      \"title\": \"Description\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"inputSchema\": {"]
#[doc = "      \"title\": \"Inputschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ToolDecl {
    #[serde(
        rename = "avp.mcp_server_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_server_id: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub description: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "inputSchema",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub input_schema:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    pub name: ::std::string::String,
}
#[doc = "`ToolInvokedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolInvokedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.step\","]
#[doc = "    \"avp.tool.call_id\","]
#[doc = "    \"avp.tool.input\","]
#[doc = "    \"avp.tool.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.step\": {"]
#[doc = "      \"title\": \"Avp.Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.tool.call_id\": {"]
#[doc = "      \"title\": \"Avp.Tool.Call Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"avp.tool.dispatch_target\": {"]
#[doc = "      \"title\": \"Avp.Tool.Dispatch Target\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"enum\": ["]
#[doc = "            \"mcp_server\","]
#[doc = "            \"local\""]
#[doc = "          ]"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.tool.input\": {"]
#[doc = "      \"title\": \"Avp.Tool.Input\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    },"]
#[doc = "    \"avp.tool.name\": {"]
#[doc = "      \"title\": \"Avp.Tool.Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ToolInvokedData {
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(rename = "avp.step")]
    pub avp_step: u64,
    #[serde(rename = "avp.tool.call_id")]
    pub avp_tool_call_id: AvpToolCallId,
    #[serde(
        rename = "avp.tool.dispatch_target",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tool_dispatch_target: ::std::option::Option<ToolInvokedDataAvpToolDispatchTarget>,
    #[serde(rename = "avp.tool.input")]
    pub avp_tool_input: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    #[serde(rename = "avp.tool.name")]
    pub avp_tool_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`ToolInvokedDataAvpToolDispatchTarget`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"mcp_server\","]
#[doc = "    \"local\""]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum ToolInvokedDataAvpToolDispatchTarget {
    #[serde(rename = "mcp_server")]
    McpServer,
    #[serde(rename = "local")]
    Local,
}
impl ::std::fmt::Display for ToolInvokedDataAvpToolDispatchTarget {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::McpServer => f.write_str("mcp_server"),
            Self::Local => f.write_str("local"),
        }
    }
}
impl ::std::str::FromStr for ToolInvokedDataAvpToolDispatchTarget {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "mcp_server" => Ok(Self::McpServer),
            "local" => Ok(Self::Local),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for ToolInvokedDataAvpToolDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolInvokedDataAvpToolDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolInvokedDataAvpToolDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`ToolInvokedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolInvokedEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/ToolInvokedData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.tool_invoked\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.tool_invoked\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ToolInvokedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<ToolInvokedEventAvpCorrelationId>,
    pub data: ToolInvokedData,
    #[serde(default = "defaults::tool_invoked_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::tool_invoked_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::tool_invoked_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ToolInvokedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::tool_invoked_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ToolInvokedEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ToolInvokedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolInvokedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolInvokedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: ToolInvokedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolInvokedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolInvokedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolInvokedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolInvokedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolInvokedEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`ToolInvokedEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ToolInvokedEventSubject(::std::string::String);
impl ::std::ops::Deref for ToolInvokedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolInvokedEventSubject> for ::std::string::String {
    fn from(value: ToolInvokedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolInvokedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolInvokedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolInvokedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolInvokedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolInvokedEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Result of a client-dispatched tool call. Anthropic `tool_result`,\nOpenAI `function_call_output` / tool-role message, Gemini\n`function_response`, Bedrock `toolResult`. Anthropic permits nested\ntext/image/document content blocks; other providers serialize a\nflat string. `structured_content` carries a programmatic payload\nalongside the human-readable `content` (MCP's `structuredContent`,\nGemini `function_response.response`, Bedrock `toolResult.content.json`);\nthe two channels are complementary, not alternatives. `is_error`\nflags rejections."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolResultBlock\","]
#[doc = "  \"description\": \"Result of a client-dispatched tool call. Anthropic `tool_result`,\\nOpenAI `function_call_output` / tool-role message, Gemini\\n`function_response`, Bedrock `toolResult`. Anthropic permits nested\\ntext/image/document content blocks; other providers serialize a\\nflat string. `structured_content` carries a programmatic payload\\nalongside the human-readable `content` (MCP's `structuredContent`,\\nGemini `function_response.response`, Bedrock `toolResult.content.json`);\\nthe two channels are complementary, not alternatives. `is_error`\\nflags rejections.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"content\","]
#[doc = "    \"tool_use_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"content\": {"]
#[doc = "      \"title\": \"Content\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"oneOf\": ["]
#[doc = "              {"]
#[doc = "                \"$ref\": \"#/$defs/TextBlock\""]
#[doc = "              },"]
#[doc = "              {"]
#[doc = "                \"$ref\": \"#/$defs/ImageBlock\""]
#[doc = "              },"]
#[doc = "              {"]
#[doc = "                \"$ref\": \"#/$defs/DocumentBlock\""]
#[doc = "              }"]
#[doc = "            ],"]
#[doc = "            \"discriminator\": {"]
#[doc = "              \"mapping\": {"]
#[doc = "                \"document\": \"#/$defs/DocumentBlock\","]
#[doc = "                \"image\": \"#/$defs/ImageBlock\","]
#[doc = "                \"text\": \"#/$defs/TextBlock\""]
#[doc = "              },"]
#[doc = "              \"propertyName\": \"type\""]
#[doc = "            }"]
#[doc = "          }"]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"is_error\": {"]
#[doc = "      \"title\": \"Is Error\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"boolean\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"structured_content\": {"]
#[doc = "      \"title\": \"Structured Content\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"tool_use_id\": {"]
#[doc = "      \"title\": \"Tool Use Id\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"tool_result\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"tool_result\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ToolResultBlock {
    pub content: Content,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub is_error: ::std::option::Option<bool>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub structured_content:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    pub tool_use_id: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::tool_result_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "Tool result sent back to the model.\n\n`avp.tool_result` is a `content.ToolResultBlock` carrying\n`tool_use_id`, `content` (string or nested text/image/document\nblocks), and `is_error`. Rejections set `is_error=True` with the\nreason in `content[0].text`. During reconstruction this block\nbecomes one entry of the next user-role message's content array."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolReturnedData\","]
#[doc = "  \"description\": \"Tool result sent back to the model.\\n\\n`avp.tool_result` is a `content.ToolResultBlock` carrying\\n`tool_use_id`, `content` (string or nested text/image/document\\nblocks), and `is_error`. Rejections set `is_error=True` with the\\nreason in `content[0].text`. During reconstruction this block\\nbecomes one entry of the next user-role message's content array.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.duration_ms\","]
#[doc = "    \"avp.step\","]
#[doc = "    \"avp.tool.call_id\","]
#[doc = "    \"avp.tool.name\","]
#[doc = "    \"avp.tool_result\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.duration_ms\": {"]
#[doc = "      \"title\": \"Avp.Duration Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.meta\": {"]
#[doc = "      \"title\": \"Avp.Meta\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": true"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.step\": {"]
#[doc = "      \"title\": \"Avp.Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.tool.call_id\": {"]
#[doc = "      \"title\": \"Avp.Tool.Call Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"avp.tool.name\": {"]
#[doc = "      \"title\": \"Avp.Tool.Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.tool_result\": {"]
#[doc = "      \"$ref\": \"#/$defs/ToolResultBlock\""]
#[doc = "    },"]
#[doc = "    \"parent_span_id\": {"]
#[doc = "      \"title\": \"Parent Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"trace_id\": {"]
#[doc = "      \"title\": \"Trace Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 32,"]
#[doc = "      \"minLength\": 32,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ToolReturnedData {
    #[serde(rename = "avp.duration_ms")]
    pub avp_duration_ms: u64,
    #[serde(
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(rename = "avp.step")]
    pub avp_step: u64,
    #[serde(rename = "avp.tool.call_id")]
    pub avp_tool_call_id: AvpToolCallId,
    #[serde(rename = "avp.tool.name")]
    pub avp_tool_name: ::std::string::String,
    #[serde(rename = "avp.tool_result")]
    pub avp_tool_result: ToolResultBlock,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`ToolReturnedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolReturnedEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.correlation_id\": {"]
#[doc = "      \"title\": \"Avp.Correlation Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"$ref\": \"#/$defs/ToolReturnedData\""]
#[doc = "    },"]
#[doc = "    \"datacontenttype\": {"]
#[doc = "      \"title\": \"Datacontenttype\","]
#[doc = "      \"default\": \"application/json\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"dataschema\": {"]
#[doc = "      \"title\": \"Dataschema\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"default\": \"avp://agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://agent\""]
#[doc = "    },"]
#[doc = "    \"specversion\": {"]
#[doc = "      \"title\": \"Specversion\","]
#[doc = "      \"default\": \"1.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"1.0\""]
#[doc = "    },"]
#[doc = "    \"subject\": {"]
#[doc = "      \"title\": \"Subject\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"minLength\": 1"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"time\": {"]
#[doc = "      \"title\": \"Time\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"avp.tool_returned\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.tool_returned\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ToolReturnedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<ToolReturnedEventAvpCorrelationId>,
    pub data: ToolReturnedData,
    #[serde(default = "defaults::tool_returned_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::tool_returned_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::tool_returned_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ToolReturnedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", skip_serializing, default = "defaults::tool_returned_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ToolReturnedEventAvpCorrelationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ToolReturnedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolReturnedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolReturnedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: ToolReturnedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolReturnedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolReturnedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolReturnedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolReturnedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolReturnedEventAvpCorrelationId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`ToolReturnedEventSubject`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ToolReturnedEventSubject(::std::string::String);
impl ::std::ops::Deref for ToolReturnedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolReturnedEventSubject> for ::std::string::String {
    fn from(value: ToolReturnedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolReturnedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolReturnedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolReturnedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolReturnedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolReturnedEventSubject {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Model invokes a client-dispatched tool. Anthropic `tool_use`,\nOpenAI `function_call` / `tool_calls`, Gemini `function_call`,\nBedrock `toolUse`, Cohere tool_calls, Mistral tool_calls."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolUseBlock\","]
#[doc = "  \"description\": \"Model invokes a client-dispatched tool. Anthropic `tool_use`,\\nOpenAI `function_call` / `tool_calls`, Gemini `function_call`,\\nBedrock `toolUse`, Cohere tool_calls, Mistral tool_calls.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\","]
#[doc = "    \"input\","]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"input\": {"]
#[doc = "      \"title\": \"Input\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"tool_use\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"tool_use\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ToolUseBlock {
    pub id: ::std::string::String,
    pub input: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    pub name: ::std::string::String,
    #[serde(rename = "type", skip_serializing, default = "defaults::tool_use_block_type")]
    pub type_: ::std::string::String,
}
#[doc = "`TraceId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Trace Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"maxLength\": 32,"]
#[doc = "  \"minLength\": 32,"]
#[doc = "  \"pattern\": \"^[0-9a-f]{32}$\""]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct TraceId(::std::string::String);
impl ::std::ops::Deref for TraceId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<TraceId> for ::std::string::String {
    fn from(value: TraceId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for TraceId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() > 32usize {
            return Err("longer than 32 characters".into());
        }
        if value.chars().count() < 32usize {
            return Err("shorter than 32 characters".into());
        }
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| ::regress::Regex::new("^[0-9a-f]{32}$").unwrap());
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[0-9a-f]{32}$\"".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for TraceId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for TraceId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for TraceId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for TraceId {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`Url`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Url\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct Url(::std::string::String);
impl ::std::ops::Deref for Url {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<Url> for ::std::string::String {
    fn from(value: Url) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for Url {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for Url {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for Url {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Url {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for Url {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "External URL. Anthropic `source.type=url`, OpenAI `image_url`,\nGemini `file_data` (when `file_uri` is a public URL)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"UrlSource\","]
#[doc = "  \"description\": \"External URL. Anthropic `source.type=url`, OpenAI `image_url`,\\nGemini `file_data` (when `file_uri` is a public URL).\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"url\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"url\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"url\""]
#[doc = "    },"]
#[doc = "    \"url\": {"]
#[doc = "      \"title\": \"Url\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct UrlSource {
    #[serde(rename = "type", skip_serializing, default = "defaults::url_source_type")]
    pub type_: ::std::string::String,
    pub url: ::std::string::String,
}
#[doc = "Per-turn token accounting carried on `assistant_message.avp.usage`.\n\n`input_tokens` is the total input tokens for the turn, INCLUDING\ncache-read tokens. `cache_read_input_tokens` and\n`cache_creation_input_tokens` are informational breakdowns already\naccounted for inside `input_tokens`; consumers MUST NOT double-count\nthem when summing. `reasoning_output_tokens` is the subset of\n`output_tokens` the provider attributes to internal reasoning (o-series\nreasoning tokens, Anthropic extended-thinking output).\n\n`extra=\"allow\"` so provider-specific token categories the spec\ndoesn't enumerate (vision tokens, audio output tokens, ...) round-trip\nthrough `avp.usage` verbatim without requiring spec churn."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Usage\","]
#[doc = "  \"description\": \"Per-turn token accounting carried on `assistant_message.avp.usage`.\\n\\n`input_tokens` is the total input tokens for the turn, INCLUDING\\ncache-read tokens. `cache_read_input_tokens` and\\n`cache_creation_input_tokens` are informational breakdowns already\\naccounted for inside `input_tokens`; consumers MUST NOT double-count\\nthem when summing. `reasoning_output_tokens` is the subset of\\n`output_tokens` the provider attributes to internal reasoning (o-series\\nreasoning tokens, Anthropic extended-thinking output).\\n\\n`extra=\\\"allow\\\"` so provider-specific token categories the spec\\ndoesn't enumerate (vision tokens, audio output tokens, ...) round-trip\\nthrough `avp.usage` verbatim without requiring spec churn.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"input_tokens\","]
#[doc = "    \"output_tokens\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"cache_creation_input_tokens\": {"]
#[doc = "      \"title\": \"Cache Creation Input Tokens\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\","]
#[doc = "          \"minimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"cache_read_input_tokens\": {"]
#[doc = "      \"title\": \"Cache Read Input Tokens\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\","]
#[doc = "          \"minimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"input_tokens\": {"]
#[doc = "      \"title\": \"Input Tokens\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"output_tokens\": {"]
#[doc = "      \"title\": \"Output Tokens\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"reasoning_output_tokens\": {"]
#[doc = "      \"title\": \"Reasoning Output Tokens\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\","]
#[doc = "          \"minimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct Usage {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub cache_creation_input_tokens: ::std::option::Option<u64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub cache_read_input_tokens: ::std::option::Option<u64>,
    pub input_tokens: u64,
    pub output_tokens: u64,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub reasoning_output_tokens: ::std::option::Option<u64>,
}
#[doc = "Video content. Gemini `inline_data` / `file_data` video, Bedrock\n`video`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"VideoBlock\","]
#[doc = "  \"description\": \"Video content. Gemini `inline_data` / `file_data` video, Bedrock\\n`video`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"source\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"oneOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/Base64Source\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/UrlSource\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/FileSource\""]
#[doc = "        }"]
#[doc = "      ],"]
#[doc = "      \"discriminator\": {"]
#[doc = "        \"mapping\": {"]
#[doc = "          \"base64\": \"#/$defs/Base64Source\","]
#[doc = "          \"file\": \"#/$defs/FileSource\","]
#[doc = "          \"url\": \"#/$defs/UrlSource\""]
#[doc = "        },"]
#[doc = "        \"propertyName\": \"type\""]
#[doc = "      }"]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"video\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"video\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct VideoBlock {
    pub source: Source,
    #[serde(rename = "type", skip_serializing, default = "defaults::video_block_type")]
    pub type_: ::std::string::String,
}
#[doc = r" Generation of default values for serde."]
pub mod defaults {
    pub(super) fn agent_described_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn agent_described_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn agent_described_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn agent_described_event_type() -> ::std::string::String {
        "avp.agent_described".to_string()
    }
    pub(super) fn agent_started_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn agent_started_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn agent_started_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn agent_started_event_type() -> ::std::string::String {
        "avp.agent_started".to_string()
    }
    pub(super) fn agent_stopped_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn agent_stopped_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn agent_stopped_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn agent_stopped_event_type() -> ::std::string::String {
        "avp.agent_stopped".to_string()
    }
    pub(super) fn assistant_message_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn assistant_message_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn assistant_message_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn assistant_message_event_type() -> ::std::string::String {
        "avp.assistant_message".to_string()
    }
    pub(super) fn audio_block_type() -> ::std::string::String {
        "audio".to_string()
    }
    pub(super) fn base64_source_type() -> ::std::string::String {
        "base64".to_string()
    }
    pub(super) fn document_block_type() -> ::std::string::String {
        "document".to_string()
    }
    pub(super) fn error_occurred_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn error_occurred_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn error_occurred_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn error_occurred_event_type() -> ::std::string::String {
        "avp.error_occurred".to_string()
    }
    pub(super) fn file_source_type() -> ::std::string::String {
        "file".to_string()
    }
    pub(super) fn image_block_type() -> ::std::string::String {
        "image".to_string()
    }
    pub(super) fn refusal_block_type() -> ::std::string::String {
        "refusal".to_string()
    }
    pub(super) fn run_requested_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn run_requested_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn run_requested_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn run_requested_event_type() -> ::std::string::String {
        "avp.run_requested".to_string()
    }
    pub(super) fn server_tool_result_block_type() -> ::std::string::String {
        "server_tool_result".to_string()
    }
    pub(super) fn server_tool_use_block_type() -> ::std::string::String {
        "server_tool_use".to_string()
    }
    pub(super) fn subagent_invoked_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn subagent_invoked_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn subagent_invoked_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn subagent_invoked_event_type() -> ::std::string::String {
        "avp.subagent_invoked".to_string()
    }
    pub(super) fn subagent_returned_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn subagent_returned_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn subagent_returned_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn subagent_returned_event_type() -> ::std::string::String {
        "avp.subagent_returned".to_string()
    }
    pub(super) fn text_block_type() -> ::std::string::String {
        "text".to_string()
    }
    pub(super) fn thinking_block_type() -> ::std::string::String {
        "thinking".to_string()
    }
    pub(super) fn tool_invoked_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_invoked_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn tool_invoked_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_invoked_event_type() -> ::std::string::String {
        "avp.tool_invoked".to_string()
    }
    pub(super) fn tool_result_block_type() -> ::std::string::String {
        "tool_result".to_string()
    }
    pub(super) fn tool_returned_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_returned_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn tool_returned_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_returned_event_type() -> ::std::string::String {
        "avp.tool_returned".to_string()
    }
    pub(super) fn tool_use_block_type() -> ::std::string::String {
        "tool_use".to_string()
    }
    pub(super) fn url_source_type() -> ::std::string::String {
        "url".to_string()
    }
    pub(super) fn video_block_type() -> ::std::string::String {
        "video".to_string()
    }
}
