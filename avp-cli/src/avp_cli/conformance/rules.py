"""The spec's rules for agents. A rule's ID is its spec and section number."""

RULES: dict[str, str] = {
    "commission.5.1": "The agent checks the Commission before the run starts",
    "commission.5.2": "Agent settings limit the built-in items",
    "commission.5.3": "Turned-off items are hidden and blocked",
    "commission.5.4": "Added items are used, or the run stops",
    "commission.5.5": "`system_prompt` replaces the agent's own",
    "commission.5.6": "The run uses `model`",
    "commission.5.7": "The agent checks its final output against `output_schema`",
    "commission.5.8": "Secrets stay out of the Trajectory",
    "commission.5.9": "Secrets come from the proxy or the environment",
    "agent-descriptor.4.1": "Names and IDs are unique",
    "agent-descriptor.4.2": "All built-in items, and only those, are listed",
    "agent-descriptor.4.3": "An absent list means none",
    "agent-descriptor.4.4": "Tools from MCP servers",
    "agent-descriptor.4.5": "Tools match what the model sees",
    "agent-descriptor.4.6": "The Descriptor is the same for every run of a version",
    "trajectory.4.1": "Produce valid ATIF",
    "trajectory.4.2": "Record effective inputs",
    "trajectory.4.3": "One agent step per model response",
    "trajectory.4.4": "Usage is per response",
    "trajectory.4.5": "Every tool call has a result",
    "trajectory.4.6": "Subagents",
    "trajectory.4.7": "Errors and stops",
}
"""agent-descriptor.4.7 only points to the Commission spec, so it isn't listed."""
