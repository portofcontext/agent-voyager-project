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
#[doc = "Supervisor → agent setup message. Declares the agent's complete environment (mcp_servers, allowed_tools, skills, subagents, prompts). Sent once at startup. The supervisor MUST NOT modify the environment mid-run."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"$id\": \"https://avp.dev/schema/v0.1/commission.schema.json\","]
#[doc = "  \"title\": \"AVP v0.1 Commission\","]
#[doc = "  \"description\": \"Supervisor → agent setup message. Declares the agent's complete environment (mcp_servers, allowed_tools, skills, subagents, prompts). Sent once at startup. The supervisor MUST NOT modify the environment mid-run.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"run_id\","]
#[doc = "    \"schema_version\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
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
#[doc = "            \"$ref\": \"#/$defs/McpServerRef\""]
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
#[doc = "            \"$ref\": \"#/$defs/SkillRef\""]
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
#[doc = "            \"$ref\": \"#/$defs/SubagentRef\""]
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
pub struct AvpV01Commission {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub enabled_builtin_skills: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub enabled_builtin_subagents: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub enabled_builtin_tools: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub mcp_servers: ::std::option::Option<::std::vec::Vec<McpServerRef>>,
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
    pub skills: ::std::option::Option<::std::vec::Vec<SkillRef>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subagents: ::std::option::Option<::std::vec::Vec<SubagentRef>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub supervisor: ::std::option::Option<SupervisorPreamble>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub system_prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tags: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub thread_id: ::std::option::Option<::std::string::String>,
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
#[doc = "`JsonValue`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(transparent)]
pub struct JsonValue(pub ::serde_json::Value);
impl ::std::ops::Deref for JsonValue {
    type Target = ::serde_json::Value;
    fn deref(&self) -> &::serde_json::Value {
        &self.0
    }
}
impl ::std::convert::From<JsonValue> for ::serde_json::Value {
    fn from(value: JsonValue) -> Self {
        value.0
    }
}
impl ::std::convert::From<::serde_json::Value> for JsonValue {
    fn from(value: ::serde_json::Value) -> Self {
        Self(value)
    }
}
#[doc = "Reference to a supervisor-managed MCP server.\n\nThe agent resolves this entry at startup by calling `avp.resolve` with\n`{kind: \"mcp_server\", id, ref}`. The resolver returns the connection\nmaterial (transport, URL, auth, etc.) the agent uses to dial the actual\nMCP server. Per-`kind` result schemas are pinned in SPEC.md. Auth and\ntransport are deployment concerns — AVP does not constrain them."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServerRef\","]
#[doc = "  \"description\": \"Reference to a supervisor-managed MCP server.\\n\\nThe agent resolves this entry at startup by calling `avp.resolve` with\\n`{kind: \\\"mcp_server\\\", id, ref}`. The resolver returns the connection\\nmaterial (transport, URL, auth, etc.) the agent uses to dial the actual\\nMCP server. Per-`kind` result schemas are pinned in SPEC.md. Auth and\\ntransport are deployment concerns — AVP does not constrain them.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\","]
#[doc = "    \"ref\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9_-]+$\""]
#[doc = "    },"]
#[doc = "    \"ref\": {"]
#[doc = "      \"$ref\": \"#/$defs/JsonValue\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct McpServerRef {
    pub id: Id,
    #[serde(rename = "ref")]
    pub ref_: JsonValue,
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
#[doc = "Reference to a supervisor-managed skill.\n\nThe agent resolves this entry at startup by calling `avp.resolve` with\n`{kind: \"skill\", id, ref}`. The resolver returns the SKILL.md content\n(or a location the agent fetches and reads) — agentskills.io's content\nmodel still applies; the resolver just hands the content back from\nwhatever store the supervisor uses."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SkillRef\","]
#[doc = "  \"description\": \"Reference to a supervisor-managed skill.\\n\\nThe agent resolves this entry at startup by calling `avp.resolve` with\\n`{kind: \\\"skill\\\", id, ref}`. The resolver returns the SKILL.md content\\n(or a location the agent fetches and reads) — agentskills.io's content\\nmodel still applies; the resolver just hands the content back from\\nwhatever store the supervisor uses.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\","]
#[doc = "    \"ref\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9_-]+$\""]
#[doc = "    },"]
#[doc = "    \"ref\": {"]
#[doc = "      \"$ref\": \"#/$defs/JsonValue\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SkillRef {
    pub id: Id,
    #[serde(rename = "ref")]
    pub ref_: JsonValue,
}
#[doc = "Reference to a supervisor-managed subagent.\n\nThe agent resolves this entry at startup by calling `avp.resolve` with\n`{kind: \"subagent\", id, ref}`; the resolver returns the model-facing\nmetadata (`name`, `description`, `inputSchema`) so the parent's model\ncan decide whether to delegate. When the model invokes the subagent at\nruntime, the agent calls `avp.spawn_subagent` with the same ref to\nobtain a child `run_id`. The subagent run carries its own complete\ntrajectory; the parent's `subagent_invoked.data[\"avp.subagent.run_id\"]`\nreferences it."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentRef\","]
#[doc = "  \"description\": \"Reference to a supervisor-managed subagent.\\n\\nThe agent resolves this entry at startup by calling `avp.resolve` with\\n`{kind: \\\"subagent\\\", id, ref}`; the resolver returns the model-facing\\nmetadata (`name`, `description`, `inputSchema`) so the parent's model\\ncan decide whether to delegate. When the model invokes the subagent at\\nruntime, the agent calls `avp.spawn_subagent` with the same ref to\\nobtain a child `run_id`. The subagent run carries its own complete\\ntrajectory; the parent's `subagent_invoked.data[\\\"avp.subagent.run_id\\\"]`\\nreferences it.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\","]
#[doc = "    \"ref\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9_-]+$\""]
#[doc = "    },"]
#[doc = "    \"ref\": {"]
#[doc = "      \"$ref\": \"#/$defs/JsonValue\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SubagentRef {
    pub id: Id,
    #[serde(rename = "ref")]
    pub ref_: JsonValue,
}
#[doc = "Identifies the supervisor that is requesting the run.\n\nCarried inside `Commission.supervisor` and stamped onto the\n`run_requested` event the agent emits as the first event of the\ntrajectory (with `source: avp://supervisor`). Lets a trajectory\nconsumer attribute the run to the originating supervisor without an\nout-of-band lookup.\n\n`name` SHOULD be a stable identifier for the supervisor implementation\nor instance (e.g. `\"simple-supervisor-example\"`, `\"acme.scheduler\"`).\n`version` is optional but recommended — it travels with the trajectory\nand lets auditors correlate a run with the exact supervisor build\nthat requested it."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SupervisorPreamble\","]
#[doc = "  \"description\": \"Identifies the supervisor that is requesting the run.\\n\\nCarried inside `Commission.supervisor` and stamped onto the\\n`run_requested` event the agent emits as the first event of the\\ntrajectory (with `source: avp://supervisor`). Lets a trajectory\\nconsumer attribute the run to the originating supervisor without an\\nout-of-band lookup.\\n\\n`name` SHOULD be a stable identifier for the supervisor implementation\\nor instance (e.g. `\\\"simple-supervisor-example\\\"`, `\\\"acme.scheduler\\\"`).\\n`version` is optional but recommended — it travels with the trajectory\\nand lets auditors correlate a run with the exact supervisor build\\nthat requested it.\","]
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
