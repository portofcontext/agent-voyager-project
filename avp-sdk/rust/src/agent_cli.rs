//! Provisional file transport for an agent's ping, describe, and run commands.

use std::{
    ffi::OsString,
    fs::{self, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
};

use clap::{Parser, Subcommand};
use serde_json::Value;

use crate::{Result, descriptor::AgentDescriptor, recorder::EventSink, trajectory::Event};

#[derive(Parser)]
#[command(
    about = "An AVP agent. Not part of the AVP spec.",
    arg_required_else_help = true
)]
struct Args {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Check that the agent runs, without loading it.
    Ping {
        #[arg(long)]
        out: Option<String>,
    },
    /// Write the agent's Descriptor.
    Describe {
        #[arg(long)]
        out: Option<String>,
    },
    /// Run a Commission and write its Trajectory as NDJSON.
    Run {
        #[arg(long)]
        commission: String,
        #[arg(long)]
        out: String,
    },
}

pub struct NdjsonSink {
    out: Option<PathBuf>,
}

impl NdjsonSink {
    pub fn new(out: Option<&Path>) -> Result<Self> {
        if let Some(path) = out {
            fs::write(path, "")?;
        }
        Ok(Self {
            out: out.map(Path::to_path_buf),
        })
    }
}

impl EventSink for NdjsonSink {
    fn write(&mut self, event: Event) -> Result<()> {
        let line = format!("{}\n", serde_json::to_string(&event)?);
        if let Some(path) = &self.out {
            OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)?
                .write_all(line.as_bytes())?;
        } else {
            let mut stdout = io::stdout().lock();
            stdout.write_all(line.as_bytes())?;
            stdout.flush()?;
        }
        Ok(())
    }
}

pub fn read_commission(value: &str) -> Result<Value> {
    let text = if value.trim_start().starts_with('{') {
        value.to_string()
    } else {
        fs::read_to_string(value)?
    };
    Ok(serde_json::from_str(&text).unwrap_or(Value::String(text)))
}

/// The run callback observes the interruption flag, ends its Trajectory, and returns.
/// Return 0 for a complete run (including refusal), 130 for SIGINT/SIGTERM, or 1 for a crash.
pub fn main(
    run: impl FnOnce(Value, NdjsonSink, Arc<AtomicBool>) -> Result<()>,
    describe: impl FnOnce() -> Result<AgentDescriptor>,
    argv: Option<Vec<OsString>>,
) -> i32 {
    let args = match Args::try_parse_from(argv.unwrap_or_else(|| std::env::args_os().collect())) {
        Ok(args) => args,
        Err(error) => {
            let _ = error.print();
            return error.exit_code();
        }
    };
    let interrupted = Arc::new(AtomicBool::new(false));
    let result = (|| -> Result<()> {
        match args.command {
            Command::Ping { out } => write(out.as_deref(), "{\"type\": \"pong\"}\n"),
            Command::Describe { out } => write(
                out.as_deref(),
                &format!("{}\n", serde_json::to_string_pretty(&describe()?)?),
            ),
            Command::Run { commission, out } => {
                let sink = NdjsonSink::new((out != "-").then(|| Path::new(&out)))?;
                let mut signals = Signals(Vec::new());
                for signal in [signal_hook::consts::SIGINT, signal_hook::consts::SIGTERM] {
                    signals
                        .0
                        .push(signal_hook::flag::register(signal, interrupted.clone())?);
                }
                run(read_commission(&commission)?, sink, interrupted.clone())
            }
        }
    })();
    if interrupted.load(Ordering::SeqCst) {
        return 130;
    }
    match result {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("{error}");
            1
        }
    }
}

fn write(out: Option<&str>, text: &str) -> Result<()> {
    match out {
        Some(path) => fs::write(path, text)?,
        None => io::stdout().write_all(text.as_bytes())?,
    }
    Ok(())
}

struct Signals(Vec<signal_hook::SigId>);
impl Drop for Signals {
    fn drop(&mut self) {
        for id in self.0.drain(..) {
            signal_hook::low_level::unregister(id);
        }
    }
}
