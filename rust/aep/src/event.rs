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
#[doc = "`AepApprovalId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Approval.Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AepApprovalId(::std::string::String);
impl ::std::ops::Deref for AepApprovalId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AepApprovalId> for ::std::string::String {
    fn from(value: AepApprovalId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AepApprovalId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AepApprovalId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepApprovalId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepApprovalId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AepApprovalId {
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
#[doc = "`AepMcpDisconnectReason`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Mcp.Disconnect Reason\","]
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
pub enum AepMcpDisconnectReason {
    #[serde(rename = "clean")]
    Clean,
    #[serde(rename = "error")]
    Error,
}
impl ::std::fmt::Display for AepMcpDisconnectReason {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Clean => f.write_str("clean"),
            Self::Error => f.write_str("error"),
        }
    }
}
impl ::std::str::FromStr for AepMcpDisconnectReason {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "clean" => Ok(Self::Clean),
            "error" => Ok(Self::Error),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for AepMcpDisconnectReason {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepMcpDisconnectReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepMcpDisconnectReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`AepMcpServerId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Mcp.Server Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AepMcpServerId(::std::string::String);
impl ::std::ops::Deref for AepMcpServerId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AepMcpServerId> for ::std::string::String {
    fn from(value: AepMcpServerId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AepMcpServerId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AepMcpServerId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepMcpServerId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepMcpServerId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AepMcpServerId {
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
#[doc = "`AepRefusalReason`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Refusal.Reason\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AepRefusalReason(::std::string::String);
impl ::std::ops::Deref for AepRefusalReason {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AepRefusalReason> for ::std::string::String {
    fn from(value: AepRefusalReason) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AepRefusalReason {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AepRefusalReason {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepRefusalReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepRefusalReason {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AepRefusalReason {
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
#[doc = "`AepRequestId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Request Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AepRequestId(::std::string::String);
impl ::std::ops::Deref for AepRequestId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AepRequestId> for ::std::string::String {
    fn from(value: AepRequestId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AepRequestId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AepRequestId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepRequestId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepRequestId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AepRequestId {
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
#[doc = "`AepSubagentInvocationId`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Subagent.Invocation Id\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AepSubagentInvocationId(::std::string::String);
impl ::std::ops::Deref for AepSubagentInvocationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AepSubagentInvocationId> for ::std::string::String {
    fn from(value: AepSubagentInvocationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AepSubagentInvocationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AepSubagentInvocationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepSubagentInvocationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepSubagentInvocationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AepSubagentInvocationId {
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
#[doc = "`AepToolDispatchTarget`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Tool.Dispatch Target\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"supervisor_rpc\","]
#[doc = "    \"mcp_server\""]
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
pub enum AepToolDispatchTarget {
    #[serde(rename = "supervisor_rpc")]
    SupervisorRpc,
    #[serde(rename = "mcp_server")]
    McpServer,
}
impl ::std::fmt::Display for AepToolDispatchTarget {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::SupervisorRpc => f.write_str("supervisor_rpc"),
            Self::McpServer => f.write_str("mcp_server"),
        }
    }
}
impl ::std::str::FromStr for AepToolDispatchTarget {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "supervisor_rpc" => Ok(Self::SupervisorRpc),
            "mcp_server" => Ok(Self::McpServer),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for AepToolDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepToolDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepToolDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "Runner → supervisor event. Each event is a CloudEvent 1.0 envelope carrying a typed `data` payload. The `type` field is the discriminator (reverse-DNS, `aep.*` namespace). Attribute names inside `data` follow OpenTelemetry GenAI semantic conventions and OTel span identification (`trace_id`, `span_id`, `parent_span_id`); AEP-specific attributes are namespaced `aep.*`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"$id\": \"https://aep.dev/schema/v0.1/event.schema.json\","]
#[doc = "  \"title\": \"AEP v0.1 Event\","]
#[doc = "  \"description\": \"Runner → supervisor event. Each event is a CloudEvent 1.0 envelope carrying a typed `data` payload. The `type` field is the discriminator (reverse-DNS, `aep.*` namespace). Attribute names inside `data` follow OpenTelemetry GenAI semantic conventions and OTel span identification (`trace_id`, `span_id`, `parent_span_id`); AEP-specific attributes are namespaced `aep.*`.\","]
#[doc = "  \"oneOf\": ["]
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
#[doc = "      \"$ref\": \"#/$defs/SkillExecutedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ErrorOccurredEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolExecRequestEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolExecResolvedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolExecTimedOutEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ApprovalRequestedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ApprovalResolvedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/VerifierEvaluatedEvent\""]
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
#[doc = "      \"aep.agent_started\": \"#/$defs/AgentStartedEvent\","]
#[doc = "      \"aep.agent_stopped\": \"#/$defs/AgentStoppedEvent\","]
#[doc = "      \"aep.approval_requested\": \"#/$defs/ApprovalRequestedEvent\","]
#[doc = "      \"aep.approval_resolved\": \"#/$defs/ApprovalResolvedEvent\","]
#[doc = "      \"aep.cost_recorded\": \"#/$defs/CostRecordedEvent\","]
#[doc = "      \"aep.error_occurred\": \"#/$defs/ErrorOccurredEvent\","]
#[doc = "      \"aep.mcp_server_connected\": \"#/$defs/McpServerConnectedEvent\","]
#[doc = "      \"aep.mcp_server_disconnected\": \"#/$defs/McpServerDisconnectedEvent\","]
#[doc = "      \"aep.model_turn_ended\": \"#/$defs/ModelTurnEndedEvent\","]
#[doc = "      \"aep.model_turn_started\": \"#/$defs/ModelTurnStartedEvent\","]
#[doc = "      \"aep.reasoning_emitted\": \"#/$defs/ReasoningEmittedEvent\","]
#[doc = "      \"aep.refusal_recorded\": \"#/$defs/RefusalRecordedEvent\","]
#[doc = "      \"aep.skill_executed\": \"#/$defs/SkillExecutedEvent\","]
#[doc = "      \"aep.skill_loaded\": \"#/$defs/SkillLoadedEvent\","]
#[doc = "      \"aep.subagent_failed\": \"#/$defs/SubagentFailedEvent\","]
#[doc = "      \"aep.subagent_invoked\": \"#/$defs/SubagentInvokedEvent\","]
#[doc = "      \"aep.subagent_returned\": \"#/$defs/SubagentReturnedEvent\","]
#[doc = "      \"aep.text_emitted\": \"#/$defs/TextEmittedEvent\","]
#[doc = "      \"aep.tool_exec_request\": \"#/$defs/ToolExecRequestEvent\","]
#[doc = "      \"aep.tool_exec_resolved\": \"#/$defs/ToolExecResolvedEvent\","]
#[doc = "      \"aep.tool_exec_timed_out\": \"#/$defs/ToolExecTimedOutEvent\","]
#[doc = "      \"aep.tool_failed\": \"#/$defs/ToolFailedEvent\","]
#[doc = "      \"aep.tool_invoked\": \"#/$defs/ToolInvokedEvent\","]
#[doc = "      \"aep.tool_returned\": \"#/$defs/ToolReturnedEvent\","]
#[doc = "      \"aep.verifier_evaluated\": \"#/$defs/VerifierEvaluatedEvent\""]
#[doc = "    },"]
#[doc = "    \"propertyName\": \"type\""]
#[doc = "  }"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(untagged)]
pub enum AepV01Event {
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
    SkillExecutedEvent(SkillExecutedEvent),
    ErrorOccurredEvent(ErrorOccurredEvent),
    ToolExecRequestEvent(ToolExecRequestEvent),
    ToolExecResolvedEvent(ToolExecResolvedEvent),
    ToolExecTimedOutEvent(ToolExecTimedOutEvent),
    ApprovalRequestedEvent(ApprovalRequestedEvent),
    ApprovalResolvedEvent(ApprovalResolvedEvent),
    VerifierEvaluatedEvent(VerifierEvaluatedEvent),
    McpServerConnectedEvent(McpServerConnectedEvent),
    McpServerDisconnectedEvent(McpServerDisconnectedEvent),
}
impl ::std::convert::From<AgentStartedEvent> for AepV01Event {
    fn from(value: AgentStartedEvent) -> Self {
        Self::AgentStartedEvent(value)
    }
}
impl ::std::convert::From<AgentStoppedEvent> for AepV01Event {
    fn from(value: AgentStoppedEvent) -> Self {
        Self::AgentStoppedEvent(value)
    }
}
impl ::std::convert::From<ModelTurnStartedEvent> for AepV01Event {
    fn from(value: ModelTurnStartedEvent) -> Self {
        Self::ModelTurnStartedEvent(value)
    }
}
impl ::std::convert::From<ModelTurnEndedEvent> for AepV01Event {
    fn from(value: ModelTurnEndedEvent) -> Self {
        Self::ModelTurnEndedEvent(value)
    }
}
impl ::std::convert::From<ToolInvokedEvent> for AepV01Event {
    fn from(value: ToolInvokedEvent) -> Self {
        Self::ToolInvokedEvent(value)
    }
}
impl ::std::convert::From<ToolReturnedEvent> for AepV01Event {
    fn from(value: ToolReturnedEvent) -> Self {
        Self::ToolReturnedEvent(value)
    }
}
impl ::std::convert::From<ToolFailedEvent> for AepV01Event {
    fn from(value: ToolFailedEvent) -> Self {
        Self::ToolFailedEvent(value)
    }
}
impl ::std::convert::From<SubagentInvokedEvent> for AepV01Event {
    fn from(value: SubagentInvokedEvent) -> Self {
        Self::SubagentInvokedEvent(value)
    }
}
impl ::std::convert::From<SubagentReturnedEvent> for AepV01Event {
    fn from(value: SubagentReturnedEvent) -> Self {
        Self::SubagentReturnedEvent(value)
    }
}
impl ::std::convert::From<SubagentFailedEvent> for AepV01Event {
    fn from(value: SubagentFailedEvent) -> Self {
        Self::SubagentFailedEvent(value)
    }
}
impl ::std::convert::From<TextEmittedEvent> for AepV01Event {
    fn from(value: TextEmittedEvent) -> Self {
        Self::TextEmittedEvent(value)
    }
}
impl ::std::convert::From<ReasoningEmittedEvent> for AepV01Event {
    fn from(value: ReasoningEmittedEvent) -> Self {
        Self::ReasoningEmittedEvent(value)
    }
}
impl ::std::convert::From<RefusalRecordedEvent> for AepV01Event {
    fn from(value: RefusalRecordedEvent) -> Self {
        Self::RefusalRecordedEvent(value)
    }
}
impl ::std::convert::From<CostRecordedEvent> for AepV01Event {
    fn from(value: CostRecordedEvent) -> Self {
        Self::CostRecordedEvent(value)
    }
}
impl ::std::convert::From<SkillLoadedEvent> for AepV01Event {
    fn from(value: SkillLoadedEvent) -> Self {
        Self::SkillLoadedEvent(value)
    }
}
impl ::std::convert::From<SkillExecutedEvent> for AepV01Event {
    fn from(value: SkillExecutedEvent) -> Self {
        Self::SkillExecutedEvent(value)
    }
}
impl ::std::convert::From<ErrorOccurredEvent> for AepV01Event {
    fn from(value: ErrorOccurredEvent) -> Self {
        Self::ErrorOccurredEvent(value)
    }
}
impl ::std::convert::From<ToolExecRequestEvent> for AepV01Event {
    fn from(value: ToolExecRequestEvent) -> Self {
        Self::ToolExecRequestEvent(value)
    }
}
impl ::std::convert::From<ToolExecResolvedEvent> for AepV01Event {
    fn from(value: ToolExecResolvedEvent) -> Self {
        Self::ToolExecResolvedEvent(value)
    }
}
impl ::std::convert::From<ToolExecTimedOutEvent> for AepV01Event {
    fn from(value: ToolExecTimedOutEvent) -> Self {
        Self::ToolExecTimedOutEvent(value)
    }
}
impl ::std::convert::From<ApprovalRequestedEvent> for AepV01Event {
    fn from(value: ApprovalRequestedEvent) -> Self {
        Self::ApprovalRequestedEvent(value)
    }
}
impl ::std::convert::From<ApprovalResolvedEvent> for AepV01Event {
    fn from(value: ApprovalResolvedEvent) -> Self {
        Self::ApprovalResolvedEvent(value)
    }
}
impl ::std::convert::From<VerifierEvaluatedEvent> for AepV01Event {
    fn from(value: VerifierEvaluatedEvent) -> Self {
        Self::VerifierEvaluatedEvent(value)
    }
}
impl ::std::convert::From<McpServerConnectedEvent> for AepV01Event {
    fn from(value: McpServerConnectedEvent) -> Self {
        Self::McpServerConnectedEvent(value)
    }
}
impl ::std::convert::From<McpServerDisconnectedEvent> for AepV01Event {
    fn from(value: McpServerDisconnectedEvent) -> Self {
        Self::McpServerDisconnectedEvent(value)
    }
}
#[doc = "`AepVerifierName`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Aep.Verifier.Name\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct AepVerifierName(::std::string::String);
impl ::std::ops::Deref for AepVerifierName {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AepVerifierName> for ::std::string::String {
    fn from(value: AepVerifierName) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AepVerifierName {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AepVerifierName {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AepVerifierName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AepVerifierName {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AepVerifierName {
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
#[doc = "Payload of aep.agent_started events."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"AgentStartedData\","]
#[doc = "  \"description\": \"Payload of aep.agent_started events.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.meta\": {"]
#[doc = "      \"title\": \"Aep.Meta\","]
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
#[doc = "    \"aep.schema_version\": {"]
#[doc = "      \"title\": \"Aep.Schema Version\","]
#[doc = "      \"default\": \"0.1\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"0.1\""]
#[doc = "    },"]
#[doc = "    \"aep.session_id\": {"]
#[doc = "      \"title\": \"Aep.Session Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.tags\": {"]
#[doc = "      \"title\": \"Aep.Tags\","]
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
#[doc = "    \"aep.thread_id\": {"]
#[doc = "      \"title\": \"Aep.Thread Id\","]
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
#[doc = "            \"type\": \"string\""]
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
        rename = "aep.meta",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_meta:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(
        rename = "aep.schema_version",
        default = "defaults::agent_started_data_aep_schema_version"
    )]
    pub aep_schema_version: ::std::string::String,
    #[serde(
        rename = "aep.session_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_session_id: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "aep.tags",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_tags: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(
        rename = "aep.thread_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_thread_id: ::std::option::Option<::std::string::String>,
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
    pub skills: ::std::option::Option<::std::vec::Vec<::std::string::String>>,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.agent_started\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.agent_started\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<AgentStartedEventAepCorrelationId>,
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
#[doc = "`AgentStartedEventAepCorrelationId`"]
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
pub struct AgentStartedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for AgentStartedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentStartedEventAepCorrelationId> for ::std::string::String {
    fn from(value: AgentStartedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentStartedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentStartedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentStartedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentStartedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentStartedEventAepCorrelationId {
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
#[doc = "    \"aep.reason\","]
#[doc = "    \"aep.state\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.duration_ms\": {"]
#[doc = "      \"title\": \"Aep.Duration Ms\","]
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
#[doc = "    \"aep.output\": {"]
#[doc = "      \"title\": \"Aep.Output\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {},"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.reason\": {"]
#[doc = "      \"$ref\": \"#/$defs/StopReason\""]
#[doc = "    },"]
#[doc = "    \"aep.state\": {"]
#[doc = "      \"$ref\": \"#/$defs/RunStateSnapshot\""]
#[doc = "    },"]
#[doc = "    \"aep.total_cost_usd\": {"]
#[doc = "      \"title\": \"Aep.Total Cost Usd\","]
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
#[doc = "    \"aep.total_tokens\": {"]
#[doc = "      \"title\": \"Aep.Total Tokens\","]
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
#[doc = "    \"aep.total_turns\": {"]
#[doc = "      \"title\": \"Aep.Total Turns\","]
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
        rename = "aep.duration_ms",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_duration_ms: ::std::option::Option<u64>,
    #[serde(
        rename = "aep.output",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_output: ::std::option::Option<::serde_json::Value>,
    #[serde(rename = "aep.reason")]
    pub aep_reason: StopReason,
    #[serde(rename = "aep.state")]
    pub aep_state: RunStateSnapshot,
    #[serde(
        rename = "aep.total_cost_usd",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_total_cost_usd: ::std::option::Option<f64>,
    #[serde(
        rename = "aep.total_tokens",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_total_tokens: ::std::option::Option<u64>,
    #[serde(
        rename = "aep.total_turns",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_total_turns: ::std::option::Option<u64>,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.agent_stopped\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.agent_stopped\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<AgentStoppedEventAepCorrelationId>,
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
#[doc = "`AgentStoppedEventAepCorrelationId`"]
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
pub struct AgentStoppedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for AgentStoppedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<AgentStoppedEventAepCorrelationId> for ::std::string::String {
    fn from(value: AgentStoppedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for AgentStoppedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for AgentStoppedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for AgentStoppedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for AgentStoppedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for AgentStoppedEventAepCorrelationId {
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
#[doc = "Runner emits this when an approval-source verifier fires.\n\nCarries the context the supervisor needs to decide: which verifier\nrequested it, the optional prompt, and (for `pre_tool:<name>`\ngates) the tool call this approval covers. The supervisor MUST\nreply with an `approval_resolved` referencing the same\n`aep.approval.id` within `aep.timeout_ms`; missing replies are\ntreated as denials."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ApprovalRequestedData\","]
#[doc = "  \"description\": \"Runner emits this when an approval-source verifier fires.\\n\\nCarries the context the supervisor needs to decide: which verifier\\nrequested it, the optional prompt, and (for `pre_tool:<name>`\\ngates) the tool call this approval covers. The supervisor MUST\\nreply with an `approval_resolved` referencing the same\\n`aep.approval.id` within `aep.timeout_ms`; missing replies are\\ntreated as denials.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.approval.id\","]
#[doc = "    \"aep.timeout_ms\","]
#[doc = "    \"aep.verifier.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.approval.id\": {"]
#[doc = "      \"title\": \"Aep.Approval.Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"aep.approval.prompt\": {"]
#[doc = "      \"title\": \"Aep.Approval.Prompt\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.timeout_ms\": {"]
#[doc = "      \"title\": \"Aep.Timeout Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"exclusiveMinimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"aep.verifier.name\": {"]
#[doc = "      \"title\": \"Aep.Verifier.Name\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.call.arguments\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Call.Arguments\","]
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
#[doc = "    \"gen_ai.tool.call.id\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Call.Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Name\","]
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
pub struct ApprovalRequestedData {
    #[serde(rename = "aep.approval.id")]
    pub aep_approval_id: AepApprovalId,
    #[serde(
        rename = "aep.approval.prompt",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_approval_prompt: ::std::option::Option<::std::string::String>,
    #[serde(rename = "aep.timeout_ms")]
    pub aep_timeout_ms: ::std::num::NonZeroU64,
    #[serde(rename = "aep.verifier.name")]
    pub aep_verifier_name: AepVerifierName,
    #[serde(
        rename = "gen_ai.tool.call.arguments",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_tool_call_arguments:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(
        rename = "gen_ai.tool.call.id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_tool_call_id: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "gen_ai.tool.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_tool_name: ::std::option::Option<::std::string::String>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "Runner asks the supervisor to approve (or deny) something —\ntypically a tool dispatch gated by a pre_tool: + approval-source\nverifier. The supervisor MUST reply with `approval_resolved`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ApprovalRequestedEvent\","]
#[doc = "  \"description\": \"Runner asks the supervisor to approve (or deny) something —\\ntypically a tool dispatch gated by a pre_tool: + approval-source\\nverifier. The supervisor MUST reply with `approval_resolved`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"$ref\": \"#/$defs/ApprovalRequestedData\""]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.approval_requested\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.approval_requested\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ApprovalRequestedEvent {
    #[serde(
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ApprovalRequestedEventAepCorrelationId>,
    pub data: ApprovalRequestedData,
    #[serde(default = "defaults::approval_requested_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::approval_requested_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::approval_requested_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ApprovalRequestedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::approval_requested_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ApprovalRequestedEventAepCorrelationId`"]
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
pub struct ApprovalRequestedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ApprovalRequestedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ApprovalRequestedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ApprovalRequestedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ApprovalRequestedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ApprovalRequestedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ApprovalRequestedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ApprovalRequestedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ApprovalRequestedEventAepCorrelationId {
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
#[doc = "`ApprovalRequestedEventSubject`"]
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
pub struct ApprovalRequestedEventSubject(::std::string::String);
impl ::std::ops::Deref for ApprovalRequestedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ApprovalRequestedEventSubject> for ::std::string::String {
    fn from(value: ApprovalRequestedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ApprovalRequestedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ApprovalRequestedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ApprovalRequestedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ApprovalRequestedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ApprovalRequestedEventSubject {
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
#[doc = "Supervisor's decision for a pending `approval_requested`.\n\n`approved` is the load-bearing field. `reason` is free-text\nintended for the trajectory consumer (and for surfacing to the\nmodel on `pre_tool:` denials via the resulting `tool_failed.error`)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ApprovalResolvedData\","]
#[doc = "  \"description\": \"Supervisor's decision for a pending `approval_requested`.\\n\\n`approved` is the load-bearing field. `reason` is free-text\\nintended for the trajectory consumer (and for surfacing to the\\nmodel on `pre_tool:` denials via the resulting `tool_failed.error`).\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.approval.approved\","]
#[doc = "    \"aep.approval.id\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.approval.approved\": {"]
#[doc = "      \"title\": \"Aep.Approval.Approved\","]
#[doc = "      \"type\": \"boolean\""]
#[doc = "    },"]
#[doc = "    \"aep.approval.id\": {"]
#[doc = "      \"title\": \"Aep.Approval.Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"aep.approval.reason\": {"]
#[doc = "      \"title\": \"Aep.Approval.Reason\","]
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
pub struct ApprovalResolvedData {
    #[serde(rename = "aep.approval.approved")]
    pub aep_approval_approved: bool,
    #[serde(rename = "aep.approval.id")]
    pub aep_approval_id: AepApprovalId,
    #[serde(
        rename = "aep.approval.reason",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_approval_reason: ::std::option::Option<::std::string::String>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "Supervisor's decision recorded into the trajectory verbatim.\n`source` is `aep://supervisor`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ApprovalResolvedEvent\","]
#[doc = "  \"description\": \"Supervisor's decision recorded into the trajectory verbatim.\\n`source` is `aep://supervisor`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\","]
#[doc = "    \"source\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"$ref\": \"#/$defs/ApprovalResolvedData\""]
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
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
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
#[doc = "      \"default\": \"aep.approval_resolved\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.approval_resolved\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ApprovalResolvedEvent {
    #[serde(
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ApprovalResolvedEventAepCorrelationId>,
    pub data: ApprovalResolvedData,
    #[serde(default = "defaults::approval_resolved_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    pub source: Source,
    #[serde(default = "defaults::approval_resolved_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ApprovalResolvedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::approval_resolved_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ApprovalResolvedEventAepCorrelationId`"]
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
pub struct ApprovalResolvedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ApprovalResolvedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ApprovalResolvedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ApprovalResolvedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ApprovalResolvedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ApprovalResolvedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ApprovalResolvedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ApprovalResolvedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ApprovalResolvedEventAepCorrelationId {
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
#[doc = "`ApprovalResolvedEventSubject`"]
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
pub struct ApprovalResolvedEventSubject(::std::string::String);
impl ::std::ops::Deref for ApprovalResolvedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ApprovalResolvedEventSubject> for ::std::string::String {
    fn from(value: ApprovalResolvedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ApprovalResolvedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ApprovalResolvedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ApprovalResolvedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ApprovalResolvedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ApprovalResolvedEventSubject {
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
#[doc = "`CostRecordedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"CostRecordedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.state\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.cost.source\": {"]
#[doc = "      \"title\": \"Aep.Cost.Source\","]
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
#[doc = "    \"aep.state\": {"]
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
        rename = "aep.cost.source",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_cost_source: ::std::option::Option<CostRecordedDataAepCostSource>,
    #[serde(rename = "aep.state")]
    pub aep_state: RunStateSnapshot,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "`CostRecordedDataAepCostSource`"]
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
pub enum CostRecordedDataAepCostSource {
    #[serde(rename = "computed")]
    Computed,
    #[serde(rename = "reported")]
    Reported,
    #[serde(rename = "unknown")]
    Unknown,
}
impl ::std::fmt::Display for CostRecordedDataAepCostSource {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Computed => f.write_str("computed"),
            Self::Reported => f.write_str("reported"),
            Self::Unknown => f.write_str("unknown"),
        }
    }
}
impl ::std::str::FromStr for CostRecordedDataAepCostSource {
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
impl ::std::convert::TryFrom<&str> for CostRecordedDataAepCostSource {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for CostRecordedDataAepCostSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for CostRecordedDataAepCostSource {
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.cost_recorded\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.cost_recorded\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<CostRecordedEventAepCorrelationId>,
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
#[doc = "`CostRecordedEventAepCorrelationId`"]
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
pub struct CostRecordedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for CostRecordedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<CostRecordedEventAepCorrelationId> for ::std::string::String {
    fn from(value: CostRecordedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for CostRecordedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for CostRecordedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for CostRecordedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for CostRecordedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for CostRecordedEventAepCorrelationId {
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
#[doc = "    \"runner_crash\","]
#[doc = "    \"accounting_reset\","]
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
    #[serde(rename = "runner_crash")]
    RunnerCrash,
    #[serde(rename = "accounting_reset")]
    AccountingReset,
    #[serde(rename = "unknown")]
    Unknown,
}
impl ::std::fmt::Display for ErrorCode {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::RateLimit => f.write_str("rate_limit"),
            Self::ContextLimit => f.write_str("context_limit"),
            Self::AuthError => f.write_str("auth_error"),
            Self::RunnerCrash => f.write_str("runner_crash"),
            Self::AccountingReset => f.write_str("accounting_reset"),
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
            "runner_crash" => Ok(Self::RunnerCrash),
            "accounting_reset" => Ok(Self::AccountingReset),
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
#[doc = "    \"aep.error.code\","]
#[doc = "    \"aep.error.message\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.error.code\": {"]
#[doc = "      \"$ref\": \"#/$defs/ErrorCode\""]
#[doc = "    },"]
#[doc = "    \"aep.error.message\": {"]
#[doc = "      \"title\": \"Aep.Error.Message\","]
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
    #[serde(rename = "aep.error.code")]
    pub aep_error_code: ErrorCode,
    #[serde(rename = "aep.error.message")]
    pub aep_error_message: ::std::string::String,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.error_occurred\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.error_occurred\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ErrorOccurredEventAepCorrelationId>,
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
#[doc = "`ErrorOccurredEventAepCorrelationId`"]
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
pub struct ErrorOccurredEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ErrorOccurredEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ErrorOccurredEventAepCorrelationId> for ::std::string::String {
    fn from(value: ErrorOccurredEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ErrorOccurredEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ErrorOccurredEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ErrorOccurredEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ErrorOccurredEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ErrorOccurredEventAepCorrelationId {
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
#[doc = "`JsonRpcError`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"JsonRpcError\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"code\","]
#[doc = "    \"message\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"code\": {"]
#[doc = "      \"title\": \"Code\","]
#[doc = "      \"type\": \"integer\""]
#[doc = "    },"]
#[doc = "    \"data\": {"]
#[doc = "      \"title\": \"Data\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {},"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"message\": {"]
#[doc = "      \"title\": \"Message\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct JsonRpcError {
    pub code: i64,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub data: ::std::option::Option<::serde_json::Value>,
    pub message: ::std::string::String,
}
#[doc = "JSON-RPC 2.0 request payload — what tool_exec_request.data carries.\n\nPer MCP convention, `method` is `\"tools/call\"` and `params` is\n`{name, arguments}`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"JsonRpcRequestPayload\","]
#[doc = "  \"description\": \"JSON-RPC 2.0 request payload — what tool_exec_request.data carries.\\n\\nPer MCP convention, `method` is `\\\"tools/call\\\"` and `params` is\\n`{name, arguments}`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"id\","]
#[doc = "    \"method\","]
#[doc = "    \"params\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"jsonrpc\": {"]
#[doc = "      \"title\": \"Jsonrpc\","]
#[doc = "      \"default\": \"2.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"2.0\""]
#[doc = "    },"]
#[doc = "    \"method\": {"]
#[doc = "      \"title\": \"Method\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"params\": {"]
#[doc = "      \"title\": \"Params\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": true"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct JsonRpcRequestPayload {
    pub id: Id,
    #[serde(default = "defaults::json_rpc_request_payload_jsonrpc")]
    pub jsonrpc: ::std::string::String,
    pub method: ::std::string::String,
    pub params: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
}
#[doc = "JSON-RPC 2.0 response payload — what tool_exec_resolved.data carries.\n\nExactly one of `result` or `error` MUST be present per the JSON-RPC spec."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"JsonRpcResponsePayload\","]
#[doc = "  \"description\": \"JSON-RPC 2.0 response payload — what tool_exec_resolved.data carries.\\n\\nExactly one of `result` or `error` MUST be present per the JSON-RPC spec.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"properties\": {"]
#[doc = "    \"error\": {"]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/JsonRpcError\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"id\": {"]
#[doc = "      \"title\": \"Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"jsonrpc\": {"]
#[doc = "      \"title\": \"Jsonrpc\","]
#[doc = "      \"default\": \"2.0\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"2.0\""]
#[doc = "    },"]
#[doc = "    \"result\": {"]
#[doc = "      \"title\": \"Result\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {},"]
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
pub struct JsonRpcResponsePayload {
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub error: ::std::option::Option<JsonRpcError>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::json_rpc_response_payload_jsonrpc")]
    pub jsonrpc: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub result: ::std::option::Option<::serde_json::Value>,
}
impl ::std::default::Default for JsonRpcResponsePayload {
    fn default() -> Self {
        Self {
            error: Default::default(),
            id: Default::default(),
            jsonrpc: defaults::json_rpc_response_payload_jsonrpc(),
            result: Default::default(),
        }
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
#[doc = "    \"aep.mcp.protocol_version\","]
#[doc = "    \"aep.mcp.server_id\","]
#[doc = "    \"aep.mcp.tool_count\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.mcp.protocol_version\": {"]
#[doc = "      \"title\": \"Aep.Mcp.Protocol Version\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"aep.mcp.server_id\": {"]
#[doc = "      \"title\": \"Aep.Mcp.Server Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"aep.mcp.server_name\": {"]
#[doc = "      \"title\": \"Aep.Mcp.Server Name\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.mcp.server_version\": {"]
#[doc = "      \"title\": \"Aep.Mcp.Server Version\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.mcp.tool_count\": {"]
#[doc = "      \"title\": \"Aep.Mcp.Tool Count\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
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
    #[serde(rename = "aep.mcp.protocol_version")]
    pub aep_mcp_protocol_version: ::std::string::String,
    #[serde(rename = "aep.mcp.server_id")]
    pub aep_mcp_server_id: AepMcpServerId,
    #[serde(
        rename = "aep.mcp.server_name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_mcp_server_name: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "aep.mcp.server_version",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_mcp_server_version: ::std::option::Option<::std::string::String>,
    #[serde(rename = "aep.mcp.tool_count")]
    pub aep_mcp_tool_count: u64,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub trace_id: TraceId,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.mcp_server_connected\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.mcp_server_connected\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<McpServerConnectedEventAepCorrelationId>,
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
#[doc = "`McpServerConnectedEventAepCorrelationId`"]
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
pub struct McpServerConnectedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for McpServerConnectedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<McpServerConnectedEventAepCorrelationId> for ::std::string::String {
    fn from(value: McpServerConnectedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for McpServerConnectedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for McpServerConnectedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for McpServerConnectedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for McpServerConnectedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for McpServerConnectedEventAepCorrelationId {
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
#[doc = "    \"aep.mcp.disconnect_reason\","]
#[doc = "    \"aep.mcp.server_id\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.mcp.disconnect_message\": {"]
#[doc = "      \"title\": \"Aep.Mcp.Disconnect Message\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.mcp.disconnect_reason\": {"]
#[doc = "      \"title\": \"Aep.Mcp.Disconnect Reason\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"enum\": ["]
#[doc = "        \"clean\","]
#[doc = "        \"error\""]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.mcp.server_id\": {"]
#[doc = "      \"title\": \"Aep.Mcp.Server Id\","]
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
        rename = "aep.mcp.disconnect_message",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_mcp_disconnect_message: ::std::option::Option<::std::string::String>,
    #[serde(rename = "aep.mcp.disconnect_reason")]
    pub aep_mcp_disconnect_reason: AepMcpDisconnectReason,
    #[serde(rename = "aep.mcp.server_id")]
    pub aep_mcp_server_id: AepMcpServerId,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.mcp_server_disconnected\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.mcp_server_disconnected\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<McpServerDisconnectedEventAepCorrelationId>,
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
#[doc = "`McpServerDisconnectedEventAepCorrelationId`"]
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
pub struct McpServerDisconnectedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for McpServerDisconnectedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<McpServerDisconnectedEventAepCorrelationId> for ::std::string::String {
    fn from(value: McpServerDisconnectedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for McpServerDisconnectedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for McpServerDisconnectedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String>
    for McpServerDisconnectedEventAepCorrelationId
{
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for McpServerDisconnectedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for McpServerDisconnectedEventAepCorrelationId {
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
#[doc = "    \"aep.cost_usd\","]
#[doc = "    \"duration_ms\","]
#[doc = "    \"gen_ai.usage.input_tokens\","]
#[doc = "    \"gen_ai.usage.output_tokens\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.cost.source\": {"]
#[doc = "      \"title\": \"Aep.Cost.Source\","]
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
#[doc = "    \"aep.cost_usd\": {"]
#[doc = "      \"title\": \"Aep.Cost Usd\","]
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
        rename = "aep.cost.source",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_cost_source: ::std::option::Option<ModelTurnEndedDataAepCostSource>,
    #[serde(rename = "aep.cost_usd")]
    pub aep_cost_usd: f64,
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
#[doc = "`ModelTurnEndedDataAepCostSource`"]
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
pub enum ModelTurnEndedDataAepCostSource {
    #[serde(rename = "computed")]
    Computed,
    #[serde(rename = "reported")]
    Reported,
    #[serde(rename = "unknown")]
    Unknown,
}
impl ::std::fmt::Display for ModelTurnEndedDataAepCostSource {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Computed => f.write_str("computed"),
            Self::Reported => f.write_str("reported"),
            Self::Unknown => f.write_str("unknown"),
        }
    }
}
impl ::std::str::FromStr for ModelTurnEndedDataAepCostSource {
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
impl ::std::convert::TryFrom<&str> for ModelTurnEndedDataAepCostSource {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ModelTurnEndedDataAepCostSource {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ModelTurnEndedDataAepCostSource {
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.model_turn_ended\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.model_turn_ended\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ModelTurnEndedEventAepCorrelationId>,
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
#[doc = "`ModelTurnEndedEventAepCorrelationId`"]
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
pub struct ModelTurnEndedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ModelTurnEndedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ModelTurnEndedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ModelTurnEndedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ModelTurnEndedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ModelTurnEndedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ModelTurnEndedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ModelTurnEndedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ModelTurnEndedEventAepCorrelationId {
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
#[doc = "    \"aep.context_messages\": {"]
#[doc = "      \"title\": \"Aep.Context Messages\","]
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
        rename = "aep.context_messages",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_context_messages: ::std::option::Option<u64>,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.model_turn_started\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.model_turn_started\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ModelTurnStartedEventAepCorrelationId>,
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
#[doc = "`ModelTurnStartedEventAepCorrelationId`"]
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
pub struct ModelTurnStartedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ModelTurnStartedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ModelTurnStartedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ModelTurnStartedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ModelTurnStartedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ModelTurnStartedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ModelTurnStartedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ModelTurnStartedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ModelTurnStartedEventAepCorrelationId {
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
#[doc = "The model produced a reasoning / thinking block during this turn.\n\nDistinct from `text_emitted` — reasoning is not user-facing output;\nit's the model's internal chain-of-thought that some providers\nexpose (Anthropic extended thinking, OpenAI o1/o3 reasoning summaries,\netc.). Consumers can filter on this event type to redact / collapse\nchain-of-thought from displays without losing it from the audit log.\n\n`aep.reasoning.signature` rides along when the provider returns a\ncryptographic signature on the thinking block (Anthropic does this\nfor redacted_thinking blocks); empty when the provider doesn't.\n`aep.reasoning.redacted` flags blocks the provider has returned in\nencrypted-only form (no plaintext) — the wire still records the\noccurrence so audit consumers can count thinking turns."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ReasoningEmittedData\","]
#[doc = "  \"description\": \"The model produced a reasoning / thinking block during this turn.\\n\\nDistinct from `text_emitted` — reasoning is not user-facing output;\\nit's the model's internal chain-of-thought that some providers\\nexpose (Anthropic extended thinking, OpenAI o1/o3 reasoning summaries,\\netc.). Consumers can filter on this event type to redact / collapse\\nchain-of-thought from displays without losing it from the audit log.\\n\\n`aep.reasoning.signature` rides along when the provider returns a\\ncryptographic signature on the thinking block (Anthropic does this\\nfor redacted_thinking blocks); empty when the provider doesn't.\\n`aep.reasoning.redacted` flags blocks the provider has returned in\\nencrypted-only form (no plaintext) — the wire still records the\\noccurrence so audit consumers can count thinking turns.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.reasoning.text\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.reasoning.redacted\": {"]
#[doc = "      \"title\": \"Aep.Reasoning.Redacted\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"boolean\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.reasoning.signature\": {"]
#[doc = "      \"title\": \"Aep.Reasoning.Signature\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.reasoning.text\": {"]
#[doc = "      \"title\": \"Aep.Reasoning.Text\","]
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
        rename = "aep.reasoning.redacted",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_reasoning_redacted: ::std::option::Option<bool>,
    #[serde(
        rename = "aep.reasoning.signature",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_reasoning_signature: ::std::option::Option<::std::string::String>,
    #[serde(rename = "aep.reasoning.text")]
    pub aep_reasoning_text: ::std::string::String,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.reasoning_emitted\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.reasoning_emitted\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ReasoningEmittedEventAepCorrelationId>,
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
#[doc = "`ReasoningEmittedEventAepCorrelationId`"]
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
pub struct ReasoningEmittedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ReasoningEmittedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ReasoningEmittedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ReasoningEmittedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ReasoningEmittedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ReasoningEmittedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ReasoningEmittedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ReasoningEmittedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ReasoningEmittedEventAepCorrelationId {
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
#[doc = "The model declined to generate a response or had its output filtered.\n\nCommon across providers but each exposes a different slice:\n  - Anthropic:  `stop_reason=\"refusal\"` (or `\"sensitive\"`), no\n                structured category, sometimes a refusal-flavored\n                text block.\n  - OpenAI:     `finish_reason=\"content_filter\"` plus a dedicated\n                `refusal` field on the assistant message containing\n                the model's refusal text.\n  - Gemini:     `finishReason` enum (`SAFETY`, `RECITATION`,\n                `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`) plus\n                per-category `safetyRatings`.\n\nAEP normalizes to a provider-agnostic shape: `reason` is the\nprovider's raw code (verbatim, so audit pipelines can match exact\nupstream strings), `message` is the model's refusal text when given,\n`category` is the provider's safety category (free-form because\nevery provider names them differently), `provider` lets downstream\nconsumers normalize the reason code without context-guessing.\n\nA refusal terminates the turn — the model produced no useful text or\ntool call. Whether the *run* terminates is a runner decision (the\nreference runner stops with `StopReason.refused`); a higher-level\nsupervisor may choose to reset history and retry."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"RefusalRecordedData\","]
#[doc = "  \"description\": \"The model declined to generate a response or had its output filtered.\\n\\nCommon across providers but each exposes a different slice:\\n  - Anthropic:  `stop_reason=\\\"refusal\\\"` (or `\\\"sensitive\\\"`), no\\n                structured category, sometimes a refusal-flavored\\n                text block.\\n  - OpenAI:     `finish_reason=\\\"content_filter\\\"` plus a dedicated\\n                `refusal` field on the assistant message containing\\n                the model's refusal text.\\n  - Gemini:     `finishReason` enum (`SAFETY`, `RECITATION`,\\n                `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`) plus\\n                per-category `safetyRatings`.\\n\\nAEP normalizes to a provider-agnostic shape: `reason` is the\\nprovider's raw code (verbatim, so audit pipelines can match exact\\nupstream strings), `message` is the model's refusal text when given,\\n`category` is the provider's safety category (free-form because\\nevery provider names them differently), `provider` lets downstream\\nconsumers normalize the reason code without context-guessing.\\n\\nA refusal terminates the turn — the model produced no useful text or\\ntool call. Whether the *run* terminates is a runner decision (the\\nreference runner stops with `StopReason.refused`); a higher-level\\nsupervisor may choose to reset history and retry.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.refusal.reason\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.refusal.category\": {"]
#[doc = "      \"title\": \"Aep.Refusal.Category\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.refusal.message\": {"]
#[doc = "      \"title\": \"Aep.Refusal.Message\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.refusal.provider\": {"]
#[doc = "      \"title\": \"Aep.Refusal.Provider\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.refusal.reason\": {"]
#[doc = "      \"title\": \"Aep.Refusal.Reason\","]
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
        rename = "aep.refusal.category",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_refusal_category: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "aep.refusal.message",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_refusal_message: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "aep.refusal.provider",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_refusal_provider: ::std::option::Option<::std::string::String>,
    #[serde(rename = "aep.refusal.reason")]
    pub aep_refusal_reason: AepRefusalReason,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.refusal_recorded\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.refusal_recorded\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<RefusalRecordedEventAepCorrelationId>,
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
#[doc = "`RefusalRecordedEventAepCorrelationId`"]
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
pub struct RefusalRecordedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for RefusalRecordedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<RefusalRecordedEventAepCorrelationId> for ::std::string::String {
    fn from(value: RefusalRecordedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for RefusalRecordedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for RefusalRecordedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for RefusalRecordedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for RefusalRecordedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for RefusalRecordedEventAepCorrelationId {
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
#[doc = "`SkillExecutedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SkillExecutedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.skill.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.skill.name\": {"]
#[doc = "      \"title\": \"Aep.Skill.Name\","]
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
pub struct SkillExecutedData {
    #[serde(rename = "aep.skill.name")]
    pub aep_skill_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`SkillExecutedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SkillExecutedEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"$ref\": \"#/$defs/SkillExecutedData\""]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.skill_executed\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.skill_executed\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SkillExecutedEvent {
    #[serde(
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<SkillExecutedEventAepCorrelationId>,
    pub data: SkillExecutedData,
    #[serde(default = "defaults::skill_executed_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::skill_executed_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::skill_executed_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<SkillExecutedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::skill_executed_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`SkillExecutedEventAepCorrelationId`"]
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
pub struct SkillExecutedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for SkillExecutedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SkillExecutedEventAepCorrelationId> for ::std::string::String {
    fn from(value: SkillExecutedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SkillExecutedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SkillExecutedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SkillExecutedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SkillExecutedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SkillExecutedEventAepCorrelationId {
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
#[doc = "`SkillExecutedEventSubject`"]
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
pub struct SkillExecutedEventSubject(::std::string::String);
impl ::std::ops::Deref for SkillExecutedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SkillExecutedEventSubject> for ::std::string::String {
    fn from(value: SkillExecutedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SkillExecutedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SkillExecutedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SkillExecutedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SkillExecutedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SkillExecutedEventSubject {
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
#[doc = "`SkillLoadedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SkillLoadedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.skill.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.skill.name\": {"]
#[doc = "      \"title\": \"Aep.Skill.Name\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"aep.skill.source\": {"]
#[doc = "      \"title\": \"Aep.Skill.Source\","]
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
    #[serde(rename = "aep.skill.name")]
    pub aep_skill_name: ::std::string::String,
    #[serde(
        rename = "aep.skill.source",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_skill_source: ::std::option::Option<::std::string::String>,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.skill_loaded\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.skill_loaded\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<SkillLoadedEventAepCorrelationId>,
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
#[doc = "`SkillLoadedEventAepCorrelationId`"]
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
pub struct SkillLoadedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for SkillLoadedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SkillLoadedEventAepCorrelationId> for ::std::string::String {
    fn from(value: SkillLoadedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SkillLoadedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SkillLoadedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SkillLoadedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SkillLoadedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SkillLoadedEventAepCorrelationId {
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
#[doc = "`Source`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"Source\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"minLength\": 1"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct Source(::std::string::String);
impl ::std::ops::Deref for Source {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<Source> for ::std::string::String {
    fn from(value: Source) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for Source {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for Source {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for Source {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Source {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for Source {
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
#[doc = "`StopReason`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"StopReason\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"converged\","]
#[doc = "    \"budget_exhausted\","]
#[doc = "    \"token_limit\","]
#[doc = "    \"turn_limit\","]
#[doc = "    \"duration_limit\","]
#[doc = "    \"error\","]
#[doc = "    \"interrupted\","]
#[doc = "    \"verifier_failed\","]
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
    #[serde(rename = "budget_exhausted")]
    BudgetExhausted,
    #[serde(rename = "token_limit")]
    TokenLimit,
    #[serde(rename = "turn_limit")]
    TurnLimit,
    #[serde(rename = "duration_limit")]
    DurationLimit,
    #[serde(rename = "error")]
    Error,
    #[serde(rename = "interrupted")]
    Interrupted,
    #[serde(rename = "verifier_failed")]
    VerifierFailed,
    #[serde(rename = "refused")]
    Refused,
}
impl ::std::fmt::Display for StopReason {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Converged => f.write_str("converged"),
            Self::BudgetExhausted => f.write_str("budget_exhausted"),
            Self::TokenLimit => f.write_str("token_limit"),
            Self::TurnLimit => f.write_str("turn_limit"),
            Self::DurationLimit => f.write_str("duration_limit"),
            Self::Error => f.write_str("error"),
            Self::Interrupted => f.write_str("interrupted"),
            Self::VerifierFailed => f.write_str("verifier_failed"),
            Self::Refused => f.write_str("refused"),
        }
    }
}
impl ::std::str::FromStr for StopReason {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "converged" => Ok(Self::Converged),
            "budget_exhausted" => Ok(Self::BudgetExhausted),
            "token_limit" => Ok(Self::TokenLimit),
            "turn_limit" => Ok(Self::TurnLimit),
            "duration_limit" => Ok(Self::DurationLimit),
            "error" => Ok(Self::Error),
            "interrupted" => Ok(Self::Interrupted),
            "verifier_failed" => Ok(Self::VerifierFailed),
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
#[doc = "Subagent descriptor in `agent_started.data.subagents` — what the\nparent model sees when deciding whether to delegate. Same MCP-shaped\ntriple (`name`, `description`, `inputSchema`) tools use, so adapters\ncan render subagents to the model's tool list with no translation."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"_SubagentDecl\","]
#[doc = "  \"description\": \"Subagent descriptor in `agent_started.data.subagents` — what the\\nparent model sees when deciding whether to delegate. Same MCP-shaped\\ntriple (`name`, `description`, `inputSchema`) tools use, so adapters\\ncan render subagents to the model's tool list with no translation.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"description\","]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"description\": {"]
#[doc = "      \"title\": \"Description\","]
#[doc = "      \"type\": \"string\""]
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
    pub description: ::std::string::String,
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
#[doc = "    \"aep.subagent.error\","]
#[doc = "    \"aep.subagent.invocation_id\","]
#[doc = "    \"duration_ms\","]
#[doc = "    \"gen_ai.agent.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.subagent.error\": {"]
#[doc = "      \"title\": \"Aep.Subagent.Error\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"aep.subagent.error.code\": {"]
#[doc = "      \"title\": \"Aep.Subagent.Error.Code\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.subagent.invocation_id\": {"]
#[doc = "      \"title\": \"Aep.Subagent.Invocation Id\","]
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
    #[serde(rename = "aep.subagent.error")]
    pub aep_subagent_error: ::std::string::String,
    #[serde(
        rename = "aep.subagent.error.code",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_subagent_error_code: ::std::option::Option<::std::string::String>,
    #[serde(rename = "aep.subagent.invocation_id")]
    pub aep_subagent_invocation_id: AepSubagentInvocationId,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.subagent_failed\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.subagent_failed\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<SubagentFailedEventAepCorrelationId>,
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
#[doc = "`SubagentFailedEventAepCorrelationId`"]
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
pub struct SubagentFailedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for SubagentFailedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentFailedEventAepCorrelationId> for ::std::string::String {
    fn from(value: SubagentFailedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentFailedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentFailedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentFailedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentFailedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentFailedEventAepCorrelationId {
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
#[doc = "    \"aep.subagent.input\","]
#[doc = "    \"aep.subagent.invocation_id\","]
#[doc = "    \"gen_ai.agent.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.subagent.input\": {"]
#[doc = "      \"title\": \"Aep.Subagent.Input\","]
#[doc = "      \"type\": \"object\","]
#[doc = "      \"additionalProperties\": true"]
#[doc = "    },"]
#[doc = "    \"aep.subagent.invocation_id\": {"]
#[doc = "      \"title\": \"Aep.Subagent.Invocation Id\","]
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
    #[serde(rename = "aep.subagent.input")]
    pub aep_subagent_input: ::serde_json::Map<::std::string::String, ::serde_json::Value>,
    #[serde(rename = "aep.subagent.invocation_id")]
    pub aep_subagent_invocation_id: AepSubagentInvocationId,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.subagent_invoked\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.subagent_invoked\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<SubagentInvokedEventAepCorrelationId>,
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
#[doc = "`SubagentInvokedEventAepCorrelationId`"]
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
pub struct SubagentInvokedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for SubagentInvokedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentInvokedEventAepCorrelationId> for ::std::string::String {
    fn from(value: SubagentInvokedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentInvokedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentInvokedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentInvokedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentInvokedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentInvokedEventAepCorrelationId {
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
#[doc = "Closes the subagent's frame. `span_id` matches the corresponding\n`subagent_invoked` event so consumers can pair them. `aep.subagent.usage`\nrolls up the subagent's own consumption (cost, tokens, turns) — this\nrollup is also reflected in the parent run's cumulative state, but the\nbreakdown is preserved here so consumers can attribute spend to the\nsubagent that incurred it."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"SubagentReturnedData\","]
#[doc = "  \"description\": \"Closes the subagent's frame. `span_id` matches the corresponding\\n`subagent_invoked` event so consumers can pair them. `aep.subagent.usage`\\nrolls up the subagent's own consumption (cost, tokens, turns) — this\\nrollup is also reflected in the parent run's cumulative state, but the\\nbreakdown is preserved here so consumers can attribute spend to the\\nsubagent that incurred it.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.subagent.invocation_id\","]
#[doc = "    \"aep.subagent.reason\","]
#[doc = "    \"aep.subagent.result.text\","]
#[doc = "    \"aep.subagent.usage\","]
#[doc = "    \"duration_ms\","]
#[doc = "    \"gen_ai.agent.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.subagent.invocation_id\": {"]
#[doc = "      \"title\": \"Aep.Subagent.Invocation Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"aep.subagent.reason\": {"]
#[doc = "      \"$ref\": \"#/$defs/StopReason\""]
#[doc = "    },"]
#[doc = "    \"aep.subagent.result.structured\": {"]
#[doc = "      \"title\": \"Aep.Subagent.Result.Structured\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {},"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.subagent.result.text\": {"]
#[doc = "      \"title\": \"Aep.Subagent.Result.Text\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"aep.subagent.usage\": {"]
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
    #[serde(rename = "aep.subagent.invocation_id")]
    pub aep_subagent_invocation_id: AepSubagentInvocationId,
    #[serde(rename = "aep.subagent.reason")]
    pub aep_subagent_reason: StopReason,
    #[serde(
        rename = "aep.subagent.result.structured",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_subagent_result_structured: ::std::option::Option<::serde_json::Value>,
    #[serde(rename = "aep.subagent.result.text")]
    pub aep_subagent_result_text: ::std::string::String,
    #[serde(rename = "aep.subagent.usage")]
    pub aep_subagent_usage: RunStateSnapshot,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.subagent_returned\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.subagent_returned\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<SubagentReturnedEventAepCorrelationId>,
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
#[doc = "`SubagentReturnedEventAepCorrelationId`"]
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
pub struct SubagentReturnedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for SubagentReturnedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<SubagentReturnedEventAepCorrelationId> for ::std::string::String {
    fn from(value: SubagentReturnedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for SubagentReturnedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for SubagentReturnedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for SubagentReturnedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SubagentReturnedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for SubagentReturnedEventAepCorrelationId {
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
#[doc = "    \"aep.text\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.text\": {"]
#[doc = "      \"title\": \"Aep.Text\","]
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
    #[serde(rename = "aep.text")]
    pub aep_text: ::std::string::String,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.text_emitted\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.text_emitted\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<TextEmittedEventAepCorrelationId>,
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
#[doc = "`TextEmittedEventAepCorrelationId`"]
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
pub struct TextEmittedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for TextEmittedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<TextEmittedEventAepCorrelationId> for ::std::string::String {
    fn from(value: TextEmittedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for TextEmittedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for TextEmittedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for TextEmittedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for TextEmittedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for TextEmittedEventAepCorrelationId {
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
#[doc = "Tool descriptor in `agent_started.data.tools` — MCP-shaped + AEP fields."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"_ToolDecl\","]
#[doc = "  \"description\": \"Tool descriptor in `agent_started.data.tools` — MCP-shaped + AEP fields.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"name\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.dispatch_target\": {"]
#[doc = "      \"title\": \"Aep.Dispatch Target\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"enum\": ["]
#[doc = "            \"supervisor_rpc\","]
#[doc = "            \"mcp_server\","]
#[doc = "            \"local\""]
#[doc = "          ]"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.mcp_server_id\": {"]
#[doc = "      \"title\": \"Aep.Mcp Server Id\","]
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
        rename = "aep.dispatch_target",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_dispatch_target: ::std::option::Option<ToolDeclAepDispatchTarget>,
    #[serde(
        rename = "aep.mcp_server_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_mcp_server_id: ::std::option::Option<::std::string::String>,
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
#[doc = "`ToolDeclAepDispatchTarget`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"supervisor_rpc\","]
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
pub enum ToolDeclAepDispatchTarget {
    #[serde(rename = "supervisor_rpc")]
    SupervisorRpc,
    #[serde(rename = "mcp_server")]
    McpServer,
    #[serde(rename = "local")]
    Local,
}
impl ::std::fmt::Display for ToolDeclAepDispatchTarget {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::SupervisorRpc => f.write_str("supervisor_rpc"),
            Self::McpServer => f.write_str("mcp_server"),
            Self::Local => f.write_str("local"),
        }
    }
}
impl ::std::str::FromStr for ToolDeclAepDispatchTarget {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "supervisor_rpc" => Ok(Self::SupervisorRpc),
            "mcp_server" => Ok(Self::McpServer),
            "local" => Ok(Self::Local),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for ToolDeclAepDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolDeclAepDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolDeclAepDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "Wraps the JSON-RPC request alongside AEP-side bookkeeping.\n\n`gen_ai.tool.name` is duplicated at the top of `data` (OTel convention)\neven though it's also inside `rpc.params.name` per MCP — this keeps tool\nfiltering on the trajectory uniform across `tool_invoked` /\n`tool_exec_request` / `tool_returned`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolExecRequestData\","]
#[doc = "  \"description\": \"Wraps the JSON-RPC request alongside AEP-side bookkeeping.\\n\\n`gen_ai.tool.name` is duplicated at the top of `data` (OTel convention)\\neven though it's also inside `rpc.params.name` per MCP — this keeps tool\\nfiltering on the trajectory uniform across `tool_invoked` /\\n`tool_exec_request` / `tool_returned`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.request_id\","]
#[doc = "    \"aep.timeout_ms\","]
#[doc = "    \"aep.tool.dispatch_target\","]
#[doc = "    \"gen_ai.tool.call.id\","]
#[doc = "    \"gen_ai.tool.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"rpc\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.mcp_server_id\": {"]
#[doc = "      \"title\": \"Aep.Mcp Server Id\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.request_id\": {"]
#[doc = "      \"title\": \"Aep.Request Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"aep.timeout_ms\": {"]
#[doc = "      \"title\": \"Aep.Timeout Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"exclusiveMinimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"aep.tool.dispatch_target\": {"]
#[doc = "      \"title\": \"Aep.Tool.Dispatch Target\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"enum\": ["]
#[doc = "        \"supervisor_rpc\","]
#[doc = "        \"mcp_server\""]
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
#[doc = "    \"rpc\": {"]
#[doc = "      \"$ref\": \"#/$defs/JsonRpcRequestPayload\""]
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
pub struct ToolExecRequestData {
    #[serde(
        rename = "aep.mcp_server_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_mcp_server_id: ::std::option::Option<::std::string::String>,
    #[serde(rename = "aep.request_id")]
    pub aep_request_id: AepRequestId,
    #[serde(rename = "aep.timeout_ms")]
    pub aep_timeout_ms: ::std::num::NonZeroU64,
    #[serde(rename = "aep.tool.dispatch_target")]
    pub aep_tool_dispatch_target: AepToolDispatchTarget,
    #[serde(rename = "gen_ai.tool.call.id")]
    pub gen_ai_tool_call_id: GenAiToolCallId,
    #[serde(rename = "gen_ai.tool.name")]
    pub gen_ai_tool_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub rpc: JsonRpcRequestPayload,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "Agent calls into an external service (supervisor RPC or MCP server).\n\n`source` is `aep://runner` because the runner emits this event when the\nagent decides to call a tool whose implementation is external."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolExecRequestEvent\","]
#[doc = "  \"description\": \"Agent calls into an external service (supervisor RPC or MCP server).\\n\\n`source` is `aep://runner` because the runner emits this event when the\\nagent decides to call a tool whose implementation is external.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"$ref\": \"#/$defs/ToolExecRequestData\""]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.tool_exec_request\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.tool_exec_request\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ToolExecRequestEvent {
    #[serde(
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ToolExecRequestEventAepCorrelationId>,
    pub data: ToolExecRequestData,
    #[serde(default = "defaults::tool_exec_request_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::tool_exec_request_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::tool_exec_request_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ToolExecRequestEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::tool_exec_request_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ToolExecRequestEventAepCorrelationId`"]
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
pub struct ToolExecRequestEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolExecRequestEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolExecRequestEventAepCorrelationId> for ::std::string::String {
    fn from(value: ToolExecRequestEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolExecRequestEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolExecRequestEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolExecRequestEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolExecRequestEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolExecRequestEventAepCorrelationId {
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
#[doc = "`ToolExecRequestEventSubject`"]
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
pub struct ToolExecRequestEventSubject(::std::string::String);
impl ::std::ops::Deref for ToolExecRequestEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolExecRequestEventSubject> for ::std::string::String {
    fn from(value: ToolExecRequestEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolExecRequestEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolExecRequestEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolExecRequestEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolExecRequestEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolExecRequestEventSubject {
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
#[doc = "Wraps the JSON-RPC response. `source` URI on the envelope identifies\nwho answered (supervisor or mcp/<server_id>).\n\n`gen_ai.tool.name` echoes the request's tool name for observability —\nconsumers shouldn't need to cross-reference the request to filter replies."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolExecResolvedData\","]
#[doc = "  \"description\": \"Wraps the JSON-RPC response. `source` URI on the envelope identifies\\nwho answered (supervisor or mcp/<server_id>).\\n\\n`gen_ai.tool.name` echoes the request's tool name for observability —\\nconsumers shouldn't need to cross-reference the request to filter replies.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.request_id\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"rpc\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.request_id\": {"]
#[doc = "      \"title\": \"Aep.Request Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"gen_ai.tool.name\": {"]
#[doc = "      \"title\": \"Gen Ai.Tool.Name\","]
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
#[doc = "    \"rpc\": {"]
#[doc = "      \"$ref\": \"#/$defs/JsonRpcResponsePayload\""]
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
pub struct ToolExecResolvedData {
    #[serde(rename = "aep.request_id")]
    pub aep_request_id: AepRequestId,
    #[serde(
        rename = "gen_ai.tool.name",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub gen_ai_tool_name: ::std::option::Option<::std::string::String>,
    pub parent_span_id: ParentSpanId,
    pub rpc: JsonRpcResponsePayload,
    pub span_id: SpanId,
    pub trace_id: TraceId,
}
#[doc = "RPC reply recorded into the trajectory verbatim. `source` is the URI\nof the responding service: `aep://supervisor` or `aep://mcp/<server_id>`."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolExecResolvedEvent\","]
#[doc = "  \"description\": \"RPC reply recorded into the trajectory verbatim. `source` is the URI\\nof the responding service: `aep://supervisor` or `aep://mcp/<server_id>`.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\","]
#[doc = "    \"source\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"$ref\": \"#/$defs/ToolExecResolvedData\""]
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
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
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
#[doc = "      \"default\": \"aep.tool_exec_resolved\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.tool_exec_resolved\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ToolExecResolvedEvent {
    #[serde(
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ToolExecResolvedEventAepCorrelationId>,
    pub data: ToolExecResolvedData,
    #[serde(default = "defaults::tool_exec_resolved_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    pub source: Source,
    #[serde(default = "defaults::tool_exec_resolved_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ToolExecResolvedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::tool_exec_resolved_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ToolExecResolvedEventAepCorrelationId`"]
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
pub struct ToolExecResolvedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolExecResolvedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolExecResolvedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ToolExecResolvedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolExecResolvedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolExecResolvedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolExecResolvedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolExecResolvedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolExecResolvedEventAepCorrelationId {
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
#[doc = "`ToolExecResolvedEventSubject`"]
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
pub struct ToolExecResolvedEventSubject(::std::string::String);
impl ::std::ops::Deref for ToolExecResolvedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolExecResolvedEventSubject> for ::std::string::String {
    fn from(value: ToolExecResolvedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolExecResolvedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolExecResolvedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolExecResolvedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolExecResolvedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolExecResolvedEventSubject {
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
#[doc = "`ToolExecTimedOutData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolExecTimedOutData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.request_id\","]
#[doc = "    \"aep.timeout_ms\","]
#[doc = "    \"gen_ai.tool.call.id\","]
#[doc = "    \"gen_ai.tool.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.request_id\": {"]
#[doc = "      \"title\": \"Aep.Request Id\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"aep.timeout_ms\": {"]
#[doc = "      \"title\": \"Aep.Timeout Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"exclusiveMinimum\": 0.0"]
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
pub struct ToolExecTimedOutData {
    #[serde(rename = "aep.request_id")]
    pub aep_request_id: AepRequestId,
    #[serde(rename = "aep.timeout_ms")]
    pub aep_timeout_ms: ::std::num::NonZeroU64,
    #[serde(rename = "gen_ai.tool.call.id")]
    pub gen_ai_tool_call_id: GenAiToolCallId,
    #[serde(rename = "gen_ai.tool.name")]
    pub gen_ai_tool_name: ::std::string::String,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    pub step: u64,
    pub trace_id: TraceId,
}
#[doc = "`ToolExecTimedOutEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolExecTimedOutEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"$ref\": \"#/$defs/ToolExecTimedOutData\""]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.tool_exec_timed_out\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.tool_exec_timed_out\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ToolExecTimedOutEvent {
    #[serde(
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ToolExecTimedOutEventAepCorrelationId>,
    pub data: ToolExecTimedOutData,
    #[serde(default = "defaults::tool_exec_timed_out_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::tool_exec_timed_out_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::tool_exec_timed_out_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<ToolExecTimedOutEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::tool_exec_timed_out_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`ToolExecTimedOutEventAepCorrelationId`"]
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
pub struct ToolExecTimedOutEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolExecTimedOutEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolExecTimedOutEventAepCorrelationId> for ::std::string::String {
    fn from(value: ToolExecTimedOutEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolExecTimedOutEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolExecTimedOutEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolExecTimedOutEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolExecTimedOutEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolExecTimedOutEventAepCorrelationId {
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
#[doc = "`ToolExecTimedOutEventSubject`"]
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
pub struct ToolExecTimedOutEventSubject(::std::string::String);
impl ::std::ops::Deref for ToolExecTimedOutEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolExecTimedOutEventSubject> for ::std::string::String {
    fn from(value: ToolExecTimedOutEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolExecTimedOutEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolExecTimedOutEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolExecTimedOutEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolExecTimedOutEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolExecTimedOutEventSubject {
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
#[doc = "`ToolFailedData`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"ToolFailedData\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.tool.error\","]
#[doc = "    \"gen_ai.tool.call.id\","]
#[doc = "    \"gen_ai.tool.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.tool.error\": {"]
#[doc = "      \"title\": \"Aep.Tool.Error\","]
#[doc = "      \"type\": \"string\""]
#[doc = "    },"]
#[doc = "    \"aep.tool.error.code\": {"]
#[doc = "      \"title\": \"Aep.Tool.Error.Code\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"integer\""]
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
    #[serde(rename = "aep.tool.error")]
    pub aep_tool_error: ::std::string::String,
    #[serde(
        rename = "aep.tool.error.code",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_tool_error_code: ::std::option::Option<i64>,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.tool_failed\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.tool_failed\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ToolFailedEventAepCorrelationId>,
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
#[doc = "`ToolFailedEventAepCorrelationId`"]
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
pub struct ToolFailedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolFailedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolFailedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ToolFailedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolFailedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolFailedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolFailedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolFailedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolFailedEventAepCorrelationId {
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
#[doc = "    \"aep.tool.dispatch_target\": {"]
#[doc = "      \"title\": \"Aep.Tool.Dispatch Target\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\","]
#[doc = "          \"enum\": ["]
#[doc = "            \"supervisor_rpc\","]
#[doc = "            \"mcp_server\","]
#[doc = "            \"local\""]
#[doc = "          ]"]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.tool.subtype\": {"]
#[doc = "      \"title\": \"Aep.Tool.Subtype\","]
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
        rename = "aep.tool.dispatch_target",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_tool_dispatch_target: ::std::option::Option<ToolInvokedDataAepToolDispatchTarget>,
    #[serde(
        rename = "aep.tool.subtype",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_tool_subtype: ::std::option::Option<::std::string::String>,
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
#[doc = "`ToolInvokedDataAepToolDispatchTarget`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"supervisor_rpc\","]
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
pub enum ToolInvokedDataAepToolDispatchTarget {
    #[serde(rename = "supervisor_rpc")]
    SupervisorRpc,
    #[serde(rename = "mcp_server")]
    McpServer,
    #[serde(rename = "local")]
    Local,
}
impl ::std::fmt::Display for ToolInvokedDataAepToolDispatchTarget {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::SupervisorRpc => f.write_str("supervisor_rpc"),
            Self::McpServer => f.write_str("mcp_server"),
            Self::Local => f.write_str("local"),
        }
    }
}
impl ::std::str::FromStr for ToolInvokedDataAepToolDispatchTarget {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "supervisor_rpc" => Ok(Self::SupervisorRpc),
            "mcp_server" => Ok(Self::McpServer),
            "local" => Ok(Self::Local),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for ToolInvokedDataAepToolDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolInvokedDataAepToolDispatchTarget {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolInvokedDataAepToolDispatchTarget {
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.tool_invoked\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.tool_invoked\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ToolInvokedEventAepCorrelationId>,
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
#[doc = "`ToolInvokedEventAepCorrelationId`"]
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
pub struct ToolInvokedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolInvokedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolInvokedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ToolInvokedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolInvokedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolInvokedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolInvokedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolInvokedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolInvokedEventAepCorrelationId {
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
#[doc = "    \"aep.tool.result.text\","]
#[doc = "    \"duration_ms\","]
#[doc = "    \"gen_ai.tool.call.id\","]
#[doc = "    \"gen_ai.tool.name\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"step\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.tool.rejected\": {"]
#[doc = "      \"title\": \"Aep.Tool.Rejected\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"boolean\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.tool.rejection_reason\": {"]
#[doc = "      \"title\": \"Aep.Tool.Rejection Reason\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"type\": \"string\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.tool.result.structured\": {"]
#[doc = "      \"title\": \"Aep.Tool.Result.Structured\","]
#[doc = "      \"anyOf\": ["]
#[doc = "        {},"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.tool.result.text\": {"]
#[doc = "      \"title\": \"Aep.Tool.Result.Text\","]
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
        rename = "aep.tool.rejected",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_tool_rejected: ::std::option::Option<bool>,
    #[serde(
        rename = "aep.tool.rejection_reason",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_tool_rejection_reason: ::std::option::Option<::std::string::String>,
    #[serde(
        rename = "aep.tool.result.structured",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_tool_result_structured: ::std::option::Option<::serde_json::Value>,
    #[serde(rename = "aep.tool.result.text")]
    pub aep_tool_result_text: ::std::string::String,
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
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.tool_returned\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.tool_returned\""]
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
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<ToolReturnedEventAepCorrelationId>,
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
#[doc = "`ToolReturnedEventAepCorrelationId`"]
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
pub struct ToolReturnedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for ToolReturnedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ToolReturnedEventAepCorrelationId> for ::std::string::String {
    fn from(value: ToolReturnedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ToolReturnedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for ToolReturnedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for ToolReturnedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ToolReturnedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ToolReturnedEventAepCorrelationId {
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
#[doc = "Why a verifier failed for non-logic reasons. Distinguishes\n'environment broken' (script missing, timed out, crashed) from\n'rule legitimately failed' (passed=false with no error)."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"VerifierError\","]
#[doc = "  \"description\": \"Why a verifier failed for non-logic reasons. Distinguishes\\n'environment broken' (script missing, timed out, crashed) from\\n'rule legitimately failed' (passed=false with no error).\","]
#[doc = "  \"type\": \"string\","]
#[doc = "  \"enum\": ["]
#[doc = "    \"source_unavailable\","]
#[doc = "    \"source_timed_out\","]
#[doc = "    \"source_crashed\""]
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
pub enum VerifierError {
    #[serde(rename = "source_unavailable")]
    SourceUnavailable,
    #[serde(rename = "source_timed_out")]
    SourceTimedOut,
    #[serde(rename = "source_crashed")]
    SourceCrashed,
}
impl ::std::fmt::Display for VerifierError {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::SourceUnavailable => f.write_str("source_unavailable"),
            Self::SourceTimedOut => f.write_str("source_timed_out"),
            Self::SourceCrashed => f.write_str("source_crashed"),
        }
    }
}
impl ::std::str::FromStr for VerifierError {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "source_unavailable" => Ok(Self::SourceUnavailable),
            "source_timed_out" => Ok(Self::SourceTimedOut),
            "source_crashed" => Ok(Self::SourceCrashed),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for VerifierError {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for VerifierError {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for VerifierError {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "The result of a deterministic Boolean check."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"VerifierEvaluatedData\","]
#[doc = "  \"description\": \"The result of a deterministic Boolean check.\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"aep.verifier.duration_ms\","]
#[doc = "    \"aep.verifier.name\","]
#[doc = "    \"aep.verifier.passed\","]
#[doc = "    \"parent_span_id\","]
#[doc = "    \"span_id\","]
#[doc = "    \"trace_id\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.verifier.data\": {"]
#[doc = "      \"title\": \"Aep.Verifier.Data\","]
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
#[doc = "    \"aep.verifier.duration_ms\": {"]
#[doc = "      \"title\": \"Aep.Verifier.Duration Ms\","]
#[doc = "      \"type\": \"integer\","]
#[doc = "      \"minimum\": 0.0"]
#[doc = "    },"]
#[doc = "    \"aep.verifier.error\": {"]
#[doc = "      \"anyOf\": ["]
#[doc = "        {"]
#[doc = "          \"$ref\": \"#/$defs/VerifierError\""]
#[doc = "        },"]
#[doc = "        {"]
#[doc = "          \"type\": \"null\""]
#[doc = "        }"]
#[doc = "      ]"]
#[doc = "    },"]
#[doc = "    \"aep.verifier.name\": {"]
#[doc = "      \"title\": \"Aep.Verifier.Name\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"minLength\": 1"]
#[doc = "    },"]
#[doc = "    \"aep.verifier.passed\": {"]
#[doc = "      \"title\": \"Aep.Verifier.Passed\","]
#[doc = "      \"type\": \"boolean\""]
#[doc = "    },"]
#[doc = "    \"aep.verifier.subject_call_ids\": {"]
#[doc = "      \"title\": \"Aep.Verifier.Subject Call Ids\","]
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
#[doc = "    \"aep.verifier.subject_request_ids\": {"]
#[doc = "      \"title\": \"Aep.Verifier.Subject Request Ids\","]
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
pub struct VerifierEvaluatedData {
    #[serde(
        rename = "aep.verifier.data",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_verifier_data:
        ::std::option::Option<::serde_json::Map<::std::string::String, ::serde_json::Value>>,
    #[serde(rename = "aep.verifier.duration_ms")]
    pub aep_verifier_duration_ms: u64,
    #[serde(
        rename = "aep.verifier.error",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_verifier_error: ::std::option::Option<VerifierError>,
    #[serde(rename = "aep.verifier.name")]
    pub aep_verifier_name: AepVerifierName,
    #[serde(rename = "aep.verifier.passed")]
    pub aep_verifier_passed: bool,
    #[serde(
        rename = "aep.verifier.subject_call_ids",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_verifier_subject_call_ids:
        ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    #[serde(
        rename = "aep.verifier.subject_request_ids",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_verifier_subject_request_ids:
        ::std::option::Option<::std::vec::Vec<::std::string::String>>,
    pub parent_span_id: ParentSpanId,
    pub span_id: SpanId,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub step: ::std::option::Option<u64>,
    pub trace_id: TraceId,
}
#[doc = "`VerifierEvaluatedEvent`"]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"title\": \"VerifierEvaluatedEvent\","]
#[doc = "  \"type\": \"object\","]
#[doc = "  \"required\": ["]
#[doc = "    \"data\""]
#[doc = "  ],"]
#[doc = "  \"properties\": {"]
#[doc = "    \"aep.correlation_id\": {"]
#[doc = "      \"title\": \"Aep.Correlation Id\","]
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
#[doc = "      \"$ref\": \"#/$defs/VerifierEvaluatedData\""]
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
#[doc = "      \"default\": \"aep://runner\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep://runner\""]
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
#[doc = "      \"default\": \"aep.verifier_evaluated\","]
#[doc = "      \"type\": \"string\","]
#[doc = "      \"const\": \"aep.verifier_evaluated\""]
#[doc = "    }"]
#[doc = "  },"]
#[doc = "  \"additionalProperties\": false"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct VerifierEvaluatedEvent {
    #[serde(
        rename = "aep.correlation_id",
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub aep_correlation_id: ::std::option::Option<VerifierEvaluatedEventAepCorrelationId>,
    pub data: VerifierEvaluatedData,
    #[serde(default = "defaults::verifier_evaluated_event_datacontenttype")]
    pub datacontenttype: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub dataschema: ::std::option::Option<::std::string::String>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub id: ::std::option::Option<Id>,
    #[serde(default = "defaults::verifier_evaluated_event_source")]
    pub source: ::std::string::String,
    #[serde(default = "defaults::verifier_evaluated_event_specversion")]
    pub specversion: ::std::string::String,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub subject: ::std::option::Option<VerifierEvaluatedEventSubject>,
    #[serde(default, skip_serializing_if = "::std::option::Option::is_none")]
    pub time: ::std::option::Option<::std::string::String>,
    #[serde(rename = "type", default = "defaults::verifier_evaluated_event_type")]
    pub type_: ::std::string::String,
}
#[doc = "`VerifierEvaluatedEventAepCorrelationId`"]
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
pub struct VerifierEvaluatedEventAepCorrelationId(::std::string::String);
impl ::std::ops::Deref for VerifierEvaluatedEventAepCorrelationId {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<VerifierEvaluatedEventAepCorrelationId> for ::std::string::String {
    fn from(value: VerifierEvaluatedEventAepCorrelationId) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for VerifierEvaluatedEventAepCorrelationId {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for VerifierEvaluatedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for VerifierEvaluatedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for VerifierEvaluatedEventAepCorrelationId {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for VerifierEvaluatedEventAepCorrelationId {
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
#[doc = "`VerifierEvaluatedEventSubject`"]
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
pub struct VerifierEvaluatedEventSubject(::std::string::String);
impl ::std::ops::Deref for VerifierEvaluatedEventSubject {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<VerifierEvaluatedEventSubject> for ::std::string::String {
    fn from(value: VerifierEvaluatedEventSubject) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for VerifierEvaluatedEventSubject {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        if value.chars().count() < 1usize {
            return Err("shorter than 1 characters".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for VerifierEvaluatedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<&::std::string::String> for VerifierEvaluatedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: &::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for VerifierEvaluatedEventSubject {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for VerifierEvaluatedEventSubject {
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
    pub(super) fn agent_started_data_aep_schema_version() -> ::std::string::String {
        "0.1".to_string()
    }
    pub(super) fn agent_started_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn agent_started_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn agent_started_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn agent_started_event_type() -> ::std::string::String {
        "aep.agent_started".to_string()
    }
    pub(super) fn agent_stopped_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn agent_stopped_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn agent_stopped_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn agent_stopped_event_type() -> ::std::string::String {
        "aep.agent_stopped".to_string()
    }
    pub(super) fn approval_requested_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn approval_requested_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn approval_requested_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn approval_requested_event_type() -> ::std::string::String {
        "aep.approval_requested".to_string()
    }
    pub(super) fn approval_resolved_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn approval_resolved_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn approval_resolved_event_type() -> ::std::string::String {
        "aep.approval_resolved".to_string()
    }
    pub(super) fn cost_recorded_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn cost_recorded_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn cost_recorded_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn cost_recorded_event_type() -> ::std::string::String {
        "aep.cost_recorded".to_string()
    }
    pub(super) fn error_occurred_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn error_occurred_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn error_occurred_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn error_occurred_event_type() -> ::std::string::String {
        "aep.error_occurred".to_string()
    }
    pub(super) fn json_rpc_request_payload_jsonrpc() -> ::std::string::String {
        "2.0".to_string()
    }
    pub(super) fn json_rpc_response_payload_jsonrpc() -> ::std::string::String {
        "2.0".to_string()
    }
    pub(super) fn mcp_server_connected_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn mcp_server_connected_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn mcp_server_connected_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn mcp_server_connected_event_type() -> ::std::string::String {
        "aep.mcp_server_connected".to_string()
    }
    pub(super) fn mcp_server_disconnected_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn mcp_server_disconnected_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn mcp_server_disconnected_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn mcp_server_disconnected_event_type() -> ::std::string::String {
        "aep.mcp_server_disconnected".to_string()
    }
    pub(super) fn model_turn_ended_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn model_turn_ended_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn model_turn_ended_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn model_turn_ended_event_type() -> ::std::string::String {
        "aep.model_turn_ended".to_string()
    }
    pub(super) fn model_turn_started_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn model_turn_started_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn model_turn_started_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn model_turn_started_event_type() -> ::std::string::String {
        "aep.model_turn_started".to_string()
    }
    pub(super) fn reasoning_emitted_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn reasoning_emitted_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn reasoning_emitted_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn reasoning_emitted_event_type() -> ::std::string::String {
        "aep.reasoning_emitted".to_string()
    }
    pub(super) fn refusal_recorded_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn refusal_recorded_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn refusal_recorded_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn refusal_recorded_event_type() -> ::std::string::String {
        "aep.refusal_recorded".to_string()
    }
    pub(super) fn skill_executed_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn skill_executed_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn skill_executed_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn skill_executed_event_type() -> ::std::string::String {
        "aep.skill_executed".to_string()
    }
    pub(super) fn skill_loaded_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn skill_loaded_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn skill_loaded_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn skill_loaded_event_type() -> ::std::string::String {
        "aep.skill_loaded".to_string()
    }
    pub(super) fn subagent_failed_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn subagent_failed_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn subagent_failed_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn subagent_failed_event_type() -> ::std::string::String {
        "aep.subagent_failed".to_string()
    }
    pub(super) fn subagent_invoked_data_gen_ai_operation_name() -> ::std::string::String {
        "invoke_agent".to_string()
    }
    pub(super) fn subagent_invoked_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn subagent_invoked_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn subagent_invoked_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn subagent_invoked_event_type() -> ::std::string::String {
        "aep.subagent_invoked".to_string()
    }
    pub(super) fn subagent_returned_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn subagent_returned_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn subagent_returned_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn subagent_returned_event_type() -> ::std::string::String {
        "aep.subagent_returned".to_string()
    }
    pub(super) fn text_emitted_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn text_emitted_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn text_emitted_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn text_emitted_event_type() -> ::std::string::String {
        "aep.text_emitted".to_string()
    }
    pub(super) fn tool_exec_request_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_exec_request_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn tool_exec_request_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_exec_request_event_type() -> ::std::string::String {
        "aep.tool_exec_request".to_string()
    }
    pub(super) fn tool_exec_resolved_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_exec_resolved_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_exec_resolved_event_type() -> ::std::string::String {
        "aep.tool_exec_resolved".to_string()
    }
    pub(super) fn tool_exec_timed_out_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_exec_timed_out_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn tool_exec_timed_out_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_exec_timed_out_event_type() -> ::std::string::String {
        "aep.tool_exec_timed_out".to_string()
    }
    pub(super) fn tool_failed_event_datacontenttype() -> ::std::option::Option<::std::string::String>
    {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_failed_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn tool_failed_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_failed_event_type() -> ::std::string::String {
        "aep.tool_failed".to_string()
    }
    pub(super) fn tool_invoked_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_invoked_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn tool_invoked_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_invoked_event_type() -> ::std::string::String {
        "aep.tool_invoked".to_string()
    }
    pub(super) fn tool_returned_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn tool_returned_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn tool_returned_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn tool_returned_event_type() -> ::std::string::String {
        "aep.tool_returned".to_string()
    }
    pub(super) fn verifier_evaluated_event_datacontenttype(
    ) -> ::std::option::Option<::std::string::String> {
        ::std::option::Option::Some("application/json".to_string())
    }
    pub(super) fn verifier_evaluated_event_source() -> ::std::string::String {
        "aep://runner".to_string()
    }
    pub(super) fn verifier_evaluated_event_specversion() -> ::std::string::String {
        "1.0".to_string()
    }
    pub(super) fn verifier_evaluated_event_type() -> ::std::string::String {
        "aep.verifier_evaluated".to_string()
    }
}
