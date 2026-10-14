//! Agent entrypoint (`ping` / `describe` / `run`), via the stock `avp::agent_cli`.

fn main() -> std::process::ExitCode {
    avp::agent_cli::main(
        || Ok(avp_agent_template::agent::describe()),
        |commission, sink| Ok(avp_agent_template::agent::run(&commission, sink)?),
    )
}
