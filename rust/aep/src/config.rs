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
#[doc = "`AepSource`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Source\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AepSource(::std::string::String);
impl ::std::ops::Deref for AepSource {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AepSource> for ::std::string::String {
    fn from(value: AepSource) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AepSource {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AepSource {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AepSource {
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
#[doc = "Supervisor → runner setup message. Declares the agent's complete environment (boundary, tools, mcp_servers, skills, verifiers, prompts). Sent once at startup. The supervisor MUST NOT modify the environment mid-run."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"$id\": \"https://aep.dev/schema/v0.1/config.schema.json\","]
#[doc = "  \"title\": \"AEP v0.1 Config\","]
#[doc = "  \"description\": \"Supervisor → runner setup message. Declares the agent's complete environment (boundary, tools, mcp_servers, skills, verifiers, prompts). Sent once at startup. The supervisor MUST NOT modify the environment mid-run.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"run_id\","]
#[doc = "    \"schema_version\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"allowed_tools\": {"]
#[doc = "      \"title\": \"Allowed Tools\","]
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
#[doc = "    \"boundary\": {"]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/Boundary\""]
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
#[doc = "            \"$ref\": \"#/$defs/McpServer\""]
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
#[doc = "    \"subagents\": {"]
#[doc = "      \"title\": \"Subagents\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/Subagent\""]
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
#[doc = "    },"]
#[doc = "    \"tools\": {"]
#[doc = "      \"title\": \"Tools\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/Tool\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"verifiers\": {"]
#[doc = "      \"title\": \"Verifiers\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/Verifier\""]
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
pub struct AepV01Config {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub allowed_tools: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub boundary: ::std::option::Option<Boundary>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub mcp_servers: ::std::option::Option<::std::vec::Vec<McpServer>>,
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
    pub subagents: ::std::option::Option<::std::vec::Vec<Subagent>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub system_prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tags: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub thread_id: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tools: ::std::option::Option<::std::vec::Vec<Tool>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub verifiers: ::std::option::Option<::std::vec::Vec<Verifier>>,
}
#[doc = "The body of `{approval: {...}}` — the prompt and any future\nknobs that describe what the supervisor is being asked to approve."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"_ApprovalSpec\","]
#[doc = "  \"description\": \"The body of `{approval: {...}}` — the prompt and any future\\nknobs that describe what the supervisor is being asked to approve.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"properties\": {"]
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
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ApprovalSpec {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub prompt: ::std::option::Option<::std::string::String>,
}
impl ::std::default::Default for ApprovalSpec {
    fn default() -> Self {
        Self {
            prompt: Default::default(),
        }
    }
}
#[doc = "Hard limits the agent enforces. Strict-greater per SPEC §9.2.\n\nCost / tokens / duration are CONSUMPTION boundaries — checked after\neach turn and tool, and may overshoot a max by one final event because\nthe cost/token spend of the next call can't be projected pre-call.\nStep is a PROJECTION boundary — checked before starting the next turn,\nso `max_steps: N` runs EXACTLY N turns."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Boundary\","]
#[doc = "  \"description\": \"Hard limits the agent enforces. Strict-greater per SPEC §9.2.\\n\\nCost / tokens / duration are CONSUMPTION boundaries — checked after\\neach turn and tool, and may overshoot a max by one final event because\\nthe cost/token spend of the next call can't be projected pre-call.\\nStep is a PROJECTION boundary — checked before starting the next turn,\\nso `max_steps: N` runs EXACTLY N turns.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"properties\": {"]
#[doc = "    \"max_cost_usd\": {"]
#[doc = "      \"title\": \"Max Cost Usd\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"number\","]
#[doc = "          \"exclusiveMinimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"max_duration_seconds\": {"]
#[doc = "      \"title\": \"Max Duration Seconds\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"number\","]
#[doc = "          \"exclusiveMinimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"max_steps\": {"]
#[doc = "      \"title\": \"Max Steps\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\","]
#[doc = "          \"exclusiveMinimum\": 0.0"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"max_tokens\": {"]
#[doc = "      \"title\": \"Max Tokens\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\","]
#[doc = "          \"exclusiveMinimum\": 0.0"]
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
pub struct Boundary {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub max_cost_usd: ::std::option::Option<f64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub max_duration_seconds: ::std::option::Option<f64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub max_steps: ::std::option::Option<::std::num::NonZeroU64>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub max_tokens: ::std::option::Option<::std::num::NonZeroU64>,
}
impl ::std::default::Default for Boundary {
    fn default() -> Self {
        Self {
            max_cost_usd: Default::default(),
            max_duration_seconds: Default::default(),
            max_steps: Default::default(),
            max_tokens: Default::default(),
        }
    }
}
#[doc = "`Description`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Description\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct Description(::std::string::String);
impl ::std::ops::Deref for Description {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<Description> for ::std::string::String {
    fn from(value: Description) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for Description {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for Description {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for Description {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Description {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for Description {
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
#[doc = "Auth for an MCP server reachable via HTTP."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpHttpAuth\","]
#[doc = "  \"description\": \"Auth for an MCP server reachable via HTTP.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"token_env\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"token_env\": {"]
#[doc = "      \"title\": \"Token Env\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"type\": {"]
#[doc = "      \"title\": \"Type\","]
#[doc = "      \"default\": \"bearer\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"bearer\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct McpHttpAuth {
    pub token_env: TokenEnv,
    #[serde(rename = "type", default = "defaults::mcp_http_auth_type")]
    pub type_: ::std::string::String,
}
#[doc = "External MCP server endpoint. The runner connects, runs initialize +\ntools/list, and merges returned tools into the effective surface."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"McpServer\","]
#[doc = "  \"description\": \"External MCP server endpoint. The runner connects, runs initialize +\\ntools/list, and merges returned tools into the effective surface.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\","]
#[doc = "    \"transport\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"_meta\": {"]
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
#[doc = "    \"auth\": {"]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/McpHttpAuth\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"command\": {"]
#[doc = "      \"title\": \"Command\","]
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
#[doc = "    \"init_timeout_ms\": {"]
#[doc = "      \"title\": \"Init Timeout Ms\","]
#[doc = "      \"default\": 30000,"]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"exclusiveMinimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"transport\": {"]
#[doc = "      \"title\": \"Transport\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"enum\": ["]
#[doc = "        \"http\","]
#[doc = "        \"stdio\""]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"url\": {"]
#[doc = "      \"title\": \"Url\","]
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
pub struct McpServer {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub args: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub auth: ::std::option::Option<McpHttpAuth>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub command: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub env: ::std::option::Option<
        ::std::collections::HashMap<::std::string::String, ::std::string::String>,
    >,
    pub id: Id,
    #[serde(default = "defaults::default_nzu64::<::std::num::NonZeroU64, 30000>")]
    pub init_timeout_ms: ::std::num::NonZeroU64,
    #[serde(
        rename = "_meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub meta: ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    pub transport: Transport,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub url: ::std::option::Option<::std::string::String>,
}
#[doc = "`Name`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Name\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"maxLength\": 64,"]
#[doc = "  \"minLength\": 1,"]
#[doc = "  \"pattern\": \"^[a-z0-9]+(-[a-z0-9]+)*$\""]
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
        if value.chars().count() > 64usize {
            return Err("longer than 64 characters".into());
        }
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| {
                ::regress::Regex::new("^[a-z0-9]+(-[a-z0-9]+)*$").unwrap()
            });
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[a-z0-9]+(-[a-z0-9]+)*$\"".into());
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
#[doc = "`OnFailure`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"OnFailure\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"halt\","]
#[doc = "    \"inject_correction\","]
#[doc = "    \"continue\""]
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
pub enum OnFailure {
    #[serde(rename = "halt")]
    Halt,
    #[serde(rename = "inject_correction")]
    InjectCorrection,
    #[serde(rename = "continue")]
    Continue,
}
impl ::std::fmt::Display for OnFailure {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Halt => f.write_str("halt"),
            Self::InjectCorrection => f.write_str("inject_correction"),
            Self::Continue => f.write_str("continue"),
        }
    }
}
impl ::std::str::FromStr for OnFailure {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "halt" => Ok(Self::Halt),
            "inject_correction" => Ok(Self::InjectCorrection),
            "continue" => Ok(Self::Continue),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for OnFailure {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for OnFailure {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for OnFailure {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
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
#[doc = "Reference to a SKILL.md following the agentskills.io specification.\n\n`name` MUST follow agentskills.io rules (1-64 chars, lowercase a-z digits\nhyphens, no leading/trailing hyphen, no consecutive hyphens). The\n`aep_source` and `aep_config` fields are AEP extensions; agentskills.io\ndoesn't define a remote-load scheme."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Skill\","]
#[doc = "  \"description\": \"Reference to a SKILL.md following the agentskills.io specification.\\n\\n`name` MUST follow agentskills.io rules (1-64 chars, lowercase a-z digits\\nhyphens, no leading/trailing hyphen, no consecutive hyphens). The\\n`aep_source` and `aep_config` fields are AEP extensions; agentskills.io\\ndoesn't define a remote-load scheme.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.source\","]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.config\": {"]
#[doc = "      \"title\": \"Aep.Config\","]
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
#[doc = "    \"aep.source\": {"]
#[doc = "      \"title\": \"Aep.Source\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 64,"]
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9]+(-[a-z0-9]+)*$\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Skill {
    #[serde(
        rename = "aep.config",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_config:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(rename = "aep.source")]
    pub aep_source: AepSource,
    pub name: Name,
}
#[doc = "`Source`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Source\","]
#[doc = "  \"anyOf\": ["]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/VerifierSourceShell\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/VerifierSourceApproval\""]
#[doc = "    }"]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(untagged)]
pub enum Source {
    Shell(VerifierSourceShell),
    Approval(VerifierSourceApproval),
}
impl ::std::convert::From<VerifierSourceShell> for Source {
    fn from(value: VerifierSourceShell) -> Self {
        Self::Shell(value)
    }
}
impl ::std::convert::From<VerifierSourceApproval> for Source {
    fn from(value: VerifierSourceApproval) -> Self {
        Self::Approval(value)
    }
}
#[doc = "Declares a sub-agent the parent can delegate to.\n\nSits alongside `tools` and `skills` as a top-level Config primitive: the\nsupervisor declares the full set of subagents up front, the parent agent\ninvokes one by name at runtime. The model surface is MCP-shaped (`name`,\n`description`, `inputSchema`) so the model sees a subagent the same way\nit sees a tool. The wire surface is its own lifecycle —\n`subagent_invoked` / `subagent_returned` / `subagent_failed` — so\nnested turns and tool calls observe as their own span tree rather than\nflatten into a single tool call.\n\nA Subagent carries an environment slice that mirrors Config (its own\n`system_prompt`, `model`, `tools`, `skills`, `verifiers`, `boundary`,\n`output_schema`). The subagent runs in a fresh conversation —\n`inherit_tools=False` by default (matches Google ADK; safer than the\nClaude Agent SDK default of inheriting). Skills and prompt context are\nnever inherited."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Subagent\","]
#[doc = "  \"description\": \"Declares a sub-agent the parent can delegate to.\\n\\nSits alongside `tools` and `skills` as a top-level Config primitive: the\\nsupervisor declares the full set of subagents up front, the parent agent\\ninvokes one by name at runtime. The model surface is MCP-shaped (`name`,\\n`description`, `inputSchema`) so the model sees a subagent the same way\\nit sees a tool. The wire surface is its own lifecycle —\\n`subagent_invoked` / `subagent_returned` / `subagent_failed` — so\\nnested turns and tool calls observe as their own span tree rather than\\nflatten into a single tool call.\\n\\nA Subagent carries an environment slice that mirrors Config (its own\\n`system_prompt`, `model`, `tools`, `skills`, `verifiers`, `boundary`,\\n`output_schema`). The subagent runs in a fresh conversation —\\n`inherit_tools=False` by default (matches Google ADK; safer than the\\nClaude Agent SDK default of inheriting). Skills and prompt context are\\nnever inherited.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"description\","]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"allowed_tools\": {"]
#[doc = "      \"title\": \"Allowed Tools\","]
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
#[doc = "    \"boundary\": {"]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/Boundary\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"description\": {"]
#[doc = "      \"title\": \"Description\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"inherit_tools\": {"]
#[doc = "      \"title\": \"Inherit Tools\","]
#[doc = "      \"default\": false,"]
#[doc = "      \"type\": \"boolean\""]
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
#[doc = "    \"mcp_servers\": {"]
#[doc = "      \"title\": \"Mcp Servers\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/McpServer\""]
#[doc = "          }"]
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
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"maxLength\": 64,"]
#[doc = "      \"minLength\": 1,"]
#[doc = "      \"pattern\": \"^[a-z0-9_-]+$\""]
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
#[doc = "    \"subagents\": {"]
#[doc = "      \"title\": \"Subagents\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/Subagent\""]
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
#[doc = "            \"$ref\": \"#/$defs/Tool\""]
#[doc = "          }"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"verifiers\": {"]
#[doc = "      \"title\": \"Verifiers\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"array\","]
#[doc = "          \"items\": {"]
#[doc = "            \"$ref\": \"#/$defs/Verifier\""]
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
pub struct Subagent {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub allowed_tools: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub boundary: ::std::option::Option<Boundary>,
    pub description: Description,
    #[serde(default)]
    pub inherit_tools: bool,
    #[serde(
        rename = "inputSchema",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub input_schema:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub mcp_servers: ::std::option::Option<::std::vec::Vec<McpServer>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub model: ::std::option::Option<::std::string::String>,
    pub name: Name,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub output_schema:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub skills: ::std::option::Option<::std::vec::Vec<Skill>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subagents: ::std::option::Option<::std::vec::Vec<Subagent>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub system_prompt: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub tools: ::std::option::Option<::std::vec::Vec<Tool>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub verifiers: ::std::option::Option<::std::vec::Vec<Verifier>>,
}
#[doc = "`TokenEnv`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Token Env\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct TokenEnv(::std::string::String);
impl ::std::ops::Deref for TokenEnv {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<TokenEnv> for ::std::string::String {
    fn from(value: TokenEnv) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for TokenEnv {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for TokenEnv {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for TokenEnv {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for TokenEnv {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for TokenEnv {
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
#[doc = "MCP-shaped tool descriptor. Per the MCP 2025-11-25 spec.\n\n`inputSchema` and `outputSchema` are camelCase per MCP. The optional\n`_meta.aep.timeout_ms` is AEP's extension (MCP defines `_meta` as the\nextension slot)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Tool\","]
#[doc = "  \"description\": \"MCP-shaped tool descriptor. Per the MCP 2025-11-25 spec.\\n\\n`inputSchema` and `outputSchema` are camelCase per MCP. The optional\\n`_meta.aep.timeout_ms` is AEP's extension (MCP defines `_meta` as the\\nextension slot).\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"inputSchema\","]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"_meta\": {"]
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
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    },"]
#[doc = "    \"name\": {"]
#[doc = "      \"title\": \"Name\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"outputSchema\": {"]
#[doc = "      \"title\": \"Outputschema\","]
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
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Tool {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub description: ::std::option::Option<::std::string::String>,
    #[serde(rename = "inputSchema")]
    pub input_schema: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    #[serde(
        rename = "_meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub meta: ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    pub name: Name,
    #[serde(
        rename = "outputSchema",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub output_schema:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub title: ::std::option::Option<::std::string::String>,
}
#[doc = "`Transport`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Transport\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"http\","]
#[doc = "    \"stdio\""]
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
pub enum Transport {
    #[serde(rename = "http")]
    Http,
    #[serde(rename = "stdio")]
    Stdio,
}
impl ::std::fmt::Display for Transport {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Http => f.write_str("http"),
            Self::Stdio => f.write_str("stdio"),
        }
    }
}
impl ::std::str::FromStr for Transport {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "http" => Ok(Self::Http),
            "stdio" => Ok(Self::Stdio),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for Transport {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for Transport {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Transport {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "Declarative check at a trigger point. AEP-specific (no upstream).\n\nTwo reaction polarities:\n  - `on_failure` (default `continue`): action when the check FAILS.\n    The common case — invariants that fail trigger correction or halt.\n  - `on_success` (default `continue`): action when the check PASSES.\n    Use `on_success: halt` for declarative convergence — \"stop when\n    this condition is met\". Halt-on-success terminates with\n    `reason=converged`; halt-on-failure terminates with\n    `reason=verifier_failed`.\n\nSources:\n  - `{shell: \"...\"}` — deterministic subprocess; exit 0 = pass.\n  - `{approval: {prompt?: \"...\"}}` — pings the supervisor for a\n    human or policy decision via the `approval_requested` /\n    `approval_resolved` RPC pair. Approved = pass; denied or timed\n    out = fail. Use with `pre_tool:<name>` triggers for human-in-\n    the-loop gates on destructive actions.\n\nA check can set both: e.g. `on_success: halt` + `on_failure: continue`\nmeans \"halt when this passes, otherwise keep going\". Setting both to\n`halt` is allowed but unusual (halts no matter what — useful for\nforced checkpoints)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Verifier\","]
#[doc = "  \"description\": \"Declarative check at a trigger point. AEP-specific (no upstream).\\n\\nTwo reaction polarities:\\n  - `on_failure` (default `continue`): action when the check FAILS.\\n    The common case — invariants that fail trigger correction or halt.\\n  - `on_success` (default `continue`): action when the check PASSES.\\n    Use `on_success: halt` for declarative convergence — \\\"stop when\\n    this condition is met\\\". Halt-on-success terminates with\\n    `reason=converged`; halt-on-failure terminates with\\n    `reason=verifier_failed`.\\n\\nSources:\\n  - `{shell: \\\"...\\\"}` — deterministic subprocess; exit 0 = pass.\\n  - `{approval: {prompt?: \\\"...\\\"}}` — pings the supervisor for a\\n    human or policy decision via the `approval_requested` /\\n    `approval_resolved` RPC pair. Approved = pass; denied or timed\\n    out = fail. Use with `pre_tool:<name>` triggers for human-in-\\n    the-loop gates on destructive actions.\\n\\nA check can set both: e.g. `on_success: halt` + `on_failure: continue`\\nmeans \\\"halt when this passes, otherwise keep going\\\". Setting both to\\n`halt` is allowed but unusual (halts no matter what — useful for\\nforced checkpoints).\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"name\","]
#[doc = "    \"source\","]
#[doc = "    \"trigger\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"correction_message\": {"]
#[doc = "      \"title\": \"Correction Message\","]
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
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"on_failure\": {"]
#[doc = "      \"default\": \"continue\","]
#[doc = "      \"$ref\": \"#/$defs/OnFailure\""]
#[doc = "    },"]
#[doc = "    \"on_success\": {"]
#[doc = "      \"default\": \"continue\","]
#[doc = "      \"$ref\": \"#/$defs/OnFailure\""]
#[doc = "    },"]
#[doc = "    \"source\": {"]
#[doc = "      \"title\": \"Source\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/VerifierSourceShell\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/VerifierSourceApproval\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"timeout_ms\": {"]
#[doc = "      \"title\": \"Timeout Ms\","]
#[doc = "      \"default\": 30000,"]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"exclusiveMinimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"trigger\": {"]
#[doc = "      \"title\": \"Trigger\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Verifier {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub correction_message: ::std::option::Option<::std::string::String>,
    pub name: Name,
    #[serde(default = "defaults::verifier_on_failure")]
    pub on_failure: OnFailure,
    #[serde(default = "defaults::verifier_on_success")]
    pub on_success: OnFailure,
    pub source: Source,
    #[serde(default = "defaults::default_nzu64::<::std::num::NonZeroU64, 30000>")]
    pub timeout_ms: ::std::num::NonZeroU64,
    pub trigger: ::std::string::String,
}
#[doc = "Approval-source verifier: pass/fail comes from the supervisor's\nresponse to an `aep.approval_requested` RPC. Used at gate triggers\n(typically `pre_tool:<name>`) where a human or policy decides\nwhether the agent proceeds. Approved → pass; denied or timed-out →\nfail. Distinct from shell sources because the decision is non-\ndeterministic and originates outside the runner."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"VerifierSourceApproval\","]
#[doc = "  \"description\": \"Approval-source verifier: pass/fail comes from the supervisor's\\nresponse to an `aep.approval_requested` RPC. Used at gate triggers\\n(typically `pre_tool:<name>`) where a human or policy decides\\nwhether the agent proceeds. Approved → pass; denied or timed-out →\\nfail. Distinct from shell sources because the decision is non-\\ndeterministic and originates outside the runner.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"approval\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"approval\": {"]
#[doc = "      \"$ref\": \"#/$defs/_ApprovalSpec\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct VerifierSourceApproval {
    pub approval: ApprovalSpec,
}
#[doc = "Shell-source verifier: pass/fail comes from the exit code of a\nsubprocess. Deterministic; runs in-process on the runner's host."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"VerifierSourceShell\","]
#[doc = "  \"description\": \"Shell-source verifier: pass/fail comes from the exit code of a\\nsubprocess. Deterministic; runs in-process on the runner's host.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"shell\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"shell\": {"]
#[doc = "      \"title\": \"Shell\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct VerifierSourceShell {
    pub shell: ::std::string::String,
}
#[doc = r" Generation of default values for serde."]
pub mod defaults {
    pub(super) fn default_nzu64<T, const V: u64>() -> T
    where
        T: ::std::convert::TryFrom<::std::num::NonZeroU64>,
        <T as ::std::convert::TryFrom<::std::num::NonZeroU64>>::Error: ::std::fmt::Debug,
    {
        T::try_from(::std::num::NonZeroU64::try_from(V).unwrap()).unwrap()
    }
    pub(super) fn mcp_http_auth_type() -> ::std::string::String {
        "bearer".to_string()
    }
    pub(super) fn verifier_on_failure() -> super::OnFailure {
        super::OnFailure::Continue
    }
    pub(super) fn verifier_on_success() -> super::OnFailure {
        super::OnFailure::Continue
    }
}
