# Run plan test cases

Every SDK's run plan function passes these cases. Each file gives a
`commission` and a `descriptor`, and the `plan` the function must return:
`started`, the `agent_started` data for the run, and `turned_off`.

Compare the plan as JSON, leaving out fields that are absent or null. Each
case's Commission passes the Commission checks.
