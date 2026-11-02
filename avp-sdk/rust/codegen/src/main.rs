use std::{
    error::Error,
    fs,
    io::Write,
    path::Path,
    process::{Command, Stdio},
};

use quote::{format_ident, quote};
use serde_json::{Value, json};

// Typify reads draft-7 schemas. These rewrites preserve the 2020-12 wire shapes.
fn normalize(schema: &mut Value) {
    let Some(object) = schema.as_object_mut() else {
        return;
    };
    object.remove("title");
    if object.get("default").is_some_and(Value::is_null) {
        object.remove("default");
    }
    if let Some(constant) = object.remove("const") {
        object.insert("enum".into(), json!([constant]));
    }
    if object.get("additionalProperties") == Some(&Value::Bool(true)) {
        object.insert("additionalProperties".into(), json!({}));
    }
    if object
        .get("anyOf")
        .and_then(Value::as_array)
        .is_some_and(|variants| {
            variants
                .iter()
                .any(|v| v.get("$ref") == Some(&json!("#/$defs/JsonValue")))
        })
    {
        object.remove("anyOf");
    }
    if let (Some(required), Some(additional)) = (
        object.get("required").and_then(Value::as_array).cloned(),
        object
            .get("additionalProperties")
            .filter(|v| v.is_object())
            .cloned(),
    ) {
        let properties = object.entry("properties").or_insert(json!({}));
        for name in required.iter().filter_map(Value::as_str) {
            properties
                .as_object_mut()
                .unwrap()
                .entry(name)
                .or_insert(additional.clone());
        }
    }
    for field in ["$defs", "properties", "patternProperties"] {
        if let Some(children) = object.get_mut(field).and_then(Value::as_object_mut) {
            children.values_mut().for_each(normalize);
        }
    }
    for field in ["additionalProperties", "items"] {
        if let Some(child) = object.get_mut(field) {
            normalize(child);
        }
    }
    for field in ["anyOf", "oneOf", "allOf"] {
        if let Some(children) = object.get_mut(field).and_then(Value::as_array_mut) {
            children.iter_mut().for_each(normalize);
        }
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let mut schema: Value = serde_json::from_str(&fs::read_to_string(
        root.join("spec/v0.1/trajectory.schema.json"),
    )?)?;
    for (file, name) in [
        ("commission", "Commission"),
        ("agent-descriptor", "AgentDescriptor"),
    ] {
        let mut standalone: Value = serde_json::from_str(&fs::read_to_string(
            root.join(format!("spec/v0.1/{file}.schema.json")),
        )?)?;
        let mut embedded = schema["$defs"][name].clone();
        standalone = serde_json::from_str(&serde_json::to_string(&standalone)?.replace(
            "#/$defs/Skill",
            if name == "Commission" {
                "#/$defs/avp__commission__Skill"
            } else {
                "#/$defs/avp__descriptor__Skill"
            },
        ))?;
        for (key, definition) in standalone["$defs"].as_object().unwrap() {
            let embedded_key = if key == "Skill" {
                if name == "Commission" {
                    "avp__commission__Skill"
                } else {
                    "avp__descriptor__Skill"
                }
            } else {
                key
            };
            if definition != &schema["$defs"][embedded_key] {
                return Err(format!("{file}: {key} differs between schemas").into());
            }
        }
        for key in ["$schema", "$id", "$defs", "title", "description"] {
            standalone.as_object_mut().unwrap().remove(key);
            embedded.as_object_mut().unwrap().remove(key);
        }
        if standalone != embedded {
            return Err(format!("{name} differs between schemas").into());
        }
    }
    let definitions = schema["$defs"].as_object().unwrap().clone();
    normalize(&mut schema);
    schema["title"] = "Event".into();
    for definition in schema["$defs"].as_object_mut().unwrap().values_mut() {
        if let Some(version) = definition
            .get_mut("properties")
            .and_then(|p| p.get_mut("avp_version"))
        {
            version["title"] = "AvpVersion".into();
        }
    }
    for (name, field, title) in [
        ("AgentStopped", "reason", "StopReason"),
        ("SubagentReturned", "subagent_reason", "StopReason"),
        ("Usage", "cost_source", "CostSource"),
        ("ErrorOccurred", "error_code", "ErrorCode"),
        ("Model", "provider", "Provider"),
        ("ModelRef", "provider", "Provider"),
    ] {
        schema["$defs"][name]["properties"][field]["title"] = title.into();
    }
    schema["$defs"]["SubagentUsage"]["properties"]["cost_source"]["anyOf"][0]["title"] =
        "CostSource".into();
    let mut types = typify::TypeSpace::default();
    types.add_root_schema(serde_json::from_value(schema)?)?;
    let mut syntax = syn::parse2::<syn::File>(types.to_stream())?;
    let mut extra = Vec::new();
    for item in &mut syntax.items {
        if let syn::Item::Enum(item) = item
            && item.ident == "ErrorCode"
        {
            item.variants
                .iter_mut()
                .find(|v| v.ident == "Unknown")
                .unwrap()
                .attrs
                .push(syn::parse_quote!(#[serde(other)]));
        }
        let syn::Item::Struct(item) = item else {
            continue;
        };
        let name = item.ident.to_string();
        let schema_name = match name.as_str() {
            "AvpCommissionSkill" => "avp__commission__Skill",
            "AvpDescriptorSkill" => "avp__descriptor__Skill",
            _ => &name,
        };
        if definitions
            .get(schema_name)
            .and_then(|d| d.get("type"))
            .and_then(Value::as_str)
            != Some("object")
        {
            continue;
        }
        let ident = item.ident.clone();
        let raw_ident = format_ident!("{ident}Input");
        let mut raw = item.clone();
        raw.ident = raw_ident.clone();
        raw.vis = syn::Visibility::Inherited;
        raw.attrs.retain(|a| !a.path().is_ident("derive"));
        raw.attrs
            .insert(0, syn::parse_quote!(#[derive(::serde::Deserialize)]));
        raw.attrs.push(syn::parse_quote!(#[serde(remote = #name)]));
        item.attrs.retain(|a| !a.path().is_ident("derive"));
        item.attrs.insert(
            0,
            syn::parse_quote!(#[derive(::serde::Serialize, Clone, Debug)]),
        );
        extra.push(quote! {
            #raw
            impl<'de> ::serde::Deserialize<'de> for #ident {
                fn deserialize<D: ::serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
                    let value = ::serde_json::Value::deserialize(deserializer)?;
                    crate::validation::validate(#schema_name, &value).map_err(::serde::de::Error::custom)?;
                    #raw_ident::deserialize(value).map_err(::serde::de::Error::custom)
                }
            }
        });
    }
    syntax
        .items
        .extend(syn::parse2::<syn::File>(quote!(#(#extra)*))?.items);
    let source = format!(
        "// Generated by avp-sdk/rust/codegen. Do not edit.\n{}",
        prettyplease::unparse(&syntax)
    );
    let mut formatter = Command::new("rustfmt")
        .args(["--edition", "2024", "--emit", "stdout"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()?;
    formatter
        .stdin
        .take()
        .unwrap()
        .write_all(source.as_bytes())?;
    let formatted = formatter.wait_with_output()?;
    if !formatted.status.success() {
        return Err("rustfmt failed".into());
    }
    let output = String::from_utf8(formatted.stdout)?;
    let check = std::env::args().any(|a| a == "--check");
    let mut files = vec![("src/wire.rs".to_string(), output)];
    files.push((
        "src/schemas/trajectory.json".into(),
        fs::read_to_string(root.join("spec/v0.1/trajectory.schema.json"))?,
    ));
    for (name, content) in files {
        let path = root.join("avp-sdk/rust").join(&name);
        if check {
            if fs::read_to_string(&path)? != content {
                return Err(format!("{name} is stale; run make sdk-rust-generate").into());
            }
        } else {
            fs::create_dir_all(path.parent().unwrap())?;
            fs::write(path, content)?;
        }
    }
    Ok(())
}
