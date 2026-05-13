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
#[doc = "The agent's self-description. Enumerates built-in tools, subagents, and skills triggerable without supervisor configuration, plus the agent's identity, capabilities, and supported models. Pre-flight (`<agent> describe` stdout) and run-time (`agent_described.data['avp.descriptor']`) views MUST match for the same agent build. See spec/v0.1/agent-descriptor.md."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"$id\": \"https://avp.dev/schema/v0.1/agent-descriptor.schema.json\","]
#[doc = "  \"title\": \"AVP v0.1 Agent Descriptor\","]
#[doc = "  \"description\": \"The agent's self-description. Enumerates built-in tools, subagents, and skills triggerable without supervisor configuration, plus the agent's identity, capabilities, and supported models. Pre-flight (`<agent> describe` stdout) and run-time (`agent_described.data['avp.descriptor']`) views MUST match for the same agent build. See spec/v0.1/agent-descriptor.md.\","]
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
pub struct AvpV01AgentDescriptor {
    pub agent_name: AgentName,
    pub agent_version: AgentVersion,
    pub avp_spec_version: ::std::string::String,
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
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subagents: ::std::option::Option<::std::vec::Vec<SubagentDecl>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub supported_models: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub system_prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tools: ::std::option::Option<::std::vec::Vec<ToolDecl>>,
}
#[doc = "`Id`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1,"]
#[doc = "  \"pattern\": \"^[a-z0-9_-]+$\""]
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
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| ::regress::Regex::new("^[a-z0-9_-]+$").unwrap());
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[a-z0-9_-]+$\"".into());
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
#[doc = "MCP server descriptor in `AgentDescriptor.mcp_servers`: identity only.\n\nConnection material (URLs, auth, command-lines) stays inside the agent\nprocess and is NOT carried on the descriptor wire. The descriptor\nrecords only the server's id and an optional description; the tools\nthe server surfaces are NOT enumerated on the descriptor — they appear\nat runtime on `mcp_server_connected.data[\"avp.mcp.tools\"]`. The id-pattern\nmirrors `Commission.McpServerRef.id` so cross-source id-collision\ndetection at startup is straight string\nequality."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerDecl\","]
#[doc = "  \"description\": \"MCP server descriptor in `AgentDescriptor.mcp_servers`: identity only.\\n\\nConnection material (URLs, auth, command-lines) stays inside the agent\\nprocess and is NOT carried on the descriptor wire. The descriptor\\nrecords only the server's id and an optional description; the tools\\nthe server surfaces are NOT enumerated on the descriptor — they appear\\nat runtime on `mcp_server_connected.data[\\\"avp.mcp.tools\\\"]`. The id-pattern\\nmirrors `Commission.McpServerRef.id` so cross-source id-collision\\ndetection at startup is straight string\\nequality.\","]
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
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9_-]+$\""]
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
}
#[doc = "Skill descriptor in `AgentDescriptor.skills` and\n`agent_started.data.skills`: name plus optional metadata about each\nskill the agent ships with or has loaded for the run.\n\nReplaces the v0.1-prototype `list[str]` shape (names-only) with a\nstructured decl matching `ToolDecl` / `SubagentDecl`. Description\ncomes from the SKILL.md frontmatter when the agent surfaces it\n(e.g. via `ClaudeSDKClient.get_context_usage()` which returns a\n`skills` breakdown including frontmatter); `version` is the skill's\nown version when known; `avp.source` is the SKILL.md path / URI.\n\nAll fields except `name` are optional so agents that only know\nthe name (Commission-declared without enrichment) still emit valid\ndecls."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SkillDecl\","]
#[doc = "  \"description\": \"Skill descriptor in `AgentDescriptor.skills` and\\n`agent_started.data.skills`: name plus optional metadata about each\\nskill the agent ships with or has loaded for the run.\\n\\nReplaces the v0.1-prototype `list[str]` shape (names-only) with a\\nstructured decl matching `ToolDecl` / `SubagentDecl`. Description\\ncomes from the SKILL.md frontmatter when the agent surfaces it\\n(e.g. via `ClaudeSDKClient.get_context_usage()` which returns a\\n`skills` breakdown including frontmatter); `version` is the skill's\\nown version when known; `avp.source` is the SKILL.md path / URI.\\n\\nAll fields except `name` are optional so agents that only know\\nthe name (Commission-declared without enrichment) still emit valid\\ndecls.\","]
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
#[doc = "Subagent descriptor in `agent_started.data.subagents`: what the\nparent model sees when deciding whether to delegate. Same MCP-shaped\ntriple (`name`, `description`, `inputSchema`) tools use, so adapters\ncan render subagents to the model's tool list with no translation.\n\n`description` is optional to match `ToolDecl`: when surfacing a\nagent-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)\nthe agent has authoritative knowledge of the name but not the prose\ndescription. Honest-null beats authored-prose-that-drifts."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentDecl\","]
#[doc = "  \"description\": \"Subagent descriptor in `agent_started.data.subagents`: what the\\nparent model sees when deciding whether to delegate. Same MCP-shaped\\ntriple (`name`, `description`, `inputSchema`) tools use, so adapters\\ncan render subagents to the model's tool list with no translation.\\n\\n`description` is optional to match `ToolDecl`: when surfacing a\\nagent-built-in subagent (e.g. the Claude Agent SDK's `general-purpose`)\\nthe agent has authoritative knowledge of the name but not the prose\\ndescription. Honest-null beats authored-prose-that-drifts.\","]
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
#[doc = "Tool descriptor used by `AgentDescriptor.tools`,\n`agent_started.data.tools`, and `mcp_server_connected.data.avp.mcp.tools`.\n\nMCP-shaped: `name` plus optional `description` and `inputSchema`. The\ndecl describes a single tool's model-facing identity; how the tool is\n*dispatched* (local vs MCP server) is implicit from where the decl\nappears on the wire — `descriptor.tools` and `agent_started.data.tools`\nare local-only; entries under `mcp_server_connected.data.avp.mcp.tools`\nare MCP-dispatched by virtue of being nested under a server. The\nper-invocation discriminator lives on `tool_invoked.data[\"avp.tool.dispatch_target\"]`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolDecl\","]
#[doc = "  \"description\": \"Tool descriptor used by `AgentDescriptor.tools`,\\n`agent_started.data.tools`, and `mcp_server_connected.data.avp.mcp.tools`.\\n\\nMCP-shaped: `name` plus optional `description` and `inputSchema`. The\\ndecl describes a single tool's model-facing identity; how the tool is\\n*dispatched* (local vs MCP server) is implicit from where the decl\\nappears on the wire — `descriptor.tools` and `agent_started.data.tools`\\nare local-only; entries under `mcp_server_connected.data.avp.mcp.tools`\\nare MCP-dispatched by virtue of being nested under a server. The\\nper-invocation discriminator lives on `tool_invoked.data[\\\"avp.tool.dispatch_target\\\"]`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"name\""]
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
