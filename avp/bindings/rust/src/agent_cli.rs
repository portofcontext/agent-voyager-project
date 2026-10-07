//! The stock agent command line.
//!
//! Every AVP agent answers the same three commands, which `avp-conformance`
//! and the `avp` CLI drive:
//!
//! - `ping --out <path>`: write `{"type":"pong"}` and exit, without booting
//!   the agent.
//! - `describe [--out <path>]`: print the agent's descriptor JSON (to `--out`,
//!   or stdout).
//! - `run --commission <json|path> [--built-in <json|path>] --out <path>`: run
//!   the Commission and write the trajectory to `--out` as NDJSON.
//!
//! An adapter supplies two closures and gets the whole contract:
//!
//! ```no_run
//! # fn describe() -> Result<avp::trajectory::AgentDescriptor, avp::agent_cli::BoxError> { todo!() }
//! # fn run(_: avp::Commission, _: avp::FileSink) -> Result<(), avp::agent_cli::BoxError> { todo!() }
//! fn main() -> std::process::ExitCode {
//!     avp::agent_cli::main(describe, run)
//! }
//! ```
//!
//! `run` returns `Ok` once the trajectory is closed with `agent_stopped`,
//! including runs that end in an expected failure (a fail-fast Commission
//! check, a provider auth or rate-limit error, a refusal); return `Err` only
//! for a crash, after recording `error_occurred` and `agent_stopped`. It exits
//! non-zero with the error on stderr.
//!
//! Async harnesses block on their runtime inside the closures. `--built-in` is
//! the conformance fixture of the agent's pretend defaults: its `system_prompt`
//! and `prompt` seed the Commission when it leaves them unset (the Commission
//! wins). Tool / MCP / subagent built-ins are not simulated. Matches the Python
//! `avp.agent_cli`.

use std::collections::HashMap;
use std::path::Path;
use std::process::ExitCode;

use serde::Serialize;
use serde_json::Value;

use crate::sink::FileSink;
use crate::Commission;

pub type BoxError = Box<dyn std::error::Error + Send + Sync>;

const USAGE: &str = "usage: <agent> ping --out <path>
       <agent> describe [--out <path>]
       <agent> run --commission <json|path> [--built-in <json|path>] --out <path>";

/// Parse `std::env::args` and dispatch. Errors print to stderr; a usage error
/// exits 2, a failed command exits 1.
pub fn main<T, D, R>(describe: D, run: R) -> ExitCode
where
    T: Serialize,
    D: FnOnce() -> Result<T, BoxError>,
    R: FnOnce(Commission, FileSink) -> Result<(), BoxError>,
{
    let args: Vec<String> = std::env::args().skip(1).collect();
    match dispatch(&args, describe, run) {
        Ok(()) => ExitCode::SUCCESS,
        Err(CliError::Usage(msg)) => {
            eprintln!("error: {msg}\n{USAGE}");
            ExitCode::from(2)
        }
        Err(CliError::Failed(e)) => {
            eprintln!("error: {e}");
            ExitCode::FAILURE
        }
    }
}

#[derive(Debug)]
pub enum CliError {
    Usage(String),
    Failed(BoxError),
}

impl<E: Into<BoxError>> From<E> for CliError {
    fn from(e: E) -> Self {
        CliError::Failed(e.into())
    }
}

/// [`main`] over explicit arguments (without the program name).
pub fn dispatch<T, D, R>(args: &[String], describe: D, run: R) -> Result<(), CliError>
where
    T: Serialize,
    D: FnOnce() -> Result<T, BoxError>,
    R: FnOnce(Commission, FileSink) -> Result<(), BoxError>,
{
    let (cmd, rest) = args
        .split_first()
        .ok_or_else(|| CliError::Usage("missing command".into()))?;
    let flags = parse_flags(rest)?;
    let get = |k: &str| flags.get(k).map(String::as_str);
    let need = |k: &str| get(k).ok_or_else(|| CliError::Usage(format!("{cmd} needs --{k}")));
    match cmd.as_str() {
        "ping" => {
            std::fs::write(need("out")?, "{\"type\":\"pong\"}\n")?;
            Ok(())
        }
        "describe" => {
            let text = serde_json::to_string_pretty(&describe()?)?;
            match get("out") {
                Some(path) => std::fs::write(path, format!("{text}\n"))?,
                None => println!("{text}"),
            }
            Ok(())
        }
        "run" => {
            let mut commission: Commission =
                serde_json::from_value(read_json_arg(need("commission")?)?)?;
            if let Some(built_in) = get("built-in") {
                apply_built_in(&mut commission, &read_json_arg(built_in)?);
            }
            let sink = FileSink::create(need("out")?)?;
            run(commission, sink)?;
            Ok(())
        }
        other => Err(CliError::Usage(format!("unknown command {other:?}"))),
    }
}

fn parse_flags(rest: &[String]) -> Result<HashMap<String, String>, CliError> {
    let mut flags = HashMap::new();
    let mut it = rest.iter();
    while let Some(arg) = it.next() {
        let Some(name) = arg.strip_prefix("--") else {
            return Err(CliError::Usage(format!("unexpected argument {arg:?}")));
        };
        let (key, value) = match name.split_once('=') {
            Some((k, v)) => (k.to_string(), v.to_string()),
            None => {
                let v = it
                    .next()
                    .ok_or_else(|| CliError::Usage(format!("--{name} needs a value")))?;
                (name.to_string(), v.clone())
            }
        };
        flags.insert(key, value);
    }
    Ok(flags)
}

/// Inline JSON (a leading `{` / `[`) or a path to a JSON file.
pub fn read_json_arg(value: &str) -> Result<Value, BoxError> {
    let trimmed = value.trim_start();
    if trimmed.starts_with('{') || trimmed.starts_with('[') {
        Ok(serde_json::from_str(value)?)
    } else {
        Ok(serde_json::from_str(&std::fs::read_to_string(Path::new(
            value,
        ))?)?)
    }
}

/// Seed `system_prompt` / `prompt` from the fixture where the Commission
/// leaves them unset.
pub fn apply_built_in(commission: &mut Commission, built_in: &Value) {
    if commission.system_prompt.is_none() {
        if let Some(s) = built_in.get("system_prompt").and_then(Value::as_str) {
            commission.system_prompt = Some(s.to_string());
        }
    }
    if commission.prompt.is_none() {
        if let Some(s) = built_in.get("prompt").and_then(Value::as_str) {
            commission.prompt = Some(s.to_string());
        }
    }
}
