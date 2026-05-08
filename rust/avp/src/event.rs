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
#[doc = "Payload of avp.agent_described events.\n\nThe agent's published manifest, emitted between `run_requested` and\n`agent_started`. `avp.agent` MUST equal what `<agent> describe`\nprints to stdout for the same agent build."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentDescribedData\","]
#[doc = "  \"description\": \"Payload of avp.agent_described events.\\n\\nThe agent's published manifest, emitted between `run_requested` and\\n`agent_started`. `avp.agent` MUST equal what `<agent> describe`\\nprints to stdout for the same agent build.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.manifest\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.manifest\": {"]
#[doc = "      \"$ref\": \"#/$defs/AgentManifest\""]
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
    #[serde(rename = "avp.manifest")]
    pub avp_manifest: AgentManifest,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "Second event of the trajectory. The agent's \"whoami\" — its\nself-published manifest of everything triggerable without supervisor\nconfiguration. Carries the same JSON `<agent> describe` prints to\nstdout for this agent build."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentDescribedEvent\","]
#[doc = "  \"description\": \"Second event of the trajectory. The agent's \\\"whoami\\\" — its\\nself-published manifest of everything triggerable without supervisor\\nconfiguration. Carries the same JSON `<agent> describe` prints to\\nstdout for this agent build.\","]
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
    #[serde(rename = "type", default = "defaults::agent_described_event_type")]
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
#[doc = "Self-description of an AVP agent — who it is, what it brings.\n\nEvery AVP-compliant agent MUST publish a manifest that enumerates\neverything triggerable without supervisor configuration: SDK preset\ntools, runtime-bundled subagents, runtime-bundled skills, plus the\nagent's name / version / supported AVP spec version. Consumers use\nthe manifest in two ways:\n\n  1. **Pre-flight** — `<agent> describe` prints the manifest as JSON\n     to stdout. A supervisor authoring a Commission can introspect what\n     the agent offers before invoking it (so `Commission.exposed`,\n     `Commission.subagents`, etc. can be authored against ground truth).\n\n  2. **On the wire** — the agent emits a `agent_described` event\n     right after `run_requested` and right before `agent_started`.\n     The on-wire payload MUST equal what `describe` prints for the\n     same agent build, so the audit trail records exactly what the\n     consumer would have seen at pre-flight time.\n\nScope: SDK defaults only. The manifest does NOT include\nsupervisor-declared surfaces (`Commission.tools`, `Commission.subagents`,\n`Commission.skills`) and does NOT include environment-discovered\nsurfaces (filesystem skills under `~/.claude/skills/`, MCP servers\ndiscovered at startup, user-installed plugins). Those appear on\n`agent_started` (the merged-view event) and `mcp_server_connected`\nrespectively. The manifest is the agent's identity, not the run's."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentManifest\","]
#[doc = "  \"description\": \"Self-description of an AVP agent — who it is, what it brings.\\n\\nEvery AVP-compliant agent MUST publish a manifest that enumerates\\neverything triggerable without supervisor configuration: SDK preset\\ntools, runtime-bundled subagents, runtime-bundled skills, plus the\\nagent's name / version / supported AVP spec version. Consumers use\\nthe manifest in two ways:\\n\\n  1. **Pre-flight** — `<agent> describe` prints the manifest as JSON\\n     to stdout. A supervisor authoring a Commission can introspect what\\n     the agent offers before invoking it (so `Commission.exposed`,\\n     `Commission.subagents`, etc. can be authored against ground truth).\\n\\n  2. **On the wire** — the agent emits a `agent_described` event\\n     right after `run_requested` and right before `agent_started`.\\n     The on-wire payload MUST equal what `describe` prints for the\\n     same agent build, so the audit trail records exactly what the\\n     consumer would have seen at pre-flight time.\\n\\nScope: SDK defaults only. The manifest does NOT include\\nsupervisor-declared surfaces (`Commission.tools`, `Commission.subagents`,\\n`Commission.skills`) and does NOT include environment-discovered\\nsurfaces (filesystem skills under `~/.claude/skills/`, MCP servers\\ndiscovered at startup, user-installed plugins). Those appear on\\n`agent_started` (the merged-view event) and `mcp_server_connected`\\nrespectively. The manifest is the agent's identity, not the run's.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"agent_name\","]
#[doc = "    \"agent_version\","]
#[doc = "    \"avp_spec_version\""]
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
#[doc = "    \"avp_spec_version\": {"]
#[doc = "      \"title\": \"Avp Spec Version\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"0.1\""]
#[doc = "    },"]
#[doc = "    \"built_in_skills\": {"]
#[doc = "      \"title\": \"Built In Skills\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/_SkillDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"built_in_subagents\": {"]
#[doc = "      \"title\": \"Built In Subagents\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/_SubagentDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"built_in_tools\": {"]
#[doc = "      \"title\": \"Built In Tools\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/_ToolDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
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
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct AgentManifest {
    pub agent_name: AgentName,
    pub agent_version: AgentVersion,
    pub avp_spec_version: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub built_in_skills: ::std::option::Option<::std::vec::Vec<SkillDecl>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub built_in_subagents: ::std::option::Option<::std::vec::Vec<SubagentDecl>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub built_in_tools: ::std::option::Option<::std::vec::Vec<ToolDecl>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub capabilities: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub default_model: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub supported_models: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
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
#[doc = "    \"avp.schema_version\": {"]
#[doc = "      \"title\": \"Avp.Schema Version\","]
#[doc = "      \"default\": \"0.1\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"0.1\""]
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
#[doc = "    \"gen_ai.operation.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Operation.Name\","]
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
#[doc = "    \"gen_ai.provider.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Provider.Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"gen_ai.request.model\": {"]
#[doc = "      \"title\": \"Gen Ai.Request.Model\","]
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
#[doc = "            \"$ref\": \"#/$defs/_SkillDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"span_id\": {"]
#[doc = "      \"title\": \"Span Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 16,"]
#[doc = "      \"minLength\": 16,"]
#[doc = "      \"pattern\": \"^[0-9a-f]{16}$\""]
#[doc = "    },"]
#[doc = "    \"subagents\": {"]
#[doc = "      \"title\": \"Subagents\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/_SubagentDecl\""]
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
#[doc = "            \"$ref\": \"#/$defs/_ToolDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
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
        rename = "avp.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(
        rename = "avp.schema_version",
        default = "defaults::agent_started_data_avp_schema_version"
    )]
    pub avp_schema_version: ::std::string::String,
    #[serde(
        rename = "avp.session_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_session_id: ::std::option::Option<::std::string::String>,
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
        rename = "gen_ai.operation.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_operation_name: ::std::option::Option<AgentStartedDataGenAiOperationName>,
    #[serde(
        rename = "gen_ai.provider.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_provider_name: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "gen_ai.request.model",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_request_model: ::std::option::Option<::std::string::String>,
    pub parent_span_id: ParentSpanId,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub skills: ::std::option::Option<::std::vec::Vec<SkillDecl>>,
    pub span_id: SpanId,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subagents: ::std::option::Option<::std::vec::Vec<SubagentDecl>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub system_prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tools: ::std::option::Option<::std::vec::Vec<ToolDecl>>,
    pub trace_id: TraceId,
}
#[doc = "`AgentStartedDataGenAiOperationName`"]
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
pub enum AgentStartedDataGenAiOperationName {
    #[serde(rename = "invoke_agent")]
    InvokeAgent,
    #[serde(rename = "chat")]
    Chat,
}
impl ::std::fmt::Display for AgentStartedDataGenAiOperationName {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::InvokeAgent => f.write_str("invoke_agent"),
            Self::Chat => f.write_str("chat"),
        }
    }
}
impl ::std::str::FromStr for AgentStartedDataGenAiOperationName {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "invoke_agent" => Ok(Self::InvokeAgent),
            "chat" => Ok(Self::Chat),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for AgentStartedDataGenAiOperationName {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentStartedDataGenAiOperationName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentStartedDataGenAiOperationName {
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
    #[serde(rename = "type", default = "defaults::agent_started_event_type")]
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
#[doc = "`AgentStoppedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentStoppedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.reason\","]
#[doc = "    \"avp.state\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.duration_ms\": {"]
#[doc = "      \"title\": \"Avp.Duration Ms\","]
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
#[doc = "    \"avp.state\": {"]
#[doc = "      \"$ref\": \"#/$defs/RunStateSnapshot\""]
#[doc = "    },"]
#[doc = "    \"avp.total_cost_usd\": {"]
#[doc = "      \"title\": \"Avp.Total Cost Usd\","]
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
#[doc = "    \"avp.total_tokens\": {"]
#[doc = "      \"title\": \"Avp.Total Tokens\","]
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
#[doc = "    \"avp.total_turns\": {"]
#[doc = "      \"title\": \"Avp.Total Turns\","]
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
        rename = "avp.duration_ms",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_duration_ms: ::std::option::Option<u64>,
    #[serde(
        rename = "avp.output",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_output: ::std::option::Option<::serde_json::Value>,
    #[serde(rename = "avp.reason")]
    pub avp_reason: StopReason,
    #[serde(rename = "avp.state")]
    pub avp_state: RunStateSnapshot,
    #[serde(
        rename = "avp.total_cost_usd",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_total_cost_usd: ::std::option::Option<f64>,
    #[serde(
        rename = "avp.total_tokens",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_total_tokens: ::std::option::Option<u64>,
    #[serde(
        rename = "avp.total_turns",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_total_turns: ::std::option::Option<u64>,
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
    #[serde(rename = "type", default = "defaults::agent_stopped_event_type")]
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
#[doc = "`AvpMcpDisconnectReason`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Avp.Mcp.Disconnect Reason\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"clean\","]
#[doc = "    \"error\""]
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
pub enum AvpMcpDisconnectReason {
    #[serde(rename = "clean")]
    Clean,
    #[serde(rename = "error")]
    Error,
}
impl ::std::fmt::Display for AvpMcpDisconnectReason {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Clean => f.write_str("clean"),
            Self::Error => f.write_str("error"),
        }
    }
}
impl ::std::str::FromStr for AvpMcpDisconnectReason {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "clean" => Ok(Self::Clean),
            "error" => Ok(Self::Error),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for AvpMcpDisconnectReason {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AvpMcpDisconnectReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AvpMcpDisconnectReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`AvpMcpServerId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Avp.Mcp.Server Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AvpMcpServerId(::std::string::String);
impl ::std::ops::Deref for AvpMcpServerId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AvpMcpServerId> for ::std::string::String {
    fn from(value: AvpMcpServerId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AvpMcpServerId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AvpMcpServerId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AvpMcpServerId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AvpMcpServerId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AvpMcpServerId {
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
#[doc = "`AvpRefusalReason`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Avp.Refusal.Reason\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AvpRefusalReason(::std::string::String);
impl ::std::ops::Deref for AvpRefusalReason {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AvpRefusalReason> for ::std::string::String {
    fn from(value: AvpRefusalReason) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AvpRefusalReason {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AvpRefusalReason {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AvpRefusalReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AvpRefusalReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AvpRefusalReason {
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
#[doc = "`AvpSupervisorName`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Avp.Supervisor.Name\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AvpSupervisorName(::std::string::String);
impl ::std::ops::Deref for AvpSupervisorName {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AvpSupervisorName> for ::std::string::String {
    fn from(value: AvpSupervisorName) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AvpSupervisorName {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AvpSupervisorName {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AvpSupervisorName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AvpSupervisorName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AvpSupervisorName {
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
#[doc = "Agent → supervisor event. Each event is a CloudEvent 1.0 envelope carrying a typed `data` payload. The `type` field is the discriminator (reverse-DNS, `avp.*` namespace). Attribute names inside `data` follow OpenTelemetry GenAI semantic conventions and OTel span identification (`trace_id`, `span_id`, `parent_span_id`); AVP-specific attributes are namespaced `avp.*`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"$id\": \"https://avp.dev/schema/v0.1/event.schema.json\","]
#[doc = "  \"title\": \"AVP v0.1 Event\","]
#[doc = "  \"description\": \"Agent → supervisor event. Each event is a CloudEvent 1.0 envelope carrying a typed `data` payload. The `type` field is the discriminator (reverse-DNS, `avp.*` namespace). Attribute names inside `data` follow OpenTelemetry GenAI semantic conventions and OTel span identification (`trace_id`, `span_id`, `parent_span_id`); AVP-specific attributes are namespaced `avp.*`.\","]
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
#[doc = "      \"$ref\": \"#/$defs/ModelTurnStartedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ModelTurnEndedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolInvokedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolReturnedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolFailedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/SubagentInvokedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/SubagentReturnedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/SubagentFailedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/TextEmittedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ReasoningEmittedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/RefusalRecordedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/CostRecordedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/SkillLoadedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ErrorOccurredEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/McpServerConnectedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/McpServerDisconnectedEvent\""]
#[doc = "    }"]
#[doc = "  ],"]
#[doc = "  \"discriminator\": {"]
#[doc = "    \"mapping\": {"]
#[doc = "      \"avp.agent_described\": \"#/$defs/AgentDescribedEvent\","]
#[doc = "      \"avp.agent_started\": \"#/$defs/AgentStartedEvent\","]
#[doc = "      \"avp.agent_stopped\": \"#/$defs/AgentStoppedEvent\","]
#[doc = "      \"avp.cost_recorded\": \"#/$defs/CostRecordedEvent\","]
#[doc = "      \"avp.error_occurred\": \"#/$defs/ErrorOccurredEvent\","]
#[doc = "      \"avp.mcp_server_connected\": \"#/$defs/McpServerConnectedEvent\","]
#[doc = "      \"avp.mcp_server_disconnected\": \"#/$defs/McpServerDisconnectedEvent\","]
#[doc = "      \"avp.model_turn_ended\": \"#/$defs/ModelTurnEndedEvent\","]
#[doc = "      \"avp.model_turn_started\": \"#/$defs/ModelTurnStartedEvent\","]
#[doc = "      \"avp.reasoning_emitted\": \"#/$defs/ReasoningEmittedEvent\","]
#[doc = "      \"avp.refusal_recorded\": \"#/$defs/RefusalRecordedEvent\","]
#[doc = "      \"avp.run_requested\": \"#/$defs/RunRequestedEvent\","]
#[doc = "      \"avp.skill_loaded\": \"#/$defs/SkillLoadedEvent\","]
#[doc = "      \"avp.subagent_failed\": \"#/$defs/SubagentFailedEvent\","]
#[doc = "      \"avp.subagent_invoked\": \"#/$defs/SubagentInvokedEvent\","]
#[doc = "      \"avp.subagent_returned\": \"#/$defs/SubagentReturnedEvent\","]
#[doc = "      \"avp.text_emitted\": \"#/$defs/TextEmittedEvent\","]
#[doc = "      \"avp.tool_failed\": \"#/$defs/ToolFailedEvent\","]
#[doc = "      \"avp.tool_invoked\": \"#/$defs/ToolInvokedEvent\","]
#[doc = "      \"avp.tool_returned\": \"#/$defs/ToolReturnedEvent\""]
#[doc = "    },"]
#[doc = "    \"propertyName\": \"type\""]
#[doc = "  }"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(untagged)]
pub enum AvpV01Event {
    RunRequestedEvent(RunRequestedEvent),
    AgentDescribedEvent(AgentDescribedEvent),
    AgentStartedEvent(AgentStartedEvent),
    AgentStoppedEvent(AgentStoppedEvent),
    ModelTurnStartedEvent(ModelTurnStartedEvent),
    ModelTurnEndedEvent(ModelTurnEndedEvent),
    ToolInvokedEvent(ToolInvokedEvent),
    ToolReturnedEvent(ToolReturnedEvent),
    ToolFailedEvent(ToolFailedEvent),
    SubagentInvokedEvent(SubagentInvokedEvent),
    SubagentReturnedEvent(SubagentReturnedEvent),
    SubagentFailedEvent(SubagentFailedEvent),
    TextEmittedEvent(TextEmittedEvent),
    ReasoningEmittedEvent(ReasoningEmittedEvent),
    RefusalRecordedEvent(RefusalRecordedEvent),
    CostRecordedEvent(CostRecordedEvent),
    SkillLoadedEvent(SkillLoadedEvent),
    ErrorOccurredEvent(ErrorOccurredEvent),
    McpServerConnectedEvent(McpServerConnectedEvent),
    McpServerDisconnectedEvent(McpServerDisconnectedEvent),
}
impl ::std::convert::From<RunRequestedEvent> for AvpV01Event {
    fn from(value: RunRequestedEvent) -> Self {
        Self::RunRequestedEvent(value)
    }
}
impl ::std::convert::From<AgentDescribedEvent> for AvpV01Event {
    fn from(value: AgentDescribedEvent) -> Self {
        Self::AgentDescribedEvent(value)
    }
}
impl ::std::convert::From<AgentStartedEvent> for AvpV01Event {
    fn from(value: AgentStartedEvent) -> Self {
        Self::AgentStartedEvent(value)
    }
}
impl ::std::convert::From<AgentStoppedEvent> for AvpV01Event {
    fn from(value: AgentStoppedEvent) -> Self {
        Self::AgentStoppedEvent(value)
    }
}
impl ::std::convert::From<ModelTurnStartedEvent> for AvpV01Event {
    fn from(value: ModelTurnStartedEvent) -> Self {
        Self::ModelTurnStartedEvent(value)
    }
}
impl ::std::convert::From<ModelTurnEndedEvent> for AvpV01Event {
    fn from(value: ModelTurnEndedEvent) -> Self {
        Self::ModelTurnEndedEvent(value)
    }
}
impl ::std::convert::From<ToolInvokedEvent> for AvpV01Event {
    fn from(value: ToolInvokedEvent) -> Self {
        Self::ToolInvokedEvent(value)
    }
}
impl ::std::convert::From<ToolReturnedEvent> for AvpV01Event {
    fn from(value: ToolReturnedEvent) -> Self {
        Self::ToolReturnedEvent(value)
    }
}
impl ::std::convert::From<ToolFailedEvent> for AvpV01Event {
    fn from(value: ToolFailedEvent) -> Self {
        Self::ToolFailedEvent(value)
    }
}
impl ::std::convert::From<SubagentInvokedEvent> for AvpV01Event {
    fn from(value: SubagentInvokedEvent) -> Self {
        Self::SubagentInvokedEvent(value)
    }
}
impl ::std::convert::From<SubagentReturnedEvent> for AvpV01Event {
    fn from(value: SubagentReturnedEvent) -> Self {
        Self::SubagentReturnedEvent(value)
    }
}
impl ::std::convert::From<SubagentFailedEvent> for AvpV01Event {
    fn from(value: SubagentFailedEvent) -> Self {
        Self::SubagentFailedEvent(value)
    }
}
impl ::std::convert::From<TextEmittedEvent> for AvpV01Event {
    fn from(value: TextEmittedEvent) -> Self {
        Self::TextEmittedEvent(value)
    }
}
impl ::std::convert::From<ReasoningEmittedEvent> for AvpV01Event {
    fn from(value: ReasoningEmittedEvent) -> Self {
        Self::ReasoningEmittedEvent(value)
    }
}
impl ::std::convert::From<RefusalRecordedEvent> for AvpV01Event {
    fn from(value: RefusalRecordedEvent) -> Self {
        Self::RefusalRecordedEvent(value)
    }
}
impl ::std::convert::From<CostRecordedEvent> for AvpV01Event {
    fn from(value: CostRecordedEvent) -> Self {
        Self::CostRecordedEvent(value)
    }
}
impl ::std::convert::From<SkillLoadedEvent> for AvpV01Event {
    fn from(value: SkillLoadedEvent) -> Self {
        Self::SkillLoadedEvent(value)
    }
}
impl ::std::convert::From<ErrorOccurredEvent> for AvpV01Event {
    fn from(value: ErrorOccurredEvent) -> Self {
        Self::ErrorOccurredEvent(value)
    }
}
impl ::std::convert::From<McpServerConnectedEvent> for AvpV01Event {
    fn from(value: McpServerConnectedEvent) -> Self {
        Self::McpServerConnectedEvent(value)
    }
}
impl ::std::convert::From<McpServerDisconnectedEvent> for AvpV01Event {
    fn from(value: McpServerDisconnectedEvent) -> Self {
        Self::McpServerDisconnectedEvent(value)
    }
}
#[doc = "`CostRecordedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"CostRecordedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.state\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
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
#[doc = "    \"avp.state\": {"]
#[doc = "      \"$ref\": \"#/$defs/RunStateSnapshot\""]
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
pub struct CostRecordedData {
    #[serde(
        rename = "avp.cost.source",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_cost_source: ::std::option::Option<CostRecordedDataAvpCostSource>,
    #[serde(rename = "avp.state")]
    pub avp_state: RunStateSnapshot,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`CostRecordedDataAvpCostSource`"]
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
pub enum CostRecordedDataAvpCostSource {
    #[serde(rename = "computed")]
    Computed,
    #[serde(rename = "reported")]
    Reported,
    #[serde(rename = "unknown")]
    Unknown,
}
impl ::std::fmt::Display for CostRecordedDataAvpCostSource {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Computed => f.write_str("computed"),
            Self::Reported => f.write_str("reported"),
            Self::Unknown => f.write_str("unknown"),
        }
    }
}
impl ::std::str::FromStr for CostRecordedDataAvpCostSource {
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
impl ::std::convert::TryFrom<&str> for CostRecordedDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for CostRecordedDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for CostRecordedDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`CostRecordedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"CostRecordedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/CostRecordedData\""]
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
#[doc = "      \"default\": \"avp.cost_recorded\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.cost_recorded\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct CostRecordedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<CostRecordedEventAvpCorrelationId>,
    pub data: CostRecordedData,
    #[serde(default = "defaults::cost_recorded_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::cost_recorded_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::cost_recorded_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<CostRecordedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::cost_recorded_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`CostRecordedEventAvpCorrelationId`"]
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
pub struct CostRecordedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for CostRecordedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<CostRecordedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: CostRecordedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for CostRecordedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for CostRecordedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for CostRecordedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for CostRecordedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for CostRecordedEventAvpCorrelationId {
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
#[doc = "`CostRecordedEventSubject`"]
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
pub struct CostRecordedEventSubject(::std::string::String);
impl ::std::ops::Deref for CostRecordedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<CostRecordedEventSubject> for ::std::string::String {
    fn from(value: CostRecordedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for CostRecordedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for CostRecordedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for CostRecordedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for CostRecordedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for CostRecordedEventSubject {
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
#[doc = "    \"accounting_reset\","]
#[doc = "    \"unsupported_model\","]
#[doc = "    \"exposed_unresolved\","]
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
    #[serde(rename = "accounting_reset")]
    AccountingReset,
    #[serde(rename = "unsupported_model")]
    UnsupportedModel,
    #[serde(rename = "exposed_unresolved")]
    ExposedUnresolved,
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
            Self::AccountingReset => f.write_str("accounting_reset"),
            Self::UnsupportedModel => f.write_str("unsupported_model"),
            Self::ExposedUnresolved => f.write_str("exposed_unresolved"),
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
            "accounting_reset" => Ok(Self::AccountingReset),
            "unsupported_model" => Ok(Self::UnsupportedModel),
            "exposed_unresolved" => Ok(Self::ExposedUnresolved),
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
    #[serde(rename = "type", default = "defaults::error_occurred_event_type")]
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
#[doc = "`GenAiToolCallId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Gen Ai.Tool.Call.Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct GenAiToolCallId(::std::string::String);
impl ::std::ops::Deref for GenAiToolCallId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<GenAiToolCallId> for ::std::string::String {
    fn from(value: GenAiToolCallId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for GenAiToolCallId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for GenAiToolCallId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for GenAiToolCallId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for GenAiToolCallId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for GenAiToolCallId {
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
#[doc = "`McpServerConnectedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerConnectedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.mcp.protocol_version\","]
#[doc = "    \"avp.mcp.server_id\","]
#[doc = "    \"avp.mcp.tool_count\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.mcp.error\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Error\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.mcp.protocol_version\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Protocol Version\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.mcp.resources\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Resources\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/_ResourceDecl\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.mcp.server_id\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Server Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"avp.mcp.server_name\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Server Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.mcp.server_version\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Server Version\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.mcp.status\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Status\","]
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
#[doc = "    },"]
#[doc = "    \"avp.mcp.tool_count\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Tool Count\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"avp.mcp.tools\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Tools\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/_ToolDecl\""]
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
pub struct McpServerConnectedData {
    #[serde(
        rename = "avp.mcp.error",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_error: ::std::option::Option<::std::string::String>,
    #[serde(rename = "avp.mcp.protocol_version")]
    pub avp_mcp_protocol_version: ::std::string::String,
    #[serde(
        rename = "avp.mcp.resources",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_resources: ::std::option::Option<::std::vec::Vec<ResourceDecl>>,
    #[serde(rename = "avp.mcp.server_id")]
    pub avp_mcp_server_id: AvpMcpServerId,
    #[serde(
        rename = "avp.mcp.server_name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_server_name: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.mcp.server_version",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_server_version: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.mcp.status",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_status: ::std::option::Option<McpServerConnectedDataAvpMcpStatus>,
    #[serde(rename = "avp.mcp.tool_count")]
    pub avp_mcp_tool_count: u64,
    #[serde(
        rename = "avp.mcp.tools",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_tools: ::std::option::Option<::std::vec::Vec<ToolDecl>>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`McpServerConnectedDataAvpMcpStatus`"]
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
pub enum McpServerConnectedDataAvpMcpStatus {
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
impl ::std::fmt::Display for McpServerConnectedDataAvpMcpStatus {
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
impl ::std::str::FromStr for McpServerConnectedDataAvpMcpStatus {
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
impl ::std::convert::TryFrom<&str> for McpServerConnectedDataAvpMcpStatus {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for McpServerConnectedDataAvpMcpStatus {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for McpServerConnectedDataAvpMcpStatus {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`McpServerConnectedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerConnectedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/McpServerConnectedData\""]
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
#[doc = "      \"default\": \"avp.mcp_server_connected\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.mcp_server_connected\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct McpServerConnectedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<McpServerConnectedEventAvpCorrelationId>,
    pub data: McpServerConnectedData,
    #[serde(default = "defaults::mcp_server_connected_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::mcp_server_connected_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::mcp_server_connected_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<McpServerConnectedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::mcp_server_connected_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`McpServerConnectedEventAvpCorrelationId`"]
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
pub struct McpServerConnectedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for McpServerConnectedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<McpServerConnectedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: McpServerConnectedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for McpServerConnectedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for McpServerConnectedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for McpServerConnectedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for McpServerConnectedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for McpServerConnectedEventAvpCorrelationId {
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
#[doc = "`McpServerConnectedEventSubject`"]
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
pub struct McpServerConnectedEventSubject(::std::string::String);
impl ::std::ops::Deref for McpServerConnectedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<McpServerConnectedEventSubject> for ::std::string::String {
    fn from(value: McpServerConnectedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for McpServerConnectedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for McpServerConnectedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for McpServerConnectedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for McpServerConnectedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for McpServerConnectedEventSubject {
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
#[doc = "`McpServerDisconnectedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerDisconnectedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.mcp.disconnect_reason\","]
#[doc = "    \"avp.mcp.server_id\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.mcp.disconnect_message\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Disconnect Message\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.mcp.disconnect_reason\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Disconnect Reason\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"enum\": ["]
#[doc = "        \"clean\","]
#[doc = "        \"error\""]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.mcp.server_id\": {"]
#[doc = "      \"title\": \"Avp.Mcp.Server Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
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
pub struct McpServerDisconnectedData {
    #[serde(
        rename = "avp.mcp.disconnect_message",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_mcp_disconnect_message: ::std::option::Option<::std::string::String>,
    #[serde(rename = "avp.mcp.disconnect_reason")]
    pub avp_mcp_disconnect_reason: AvpMcpDisconnectReason,
    #[serde(rename = "avp.mcp.server_id")]
    pub avp_mcp_server_id: AvpMcpServerId,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`McpServerDisconnectedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerDisconnectedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/McpServerDisconnectedData\""]
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
#[doc = "      \"default\": \"avp.mcp_server_disconnected\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.mcp_server_disconnected\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct McpServerDisconnectedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<McpServerDisconnectedEventAvpCorrelationId>,
    pub data: McpServerDisconnectedData,
    #[serde(default = "defaults::mcp_server_disconnected_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::mcp_server_disconnected_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::mcp_server_disconnected_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<McpServerDisconnectedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "type",
        default = "defaults::mcp_server_disconnected_event_type"
    )]
    pub type_: ::std::string::String,
}
#[doc = "`McpServerDisconnectedEventAvpCorrelationId`"]
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
pub struct McpServerDisconnectedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for McpServerDisconnectedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<McpServerDisconnectedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: McpServerDisconnectedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for McpServerDisconnectedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for McpServerDisconnectedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String>
    for McpServerDisconnectedEventAvpCorrelationId
{
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for McpServerDisconnectedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for McpServerDisconnectedEventAvpCorrelationId {
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
#[doc = "`McpServerDisconnectedEventSubject`"]
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
pub struct McpServerDisconnectedEventSubject(::std::string::String);
impl ::std::ops::Deref for McpServerDisconnectedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<McpServerDisconnectedEventSubject> for ::std::string::String {
    fn from(value: McpServerDisconnectedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for McpServerDisconnectedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for McpServerDisconnectedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for McpServerDisconnectedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for McpServerDisconnectedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for McpServerDisconnectedEventSubject {
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
#[doc = "`ModelTurnEndedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ModelTurnEndedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.cost_usd\","]
#[doc = "    \"duration_ms\","]
#[doc = "    \"gen_ai.usage.input_tokens\","]
#[doc = "    \"gen_ai.usage.output_tokens\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
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
#[doc = "    \"duration_ms\": {"]
#[doc = "      \"title\": \"Duration Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"gen_ai.provider.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Provider.Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"gen_ai.request.model\": {"]
#[doc = "      \"title\": \"Gen Ai.Request.Model\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"gen_ai.response.finish_reasons\": {"]
#[doc = "      \"title\": \"Gen Ai.Response.Finish Reasons\","]
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
#[doc = "    \"gen_ai.response.model\": {"]
#[doc = "      \"title\": \"Gen Ai.Response.Model\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"gen_ai.response.time_to_first_chunk\": {"]
#[doc = "      \"title\": \"Gen Ai.Response.Time To First Chunk\","]
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
#[doc = "    \"gen_ai.usage.cache_creation.input_tokens\": {"]
#[doc = "      \"title\": \"Gen Ai.Usage.Cache Creation.Input Tokens\","]
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
#[doc = "    \"gen_ai.usage.cache_read.input_tokens\": {"]
#[doc = "      \"title\": \"Gen Ai.Usage.Cache Read.Input Tokens\","]
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
#[doc = "    \"gen_ai.usage.input_tokens\": {"]
#[doc = "      \"title\": \"Gen Ai.Usage.Input Tokens\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"gen_ai.usage.output_tokens\": {"]
#[doc = "      \"title\": \"Gen Ai.Usage.Output Tokens\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"gen_ai.usage.reasoning.output_tokens\": {"]
#[doc = "      \"title\": \"Gen Ai.Usage.Reasoning.Output Tokens\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
pub struct ModelTurnEndedData {
    #[serde(
        rename = "avp.cost.source",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_cost_source: ::std::option::Option<ModelTurnEndedDataAvpCostSource>,
    #[serde(rename = "avp.cost_usd")]
    pub avp_cost_usd: f64,
    pub duration_ms: u64,
    #[serde(
        rename = "gen_ai.provider.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_provider_name: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "gen_ai.request.model",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_request_model: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "gen_ai.response.finish_reasons",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_response_finish_reasons:
        ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(
        rename = "gen_ai.response.model",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_response_model: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "gen_ai.response.time_to_first_chunk",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_response_time_to_first_chunk: ::std::option::Option<f64>,
    #[serde(
        rename = "gen_ai.usage.cache_creation.input_tokens",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_usage_cache_creation_input_tokens: ::std::option::Option<u64>,
    #[serde(
        rename = "gen_ai.usage.cache_read.input_tokens",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_usage_cache_read_input_tokens: ::std::option::Option<u64>,
    #[serde(rename = "gen_ai.usage.input_tokens")]
    pub gen_ai_usage_input_tokens: u64,
    #[serde(rename = "gen_ai.usage.output_tokens")]
    pub gen_ai_usage_output_tokens: u64,
    #[serde(
        rename = "gen_ai.usage.reasoning.output_tokens",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_usage_reasoning_output_tokens: ::std::option::Option<u64>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`ModelTurnEndedDataAvpCostSource`"]
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
pub enum ModelTurnEndedDataAvpCostSource {
    #[serde(rename = "computed")]
    Computed,
    #[serde(rename = "reported")]
    Reported,
    #[serde(rename = "unknown")]
    Unknown,
}
impl ::std::fmt::Display for ModelTurnEndedDataAvpCostSource {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Computed => f.write_str("computed"),
            Self::Reported => f.write_str("reported"),
            Self::Unknown => f.write_str("unknown"),
        }
    }
}
impl ::std::str::FromStr for ModelTurnEndedDataAvpCostSource {
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
impl ::std::convert::TryFrom<&str> for ModelTurnEndedDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ModelTurnEndedDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ModelTurnEndedDataAvpCostSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`ModelTurnEndedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ModelTurnEndedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/ModelTurnEndedData\""]
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
#[doc = "      \"default\": \"avp.model_turn_ended\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.model_turn_ended\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ModelTurnEndedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<ModelTurnEndedEventAvpCorrelationId>,
    pub data: ModelTurnEndedData,
    #[serde(default = "defaults::model_turn_ended_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::model_turn_ended_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::model_turn_ended_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ModelTurnEndedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::model_turn_ended_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ModelTurnEndedEventAvpCorrelationId`"]
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
pub struct ModelTurnEndedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for ModelTurnEndedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ModelTurnEndedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: ModelTurnEndedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ModelTurnEndedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ModelTurnEndedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ModelTurnEndedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ModelTurnEndedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ModelTurnEndedEventAvpCorrelationId {
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
#[doc = "`ModelTurnEndedEventSubject`"]
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
pub struct ModelTurnEndedEventSubject(::std::string::String);
impl ::std::ops::Deref for ModelTurnEndedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ModelTurnEndedEventSubject> for ::std::string::String {
    fn from(value: ModelTurnEndedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ModelTurnEndedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ModelTurnEndedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ModelTurnEndedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ModelTurnEndedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ModelTurnEndedEventSubject {
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
#[doc = "`ModelTurnStartedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ModelTurnStartedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.context_messages\": {"]
#[doc = "      \"title\": \"Avp.Context Messages\","]
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
#[doc = "    \"gen_ai.request.stream\": {"]
#[doc = "      \"title\": \"Gen Ai.Request.Stream\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"boolean\""]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
pub struct ModelTurnStartedData {
    #[serde(
        rename = "avp.context_messages",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_context_messages: ::std::option::Option<u64>,
    #[serde(
        rename = "gen_ai.request.stream",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_request_stream: ::std::option::Option<bool>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`ModelTurnStartedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ModelTurnStartedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/ModelTurnStartedData\""]
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
#[doc = "      \"default\": \"avp.model_turn_started\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.model_turn_started\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ModelTurnStartedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<ModelTurnStartedEventAvpCorrelationId>,
    pub data: ModelTurnStartedData,
    #[serde(default = "defaults::model_turn_started_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::model_turn_started_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::model_turn_started_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ModelTurnStartedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::model_turn_started_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ModelTurnStartedEventAvpCorrelationId`"]
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
pub struct ModelTurnStartedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for ModelTurnStartedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ModelTurnStartedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: ModelTurnStartedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ModelTurnStartedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ModelTurnStartedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ModelTurnStartedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ModelTurnStartedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ModelTurnStartedEventAvpCorrelationId {
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
#[doc = "`ModelTurnStartedEventSubject`"]
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
pub struct ModelTurnStartedEventSubject(::std::string::String);
impl ::std::ops::Deref for ModelTurnStartedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ModelTurnStartedEventSubject> for ::std::string::String {
    fn from(value: ModelTurnStartedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ModelTurnStartedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ModelTurnStartedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ModelTurnStartedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ModelTurnStartedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ModelTurnStartedEventSubject {
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
#[doc = "The model produced a reasoning / thinking block during this turn.\n\nDistinct from `text_emitted` — reasoning is not user-facing output;\nit's the model's internal chain-of-thought that some providers\nexpose (Anthropic extended thinking, OpenAI o1/o3 reasoning summaries,\netc.). Consumers can filter on this event type to redact / collapse\nchain-of-thought from displays without losing it from the audit log.\n\n`avp.reasoning.signature` rides along when the provider returns a\ncryptographic signature on the thinking block (Anthropic does this\nfor redacted_thinking blocks); empty when the provider doesn't.\n`avp.reasoning.redacted` flags blocks the provider has returned in\nencrypted-only form (no plaintext) — the wire still records the\noccurrence so audit consumers can count thinking turns."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ReasoningEmittedData\","]
#[doc = "  \"description\": \"The model produced a reasoning / thinking block during this turn.\\n\\nDistinct from `text_emitted` — reasoning is not user-facing output;\\nit's the model's internal chain-of-thought that some providers\\nexpose (Anthropic extended thinking, OpenAI o1/o3 reasoning summaries,\\netc.). Consumers can filter on this event type to redact / collapse\\nchain-of-thought from displays without losing it from the audit log.\\n\\n`avp.reasoning.signature` rides along when the provider returns a\\ncryptographic signature on the thinking block (Anthropic does this\\nfor redacted_thinking blocks); empty when the provider doesn't.\\n`avp.reasoning.redacted` flags blocks the provider has returned in\\nencrypted-only form (no plaintext) — the wire still records the\\noccurrence so audit consumers can count thinking turns.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.reasoning.text\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.reasoning.redacted\": {"]
#[doc = "      \"title\": \"Avp.Reasoning.Redacted\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"boolean\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.reasoning.signature\": {"]
#[doc = "      \"title\": \"Avp.Reasoning.Signature\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.reasoning.text\": {"]
#[doc = "      \"title\": \"Avp.Reasoning.Text\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
pub struct ReasoningEmittedData {
    #[serde(
        rename = "avp.reasoning.redacted",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_reasoning_redacted: ::std::option::Option<bool>,
    #[serde(
        rename = "avp.reasoning.signature",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_reasoning_signature: ::std::option::Option<::std::string::String>,
    #[serde(rename = "avp.reasoning.text")]
    pub avp_reasoning_text: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`ReasoningEmittedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ReasoningEmittedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/ReasoningEmittedData\""]
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
#[doc = "      \"default\": \"avp.reasoning_emitted\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.reasoning_emitted\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ReasoningEmittedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<ReasoningEmittedEventAvpCorrelationId>,
    pub data: ReasoningEmittedData,
    #[serde(default = "defaults::reasoning_emitted_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::reasoning_emitted_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::reasoning_emitted_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ReasoningEmittedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::reasoning_emitted_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ReasoningEmittedEventAvpCorrelationId`"]
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
pub struct ReasoningEmittedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for ReasoningEmittedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ReasoningEmittedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: ReasoningEmittedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ReasoningEmittedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ReasoningEmittedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ReasoningEmittedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ReasoningEmittedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ReasoningEmittedEventAvpCorrelationId {
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
#[doc = "`ReasoningEmittedEventSubject`"]
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
pub struct ReasoningEmittedEventSubject(::std::string::String);
impl ::std::ops::Deref for ReasoningEmittedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ReasoningEmittedEventSubject> for ::std::string::String {
    fn from(value: ReasoningEmittedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ReasoningEmittedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ReasoningEmittedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ReasoningEmittedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ReasoningEmittedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ReasoningEmittedEventSubject {
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
#[doc = "The model declined to generate a response or had its output filtered.\n\nCommon across providers but each exposes a different slice:\n  - Anthropic:  `stop_reason=\"refusal\"` (or `\"sensitive\"`), no\n                structured category, sometimes a refusal-flavored\n                text block.\n  - OpenAI:     `finish_reason=\"content_filter\"` plus a dedicated\n                `refusal` field on the assistant message containing\n                the model's refusal text.\n  - Gemini:     `finishReason` enum (`SAFETY`, `RECITATION`,\n                `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`) plus\n                per-category `safetyRatings`.\n\nAVP normalizes to a provider-agnostic shape: `reason` is the\nprovider's raw code (verbatim, so audit pipelines can match exact\nupstream strings), `message` is the model's refusal text when given,\n`category` is the provider's safety category (free-form because\nevery provider names them differently), `provider` lets downstream\nconsumers normalize the reason code without context-guessing.\n\nA refusal terminates the turn — the model produced no useful text or\ntool call. Whether the *run* terminates is an agent decision (the\nreference agent stops with `StopReason.refused`); a higher-level\nsupervisor may choose to reset history and retry."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RefusalRecordedData\","]
#[doc = "  \"description\": \"The model declined to generate a response or had its output filtered.\\n\\nCommon across providers but each exposes a different slice:\\n  - Anthropic:  `stop_reason=\\\"refusal\\\"` (or `\\\"sensitive\\\"`), no\\n                structured category, sometimes a refusal-flavored\\n                text block.\\n  - OpenAI:     `finish_reason=\\\"content_filter\\\"` plus a dedicated\\n                `refusal` field on the assistant message containing\\n                the model's refusal text.\\n  - Gemini:     `finishReason` enum (`SAFETY`, `RECITATION`,\\n                `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`) plus\\n                per-category `safetyRatings`.\\n\\nAVP normalizes to a provider-agnostic shape: `reason` is the\\nprovider's raw code (verbatim, so audit pipelines can match exact\\nupstream strings), `message` is the model's refusal text when given,\\n`category` is the provider's safety category (free-form because\\nevery provider names them differently), `provider` lets downstream\\nconsumers normalize the reason code without context-guessing.\\n\\nA refusal terminates the turn — the model produced no useful text or\\ntool call. Whether the *run* terminates is an agent decision (the\\nreference agent stops with `StopReason.refused`); a higher-level\\nsupervisor may choose to reset history and retry.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.refusal.reason\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
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
#[doc = "    \"avp.refusal.message\": {"]
#[doc = "      \"title\": \"Avp.Refusal.Message\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.refusal.provider\": {"]
#[doc = "      \"title\": \"Avp.Refusal.Provider\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.refusal.reason\": {"]
#[doc = "      \"title\": \"Avp.Refusal.Reason\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
pub struct RefusalRecordedData {
    #[serde(
        rename = "avp.refusal.category",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_refusal_category: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.refusal.message",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_refusal_message: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.refusal.provider",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_refusal_provider: ::std::option::Option<::std::string::String>,
    #[serde(rename = "avp.refusal.reason")]
    pub avp_refusal_reason: AvpRefusalReason,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`RefusalRecordedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RefusalRecordedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/RefusalRecordedData\""]
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
#[doc = "      \"default\": \"avp.refusal_recorded\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.refusal_recorded\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct RefusalRecordedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<RefusalRecordedEventAvpCorrelationId>,
    pub data: RefusalRecordedData,
    #[serde(default = "defaults::refusal_recorded_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::refusal_recorded_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::refusal_recorded_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<RefusalRecordedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::refusal_recorded_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`RefusalRecordedEventAvpCorrelationId`"]
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
pub struct RefusalRecordedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for RefusalRecordedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<RefusalRecordedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: RefusalRecordedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for RefusalRecordedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for RefusalRecordedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for RefusalRecordedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for RefusalRecordedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for RefusalRecordedEventAvpCorrelationId {
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
#[doc = "`RefusalRecordedEventSubject`"]
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
pub struct RefusalRecordedEventSubject(::std::string::String);
impl ::std::ops::Deref for RefusalRecordedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<RefusalRecordedEventSubject> for ::std::string::String {
    fn from(value: RefusalRecordedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for RefusalRecordedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for RefusalRecordedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for RefusalRecordedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for RefusalRecordedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for RefusalRecordedEventSubject {
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
#[doc = "MCP resource descriptor in `mcp_server_connected.data.avp.mcp.resources`.\n\nMirrors MCP's `Resource` type from the protocol spec — `uri` is the\nprimary identifier the agent uses to fetch via `resources/read`,\n`name` and `description` are display/discovery metadata, `mimeType`\nhints at the content format. Skills sourced as `mcp://<server-id>/<path>`\nin `Commission.skills[].avp.source` resolve through this catalog."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"_ResourceDecl\","]
#[doc = "  \"description\": \"MCP resource descriptor in `mcp_server_connected.data.avp.mcp.resources`.\\n\\nMirrors MCP's `Resource` type from the protocol spec — `uri` is the\\nprimary identifier the agent uses to fetch via `resources/read`,\\n`name` and `description` are display/discovery metadata, `mimeType`\\nhints at the content format. Skills sourced as `mcp://<server-id>/<path>`\\nin `Commission.skills[].avp.source` resolve through this catalog.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"uri\""]
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
#[doc = "    \"mimeType\": {"]
#[doc = "      \"title\": \"Mimetype\","]
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
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"uri\": {"]
#[doc = "      \"title\": \"Uri\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct ResourceDecl {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub description: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "mimeType",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub mime_type: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub name: ::std::option::Option<::std::string::String>,
    pub uri: Uri,
}
#[doc = "Payload of avp.run_requested events.\n\nAnchors the trajectory: the supervisor's assertion that this run was\nrequested with this Commission. Agent-relayed (the agent emits the\nevent with `source: avp://supervisor` based on `Commission.supervisor`),\nso no I/O contract change beyond Commission — but attribution is the\nsupervisor's, not the agent's.\n\n`avp.commission` is the full Commission snapshot the supervisor handed\nin. Carrying it on the wire makes the trajectory self-contained: an\nauditor can replay (or re-validate) the run from the trajectory\nalone, without an external Commission registry."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RunRequestedData\","]
#[doc = "  \"description\": \"Payload of avp.run_requested events.\\n\\nAnchors the trajectory: the supervisor's assertion that this run was\\nrequested with this Commission. Agent-relayed (the agent emits the\\nevent with `source: avp://supervisor` based on `Commission.supervisor`),\\nso no I/O contract change beyond Commission — but attribution is the\\nsupervisor's, not the agent's.\\n\\n`avp.commission` is the full Commission snapshot the supervisor handed\\nin. Carrying it on the wire makes the trajectory self-contained: an\\nauditor can replay (or re-validate) the run from the trajectory\\nalone, without an external Commission registry.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.commission\","]
#[doc = "    \"avp.supervisor.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.commission\": {"]
#[doc = "      \"title\": \"Avp.Commission\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    },"]
#[doc = "    \"avp.supervisor.name\": {"]
#[doc = "      \"title\": \"Avp.Supervisor.Name\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
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
    #[serde(rename = "avp.commission")]
    pub avp_commission: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    #[serde(rename = "avp.supervisor.name")]
    pub avp_supervisor_name: AvpSupervisorName,
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
#[doc = "First event of the trajectory. Agent-relayed but supervisor-attributed:\nthe agent emits it from `Commission.supervisor` with `source: avp://supervisor`,\nso a downstream consumer reading the wire sees the supervisor as the\nasserter of \"this run was requested with this Commission.\" Same relay\npattern as `tool_exec_resolved`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RunRequestedEvent\","]
#[doc = "  \"description\": \"First event of the trajectory. Agent-relayed but supervisor-attributed:\\nthe agent emits it from `Commission.supervisor` with `source: avp://supervisor`,\\nso a downstream consumer reading the wire sees the supervisor as the\\nasserter of \\\"this run was requested with this Commission.\\\" Same relay\\npattern as `tool_exec_resolved`.\","]
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
#[doc = "      \"default\": \"avp://supervisor\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp://supervisor\""]
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
    #[serde(rename = "type", default = "defaults::run_requested_event_type")]
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
#[doc = "Cumulative run-state used in cost_recorded and agent_stopped data.\nOpen model — supervisor SDKs can carry implementation-specific fields."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RunStateSnapshot\","]
#[doc = "  \"description\": \"Cumulative run-state used in cost_recorded and agent_stopped data.\\nOpen model — supervisor SDKs can carry implementation-specific fields.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"total_cost_usd\","]
#[doc = "    \"total_tokens\","]
#[doc = "    \"total_turns\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"duration_ms\": {"]
#[doc = "      \"title\": \"Duration Ms\","]
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
#[doc = "    \"started_at\": {"]
#[doc = "      \"title\": \"Started At\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"tokens_cache_read_total\": {"]
#[doc = "      \"title\": \"Tokens Cache Read Total\","]
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
#[doc = "    \"tokens_cache_write_total\": {"]
#[doc = "      \"title\": \"Tokens Cache Write Total\","]
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
#[doc = "    \"tokens_input_total\": {"]
#[doc = "      \"title\": \"Tokens Input Total\","]
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
#[doc = "    \"tokens_output_total\": {"]
#[doc = "      \"title\": \"Tokens Output Total\","]
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
#[doc = "    \"tools_invoked\": {"]
#[doc = "      \"title\": \"Tools Invoked\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"object\","]
#[doc = "          \"additionalProperties\": {"]
#[doc = "            \"type\": \"integer\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"total_cost_usd\": {"]
#[doc = "      \"title\": \"Total Cost Usd\","]
#[doc = "      \"type\": \"number\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"total_tokens\": {"]
#[doc = "      \"title\": \"Total Tokens\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"total_turns\": {"]
#[doc = "      \"title\": \"Total Turns\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct RunStateSnapshot {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub duration_ms: ::std::option::Option<u64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub started_at: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tokens_cache_read_total: ::std::option::Option<u64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tokens_cache_write_total: ::std::option::Option<u64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tokens_input_total: ::std::option::Option<u64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tokens_output_total: ::std::option::Option<u64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tools_invoked:
        ::std::option::Option<::std::collections::HashMap<::std::string::String, i64>>,
    pub total_cost_usd: f64,
    pub total_tokens: u64,
    pub total_turns: u64,
}
#[doc = "Skill descriptor in `agent_started.data.skills` — name plus\noptional metadata about each skill loaded for the run.\n\nReplaces the v0.1-prototype `list[str]` shape (names-only) with a\nstructured decl matching `_ToolDecl` / `_SubagentDecl`. Description\ncomes from the SKILL.md frontmatter when the agent surfaces it\n(e.g. via `ClaudeSDKClient.get_context_usage()` which returns a\n`skills` breakdown including frontmatter); `avp.source` is the\nSKILL.md path / URI when known.\n\nAll fields except `name` are optional so agents that only know\nthe name (Commission-declared without enrichment) still emit valid\ndecls."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"_SkillDecl\","]
#[doc = "  \"description\": \"Skill descriptor in `agent_started.data.skills` — name plus\\noptional metadata about each skill loaded for the run.\\n\\nReplaces the v0.1-prototype `list[str]` shape (names-only) with a\\nstructured decl matching `_ToolDecl` / `_SubagentDecl`. Description\\ncomes from the SKILL.md frontmatter when the agent surfaces it\\n(e.g. via `ClaudeSDKClient.get_context_usage()` which returns a\\n`skills` breakdown including frontmatter); `avp.source` is the\\nSKILL.md path / URI when known.\\n\\nAll fields except `name` are optional so agents that only know\\nthe name (Commission-declared without enrichment) still emit valid\\ndecls.\","]
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
}
#[doc = "Payload of `avp.skill_loaded` events.\n\nSemantics: emitted when the SKILL.md body content has been added to\nthe model's active context window. NOT a registration acknowledgment\n— the registration view is `agent_started.data.skills[]`.\n\nTwo emission patterns, differentiated by the agent's\n`manifest.capabilities`:\n\n  - `skills:eager` — agent injects all declared SKILL.md bodies at\n    startup (e.g., as system_prompt suffix). Emit once per skill at\n    `step=0`, after `agent_started` and `mcp_server_connected`.\n  - `skills:progressive` — model decides per-turn which skill bodies\n    to pull in (Anthropic Skills, Claude Code progressive disclosure).\n    Emit when the body actually enters context, with `step=N` matching\n    the turn it loaded in. MAY fire multiple times for the same\n    skill (e.g., re-load after compaction).\n\nAgents whose SDK does not expose progressive-disclosure load events\nSHOULD NOT emit `skill_loaded` at all — `agent_started.data.skills[]`\nstill records the registration. Honest-silent beats fabricated events."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SkillLoadedData\","]
#[doc = "  \"description\": \"Payload of `avp.skill_loaded` events.\\n\\nSemantics: emitted when the SKILL.md body content has been added to\\nthe model's active context window. NOT a registration acknowledgment\\n— the registration view is `agent_started.data.skills[]`.\\n\\nTwo emission patterns, differentiated by the agent's\\n`manifest.capabilities`:\\n\\n  - `skills:eager` — agent injects all declared SKILL.md bodies at\\n    startup (e.g., as system_prompt suffix). Emit once per skill at\\n    `step=0`, after `agent_started` and `mcp_server_connected`.\\n  - `skills:progressive` — model decides per-turn which skill bodies\\n    to pull in (Anthropic Skills, Claude Code progressive disclosure).\\n    Emit when the body actually enters context, with `step=N` matching\\n    the turn it loaded in. MAY fire multiple times for the same\\n    skill (e.g., re-load after compaction).\\n\\nAgents whose SDK does not expose progressive-disclosure load events\\nSHOULD NOT emit `skill_loaded` at all — `agent_started.data.skills[]`\\nstill records the registration. Honest-silent beats fabricated events.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.skill.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.skill.name\": {"]
#[doc = "      \"title\": \"Avp.Skill.Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.skill.source\": {"]
#[doc = "      \"title\": \"Avp.Skill.Source\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
pub struct SkillLoadedData {
    #[serde(rename = "avp.skill.name")]
    pub avp_skill_name: ::std::string::String,
    #[serde(
        rename = "avp.skill.source",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_skill_source: ::std::option::Option<::std::string::String>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`SkillLoadedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SkillLoadedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/SkillLoadedData\""]
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
#[doc = "      \"default\": \"avp.skill_loaded\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.skill_loaded\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SkillLoadedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<SkillLoadedEventAvpCorrelationId>,
    pub data: SkillLoadedData,
    #[serde(default = "defaults::skill_loaded_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::skill_loaded_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::skill_loaded_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<SkillLoadedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::skill_loaded_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`SkillLoadedEventAvpCorrelationId`"]
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
pub struct SkillLoadedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for SkillLoadedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SkillLoadedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: SkillLoadedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SkillLoadedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SkillLoadedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SkillLoadedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SkillLoadedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SkillLoadedEventAvpCorrelationId {
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
#[doc = "`SkillLoadedEventSubject`"]
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
pub struct SkillLoadedEventSubject(::std::string::String);
impl ::std::ops::Deref for SkillLoadedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SkillLoadedEventSubject> for ::std::string::String {
    fn from(value: SkillLoadedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SkillLoadedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SkillLoadedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SkillLoadedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SkillLoadedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SkillLoadedEventSubject {
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
#[doc = "Why a run terminated. v0.1 keeps the enum tight: model said done,\nmodel declined, agent crashed, or operator interrupted. Cap-driven\nstop reasons (turn / token / cost / duration limits) are not part of\nv0.1 — agents that need bounded execution wire it externally\n(subprocess timeouts, supervisor SIGKILL)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"StopReason\","]
#[doc = "  \"description\": \"Why a run terminated. v0.1 keeps the enum tight: model said done,\\nmodel declined, agent crashed, or operator interrupted. Cap-driven\\nstop reasons (turn / token / cost / duration limits) are not part of\\nv0.1 — agents that need bounded execution wire it externally\\n(subprocess timeouts, supervisor SIGKILL).\","]
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
#[doc = "Subagent descriptor in `agent_started.data.subagents` — what the\nparent model sees when deciding whether to delegate. Same MCP-shaped\ntriple (`name`, `description`, `inputSchema`) tools use, so adapters\ncan render subagents to the model's tool list with no translation.\n\n`description` is optional to match `_ToolDecl`: when surfacing a\nagent-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)\nthe agent has authoritative knowledge of the name but not the prose\ndescription. Honest-null beats authored-prose-that-drifts."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"_SubagentDecl\","]
#[doc = "  \"description\": \"Subagent descriptor in `agent_started.data.subagents` — what the\\nparent model sees when deciding whether to delegate. Same MCP-shaped\\ntriple (`name`, `description`, `inputSchema`) tools use, so adapters\\ncan render subagents to the model's tool list with no translation.\\n\\n`description` is optional to match `_ToolDecl`: when surfacing a\\nagent-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)\\nthe agent has authoritative knowledge of the name but not the prose\\ndescription. Honest-null beats authored-prose-that-drifts.\","]
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
#[doc = "Subagent invocation errored. The parent treats the error as a\ntool-call failure: the model receives an `Error: ...` string in place\nof the result and may retry or proceed."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentFailedData\","]
#[doc = "  \"description\": \"Subagent invocation errored. The parent treats the error as a\\ntool-call failure: the model receives an `Error: ...` string in place\\nof the result and may retry or proceed.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.subagent.error\","]
#[doc = "    \"avp.subagent.invocation_id\","]
#[doc = "    \"duration_ms\","]
#[doc = "    \"gen_ai.agent.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.subagent.error\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Error\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.subagent.error.code\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Error.Code\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.subagent.invocation_id\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Invocation Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"duration_ms\": {"]
#[doc = "      \"title\": \"Duration Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"gen_ai.agent.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Agent.Name\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
pub struct SubagentFailedData {
    #[serde(rename = "avp.subagent.error")]
    pub avp_subagent_error: ::std::string::String,
    #[serde(
        rename = "avp.subagent.error.code",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_subagent_error_code: ::std::option::Option<::std::string::String>,
    #[serde(rename = "avp.subagent.invocation_id")]
    pub avp_subagent_invocation_id: AvpSubagentInvocationId,
    pub duration_ms: u64,
    #[serde(rename = "gen_ai.agent.name")]
    pub gen_ai_agent_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`SubagentFailedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentFailedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/SubagentFailedData\""]
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
#[doc = "      \"default\": \"avp.subagent_failed\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.subagent_failed\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SubagentFailedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<SubagentFailedEventAvpCorrelationId>,
    pub data: SubagentFailedData,
    #[serde(default = "defaults::subagent_failed_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::subagent_failed_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::subagent_failed_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<SubagentFailedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::subagent_failed_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`SubagentFailedEventAvpCorrelationId`"]
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
pub struct SubagentFailedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for SubagentFailedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentFailedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: SubagentFailedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentFailedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentFailedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentFailedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentFailedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentFailedEventAvpCorrelationId {
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
#[doc = "`SubagentFailedEventSubject`"]
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
pub struct SubagentFailedEventSubject(::std::string::String);
impl ::std::ops::Deref for SubagentFailedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentFailedEventSubject> for ::std::string::String {
    fn from(value: SubagentFailedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentFailedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentFailedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentFailedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentFailedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentFailedEventSubject {
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
#[doc = "Parent agent delegates to a declared subagent.\n\nThe event's `span_id` IS the subagent's frame span. Events emitted by\nthe subagent's sub-loop set `parent_span_id` to this frame (or chain\nthrough descendants of it), so the trajectory reconstructs as a nested\ntree. Per OTel GenAI semconv §invoke_agent, `gen_ai.operation.name` is\n`invoke_agent` and `gen_ai.agent.name` carries the subagent's declared\nname."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentInvokedData\","]
#[doc = "  \"description\": \"Parent agent delegates to a declared subagent.\\n\\nThe event's `span_id` IS the subagent's frame span. Events emitted by\\nthe subagent's sub-loop set `parent_span_id` to this frame (or chain\\nthrough descendants of it), so the trajectory reconstructs as a nested\\ntree. Per OTel GenAI semconv §invoke_agent, `gen_ai.operation.name` is\\n`invoke_agent` and `gen_ai.agent.name` carries the subagent's declared\\nname.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.subagent.input\","]
#[doc = "    \"avp.subagent.invocation_id\","]
#[doc = "    \"gen_ai.agent.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
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
#[doc = "    \"gen_ai.agent.description\": {"]
#[doc = "      \"title\": \"Gen Ai.Agent.Description\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"gen_ai.agent.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Agent.Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"gen_ai.operation.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Operation.Name\","]
#[doc = "      \"default\": \"invoke_agent\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"invoke_agent\""]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
    #[serde(rename = "avp.subagent.input")]
    pub avp_subagent_input: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    #[serde(rename = "avp.subagent.invocation_id")]
    pub avp_subagent_invocation_id: AvpSubagentInvocationId,
    #[serde(
        rename = "gen_ai.agent.description",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_agent_description: ::std::option::Option<::std::string::String>,
    #[serde(rename = "gen_ai.agent.name")]
    pub gen_ai_agent_name: ::std::string::String,
    #[serde(
        rename = "gen_ai.operation.name",
        default = "defaults::subagent_invoked_data_gen_ai_operation_name"
    )]
    pub gen_ai_operation_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
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
    #[serde(rename = "type", default = "defaults::subagent_invoked_event_type")]
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
#[doc = "Closes the subagent's frame. `span_id` matches the corresponding\n`subagent_invoked` event so consumers can pair them. `avp.subagent.usage`\nrolls up the subagent's own consumption (cost, tokens, turns) — this\nrollup is also reflected in the parent run's cumulative state, but the\nbreakdown is preserved here so consumers can attribute spend to the\nsubagent that incurred it."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentReturnedData\","]
#[doc = "  \"description\": \"Closes the subagent's frame. `span_id` matches the corresponding\\n`subagent_invoked` event so consumers can pair them. `avp.subagent.usage`\\nrolls up the subagent's own consumption (cost, tokens, turns) — this\\nrollup is also reflected in the parent run's cumulative state, but the\\nbreakdown is preserved here so consumers can attribute spend to the\\nsubagent that incurred it.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.subagent.invocation_id\","]
#[doc = "    \"avp.subagent.reason\","]
#[doc = "    \"avp.subagent.result.text\","]
#[doc = "    \"avp.subagent.usage\","]
#[doc = "    \"duration_ms\","]
#[doc = "    \"gen_ai.agent.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.subagent.invocation_id\": {"]
#[doc = "      \"title\": \"Avp.Subagent.Invocation Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
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
#[doc = "      \"$ref\": \"#/$defs/RunStateSnapshot\""]
#[doc = "    },"]
#[doc = "    \"duration_ms\": {"]
#[doc = "      \"title\": \"Duration Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"gen_ai.agent.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Agent.Name\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
    #[serde(rename = "avp.subagent.invocation_id")]
    pub avp_subagent_invocation_id: AvpSubagentInvocationId,
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
    #[serde(rename = "avp.subagent.usage")]
    pub avp_subagent_usage: RunStateSnapshot,
    pub duration_ms: u64,
    #[serde(rename = "gen_ai.agent.name")]
    pub gen_ai_agent_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
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
    #[serde(rename = "type", default = "defaults::subagent_returned_event_type")]
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
#[doc = "`TextEmittedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"TextEmittedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.text\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.text\": {"]
#[doc = "      \"title\": \"Avp.Text\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
pub struct TextEmittedData {
    #[serde(rename = "avp.text")]
    pub avp_text: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`TextEmittedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"TextEmittedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/TextEmittedData\""]
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
#[doc = "      \"default\": \"avp.text_emitted\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.text_emitted\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct TextEmittedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<TextEmittedEventAvpCorrelationId>,
    pub data: TextEmittedData,
    #[serde(default = "defaults::text_emitted_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::text_emitted_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::text_emitted_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<TextEmittedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::text_emitted_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`TextEmittedEventAvpCorrelationId`"]
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
pub struct TextEmittedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for TextEmittedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<TextEmittedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: TextEmittedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for TextEmittedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for TextEmittedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for TextEmittedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for TextEmittedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for TextEmittedEventAvpCorrelationId {
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
#[doc = "`TextEmittedEventSubject`"]
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
pub struct TextEmittedEventSubject(::std::string::String);
impl ::std::ops::Deref for TextEmittedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<TextEmittedEventSubject> for ::std::string::String {
    fn from(value: TextEmittedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for TextEmittedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for TextEmittedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for TextEmittedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for TextEmittedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for TextEmittedEventSubject {
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
#[doc = "Tool descriptor in `agent_started.data.tools` — MCP-shaped + AVP fields."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"_ToolDecl\","]
#[doc = "  \"description\": \"Tool descriptor in `agent_started.data.tools` — MCP-shaped + AVP fields.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.dispatch_target\": {"]
#[doc = "      \"title\": \"Avp.Dispatch Target\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"enum\": ["]
#[doc = "            \"mcp_server\","]
#[doc = "            \"local\","]
#[doc = "            \"hosted\""]
#[doc = "          ]"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
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
        rename = "avp.dispatch_target",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_dispatch_target: ::std::option::Option<ToolDeclAvpDispatchTarget>,
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
#[doc = "`ToolDeclAvpDispatchTarget`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"mcp_server\","]
#[doc = "    \"local\","]
#[doc = "    \"hosted\""]
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
pub enum ToolDeclAvpDispatchTarget {
    #[serde(rename = "mcp_server")]
    McpServer,
    #[serde(rename = "local")]
    Local,
    #[serde(rename = "hosted")]
    Hosted,
}
impl ::std::fmt::Display for ToolDeclAvpDispatchTarget {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::McpServer => f.write_str("mcp_server"),
            Self::Local => f.write_str("local"),
            Self::Hosted => f.write_str("hosted"),
        }
    }
}
impl ::std::str::FromStr for ToolDeclAvpDispatchTarget {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "mcp_server" => Ok(Self::McpServer),
            "local" => Ok(Self::Local),
            "hosted" => Ok(Self::Hosted),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for ToolDeclAvpDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolDeclAvpDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolDeclAvpDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`ToolFailedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolFailedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.tool.error\","]
#[doc = "    \"gen_ai.tool.call.id\","]
#[doc = "    \"gen_ai.tool.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.tool.error\": {"]
#[doc = "      \"title\": \"Avp.Tool.Error\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"avp.tool.error.code\": {"]
#[doc = "      \"title\": \"Avp.Tool.Error.Code\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.call.id\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Call.Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Name\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
pub struct ToolFailedData {
    #[serde(rename = "avp.tool.error")]
    pub avp_tool_error: ::std::string::String,
    #[serde(
        rename = "avp.tool.error.code",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tool_error_code: ::std::option::Option<::std::string::String>,
    #[serde(rename = "gen_ai.tool.call.id")]
    pub gen_ai_tool_call_id: GenAiToolCallId,
    #[serde(rename = "gen_ai.tool.name")]
    pub gen_ai_tool_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`ToolFailedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolFailedEvent\","]
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
#[doc = "      \"$ref\": \"#/$defs/ToolFailedData\""]
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
#[doc = "      \"default\": \"avp.tool_failed\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"avp.tool_failed\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ToolFailedEvent {
    #[serde(
        rename = "avp.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_correlation_id: ::std::option::Option<ToolFailedEventAvpCorrelationId>,
    pub data: ToolFailedData,
    #[serde(default = "defaults::tool_failed_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::tool_failed_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::tool_failed_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ToolFailedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::tool_failed_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ToolFailedEventAvpCorrelationId`"]
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
pub struct ToolFailedEventAvpCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolFailedEventAvpCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolFailedEventAvpCorrelationId> for ::std::string::String {
    fn from(value: ToolFailedEventAvpCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolFailedEventAvpCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolFailedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolFailedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolFailedEventAvpCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolFailedEventAvpCorrelationId {
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
#[doc = "`ToolFailedEventSubject`"]
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
pub struct ToolFailedEventSubject(::std::string::String);
impl ::std::ops::Deref for ToolFailedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolFailedEventSubject> for ::std::string::String {
    fn from(value: ToolFailedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolFailedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolFailedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolFailedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolFailedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolFailedEventSubject {
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
#[doc = "`ToolInvokedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolInvokedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"gen_ai.tool.call.arguments\","]
#[doc = "    \"gen_ai.tool.call.id\","]
#[doc = "    \"gen_ai.tool.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.tool.dispatch_target\": {"]
#[doc = "      \"title\": \"Avp.Tool.Dispatch Target\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"enum\": ["]
#[doc = "            \"mcp_server\","]
#[doc = "            \"local\","]
#[doc = "            \"hosted\""]
#[doc = "          ]"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.tool.subtype\": {"]
#[doc = "      \"title\": \"Avp.Tool.Subtype\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.call.arguments\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Call.Arguments\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.call.id\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Call.Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Name\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
        rename = "avp.tool.dispatch_target",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tool_dispatch_target: ::std::option::Option<ToolInvokedDataAvpToolDispatchTarget>,
    #[serde(
        rename = "avp.tool.subtype",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tool_subtype: ::std::option::Option<::std::string::String>,
    #[serde(rename = "gen_ai.tool.call.arguments")]
    pub gen_ai_tool_call_arguments: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    #[serde(rename = "gen_ai.tool.call.id")]
    pub gen_ai_tool_call_id: GenAiToolCallId,
    #[serde(rename = "gen_ai.tool.name")]
    pub gen_ai_tool_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
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
#[doc = "    \"local\","]
#[doc = "    \"hosted\""]
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
    #[serde(rename = "hosted")]
    Hosted,
}
impl ::std::fmt::Display for ToolInvokedDataAvpToolDispatchTarget {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::McpServer => f.write_str("mcp_server"),
            Self::Local => f.write_str("local"),
            Self::Hosted => f.write_str("hosted"),
        }
    }
}
impl ::std::str::FromStr for ToolInvokedDataAvpToolDispatchTarget {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "mcp_server" => Ok(Self::McpServer),
            "local" => Ok(Self::Local),
            "hosted" => Ok(Self::Hosted),
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
    #[serde(rename = "type", default = "defaults::tool_invoked_event_type")]
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
#[doc = "`ToolReturnedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolReturnedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"avp.tool.result.text\","]
#[doc = "    \"duration_ms\","]
#[doc = "    \"gen_ai.tool.call.id\","]
#[doc = "    \"gen_ai.tool.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"avp.tool.rejected\": {"]
#[doc = "      \"title\": \"Avp.Tool.Rejected\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"boolean\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.tool.rejection_reason\": {"]
#[doc = "      \"title\": \"Avp.Tool.Rejection Reason\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.tool.result.structured\": {"]
#[doc = "      \"title\": \"Avp.Tool.Result.Structured\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {},"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"avp.tool.result.text\": {"]
#[doc = "      \"title\": \"Avp.Tool.Result.Text\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"duration_ms\": {"]
#[doc = "      \"title\": \"Duration Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.call.id\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Call.Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Name\","]
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
#[doc = "    \"step\": {"]
#[doc = "      \"title\": \"Step\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
    #[serde(
        rename = "avp.tool.rejected",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tool_rejected: ::std::option::Option<bool>,
    #[serde(
        rename = "avp.tool.rejection_reason",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tool_rejection_reason: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "avp.tool.result.structured",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub avp_tool_result_structured: ::std::option::Option<::serde_json::Value>,
    #[serde(rename = "avp.tool.result.text")]
    pub avp_tool_result_text: ::std::string::String,
    pub duration_ms: u64,
    #[serde(rename = "gen_ai.tool.call.id")]
    pub gen_ai_tool_call_id: GenAiToolCallId,
    #[serde(rename = "gen_ai.tool.name")]
    pub gen_ai_tool_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
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
    #[serde(rename = "type", default = "defaults::tool_returned_event_type")]
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
#[doc = "`Uri`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Uri\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct Uri(::std::string::String);
impl ::std::ops::Deref for Uri {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<Uri> for ::std::string::String {
    fn from(value: Uri) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for Uri {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for Uri {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for Uri {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Uri {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for Uri {
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
    pub(super) fn agent_started_data_avp_schema_version() -> ::std::string::String {
        "0.1".to_string()
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
    pub(super) fn cost_recorded_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn cost_recorded_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn cost_recorded_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn cost_recorded_event_type() -> ::std::string::String {
        "avp.cost_recorded".to_string()
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
    pub(super) fn mcp_server_connected_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn mcp_server_connected_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn mcp_server_connected_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn mcp_server_connected_event_type() -> ::std::string::String {
        "avp.mcp_server_connected".to_string()
    }
    pub(super) fn mcp_server_disconnected_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn mcp_server_disconnected_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn mcp_server_disconnected_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn mcp_server_disconnected_event_type() -> ::std::string::String {
        "avp.mcp_server_disconnected".to_string()
    }
    pub(super) fn model_turn_ended_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn model_turn_ended_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn model_turn_ended_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn model_turn_ended_event_type() -> ::std::string::String {
        "avp.model_turn_ended".to_string()
    }
    pub(super) fn model_turn_started_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn model_turn_started_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn model_turn_started_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn model_turn_started_event_type() -> ::std::string::String {
        "avp.model_turn_started".to_string()
    }
    pub(super) fn reasoning_emitted_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn reasoning_emitted_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn reasoning_emitted_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn reasoning_emitted_event_type() -> ::std::string::String {
        "avp.reasoning_emitted".to_string()
    }
    pub(super) fn refusal_recorded_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn refusal_recorded_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn refusal_recorded_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn refusal_recorded_event_type() -> ::std::string::String {
        "avp.refusal_recorded".to_string()
    }
    pub(super) fn run_requested_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn run_requested_event_source() -> ::std::string::String {
        "avp://supervisor".to_string()
    }
    pub(super) fn run_requested_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn run_requested_event_type() -> ::std::string::String {
        "avp.run_requested".to_string()
    }
    pub(super) fn skill_loaded_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn skill_loaded_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn skill_loaded_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn skill_loaded_event_type() -> ::std::string::String {
        "avp.skill_loaded".to_string()
    }
    pub(super) fn subagent_failed_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn subagent_failed_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn subagent_failed_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn subagent_failed_event_type() -> ::std::string::String {
        "avp.subagent_failed".to_string()
    }
    pub(super) fn subagent_invoked_data_gen_ai_operation_name() -> ::std::string::String {
        "invoke_agent".to_string()
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
    pub(super) fn text_emitted_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn text_emitted_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn text_emitted_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn text_emitted_event_type() -> ::std::string::String {
        "avp.text_emitted".to_string()
    }
    pub(super) fn tool_failed_event_datacontenttype() -> ::std::option::Option<::std::string::String>
    {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_failed_event_source() -> ::std::string::String {
        "avp://agent".to_string()
    }
    pub(super) fn tool_failed_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_failed_event_type() -> ::std::string::String {
        "avp.tool_failed".to_string()
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
}
