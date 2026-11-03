//! Agent fixture for the command line subprocess tests.
use std::{sync::atomic::Ordering, time::Duration};

use avp::{
    agent_cli,
    descriptor::AgentDescriptor,
    recorder::{Recorder, ResponseOptions},
    trajectory::StopReason,
    utils::run_plan::plan_run,
};
use serde_json::json;

fn describe() -> avp::Result<AgentDescriptor> {
    Ok(serde_json::from_value(
        json!({"avp_version": "0.1", "agent_name": "example", "agent_version": "0.1.0"}),
    )?)
}

fn main() {
    std::process::exit(agent_cli::main(
        |received, sink, interrupted| {
            let descriptor = describe()?;
            let mut rec = Recorder::new(sink);
            let Some(commission) = rec.begin(received, descriptor.clone())? else {
                return Ok(());
            };
            rec.start(plan_run(&commission, &descriptor).started, None)?;
            if commission.prompt == "crash" {
                return Err("example crash".into());
            }
            while commission.prompt == "wait" && !interrupted.load(Ordering::SeqCst) {
                std::thread::sleep(Duration::from_millis(10));
            }
            if interrupted.load(Ordering::SeqCst) {
                return rec.stop(StopReason::Interrupted, json!(null));
            }
            rec.response(
                serde_json::from_value(json!([{"type": "text", "text": "Hello."}]))?,
                ResponseOptions::default(),
            )?;
            rec.stop(StopReason::Converged, json!("Hello."))
        },
        describe,
        None,
    ));
}
