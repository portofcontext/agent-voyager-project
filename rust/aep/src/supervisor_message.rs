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
#[doc = "Supervisor (or MCP server) → runner reply. v0.1 carries only `aep.tool_exec_resolved` events. `source` is `aep://supervisor` for supervisor-routed RPCs or `aep://mcp/<server_id>` for MCP-server-routed RPCs. The payload's `data.rpc` is a JSON-RPC 2.0 response."]
#[doc = r""]
#[doc = r" <details><summary>JSON schema</summary>"]
#[doc = r""]
#[doc = r" ```json"]
#[doc = "{"]
#[doc = "  \"$id\": \"https://aep.dev/schema/v0.1/supervisor-message.schema.json\","]
#[doc = "  \"title\": \"AEP v0.1 SupervisorMessage\","]
#[doc = "  \"description\": \"Supervisor (or MCP server) → runner reply. v0.1 carries only `aep.tool_exec_resolved` events. `source` is `aep://supervisor` for supervisor-routed RPCs or `aep://mcp/<server_id>` for MCP-server-routed RPCs. The payload's `data.rpc` is a JSON-RPC 2.0 response.\","]
#[doc = "  \"anyOf\": ["]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ToolExecResolvedEvent\""]
#[doc = "    },"]
#[doc = "    {"]
#[doc = "      \"$ref\": \"#/$defs/ApprovalResolvedEvent\""]
#[doc = "    }"]
#[doc = "  ]"]
#[doc = "}"]
#[doc = r" ```"]
#[doc = r" </details>"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
pub struct AepV01SupervisorMessage {
    #[serde(
        flatten,
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub subtype_0: ::std::option::Option<ToolExecResolvedEvent>,
    #[serde(
        flatten,
        default,
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub subtype_1: ::std::option::Option<ApprovalResolvedEvent>,
}
impl ::std::default::Default for AepV01SupervisorMessage {
    fn default() -> Self {
        Self {
            subtype_0: Default::default(),
            subtype_1: Default::default(),
        }
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
#[doc = r" Generation of default values for serde."]
pub mod defaults {
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
    pub(super) fn json_rpc_response_payload_jsonrpc() -> ::std::string::String {
        "2.0".to_string()
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
}
