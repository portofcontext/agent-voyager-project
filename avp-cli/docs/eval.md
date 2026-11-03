# Eval files

An eval file, `<name>.eval.json`, runs Commissions on a dataset and scores each
run. Each item in the dataset fills placeholders in the Commission, so one
Commission makes a different run for every item.

```json
{
  "eval_version": "0.1",
  "name": "capitals",
  "agents": "pd",
  "commission": {
    "avp_version": "0.1",
    "model": { "provider": "anthropic", "id": "claude-haiku-4-5" },
    "prompt": "Name the city in: {item.text}"
  },
  "dataset": [
    { "id": "paris", "text": "Paris is the capital of France.", "answer": "Paris" },
    { "id": "tokyo", "text": "Tokyo is the capital of Japan.", "answer": "Tokyo" }
  ],
  "scorer": { "name": "match", "expected": "{item.answer}" }
}
```

The `paris` item's run gets the prompt `Name the city in: Paris is the capital
of France.`

## Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `eval_version` | `"0.1"` | Yes | The eval format the file follows. |
| `name` | name | Yes | The eval's name. |
| `agents` | name or list of names | No | Installed agents to run. `--agent` replaces it; one of the two is required. |
| `commission` | Commission, or a list of them | Yes | The Commission to run, or a list of them to compare. |
| `dataset` | list of items | Yes | The items, at least one. |
| `scorer` | object | Yes | How each run is scored. See [Scorers](#scorers). |

A name uses lowercase letters, digits, `.`, `_`, and `-`, and starts with a
letter or digit.

Every Commission runs on every agent for every item.

A Commission is given as one of:

- A path to its JSON file, relative to the eval file. A string with a `/`
  or ending in `.json` is a path.
- An inline Commission object.
- ⬜ A saved Commission's name. Saved Commissions aren't supported yet.

Each Commission has a name, used on the scoreboard and in its runs' IDs: its
file's name without `.json`, its saved name, or `inline-1`, `inline-2`, and so
on by its place in the list. Two Commissions can't have the same name, and a
file's name must be a valid name.

A Commission file can leave out `run_id` and `supervisor`. avp sets them for
each run and replaces any value the file gives.

## Items

An item is an object with an `id` and any other fields. The `id` names the
item's runs and its row on the scoreboard, so it must be unique and stay the
same when the dataset changes. It is a name.

## Placeholders

A placeholder names a field by its namespace and a dotted path, such as
`item.text` or `item.answer.city`. There are two forms.

**In a string**, `{item.path}` is replaced by the field's value as text:

```json
"prompt": "Read /data/{item.id}.pdf and answer: {item.question}"
```

The value must be a string, a number, or `true` or `false`. An object, an
array, or `null` is an error; insert it whole instead.

**As a whole value**, an object whose only key is `$item` is replaced by the
field's value, of any type:

```json
"output_schema": { "$item": "schema" }
```

With the item `{"id": "a", "schema": {"type": "object"}}`, the run's
Commission has `"output_schema": {"type": "object"}`.

The rules:

- Placeholders are filled in string values only, never in object keys.
- Text that is not `{item.…}` or `{run.…}`, such as JSON in a prompt, stays as
  written.
- Filled text is not read again, so a value containing `{item.x}` stays as it is.
- There is no escape: a Commission can't contain the literal text `{item.x}`.
- A placeholder naming a field the item doesn't have is an error.

### Namespaces

| Namespace | Where | Holds |
|---|---|---|
| `item` | Commissions and the scorer | The item's fields, `id` included. |
| `run` | The scorer | The finished run, as in [the scorer's input](#input): `run.output`, `run.reason`, and the rest. `run.item` is the same as `item`. |

`{run.…}` and `{"$run": …}` in a Commission are errors, since the run hasn't
happened yet.

## Checking

avp fills every Commission for every item and validates the result before any
run starts, and reports every error it finds with where it is:

```text
item paris, commission.inline-1.prompt: item has no field 'country'
item tokyo, commission.inline-1.model.id: Input should be a valid string
```

## Scorers

⬜ Not built yet.

A scorer takes one finished run, with its item, and returns a score. Every
scorer takes the same [input](#input) and returns the same [score](#score).
`name` picks the scorer, and its other fields configure it:

| `name` | Scores by |
|---|---|
| `match` | Comparing the run's text output with an expected string. |
| `structured-match` | Comparing the run's structured output with an expected object, key by key. |
| `command` | Running a command of your own. |
| ⬜ `llm-judge` | Asking a model whether the output is correct. |

Placeholders in a scorer's fields are filled for each run, from `item` and
`run`.

### Input

| Field | Type | Description |
|---|---|---|
| `run.id` | string | The run's `run_id`. |
| `run.agent` | name | The agent that ran. |
| `run.commission` | name | The Commission's name. |
| `run.exit_code` | integer | The agent command's exit code. |
| `run.trajectory` | list of Trajectory events | The run's valid events, in order. |
| `run.invalid_trajectory` | list of objects | The Trajectory's lines that aren't valid events, left out of `run.trajectory`: each `{"line": 2, "error": "isn't JSON"}`, with `line` counted from 1. Events of a type avp doesn't know are skipped, not listed. |
| `run.output` | any | `agent_stopped`'s `output`, or `null`. |
| `run.reason` | string or `null` | `agent_stopped`'s `reason`, or `null` when there is no `agent_stopped`. |
| `run.item` | object | The item, as in the dataset. |
| `config` | object | For a `command` scorer, its `config` field. For a built-in scorer, its fields other than `name`. Placeholders in it are filled. |

`run` is what avp passes, and `config` is what the eval file passes.

### Score

| Field | Type | Description |
|---|---|---|
| `value` | number | From 0 to 1. Partial credit is allowed. |
| `passed` | boolean | Whether the run passed. |
| `reasons` | list of strings | Why it lost points, shown on the scoreboard. Empty when it passed. |

The scoreboard reports both accuracy, the mean `value`, and pass rate, the
share of runs that passed.

A scorer that fails, by raising an error or, for a command, exiting with a
non-zero code, gives no score. The run is left out of accuracy and pass rate
and listed apart as "scorer failed", with the traceback or the command's
stderr saved in the run's directory.

### `match`

```json
"scorer": { "name": "match", "expected": "{item.answer}" }
```

| Field | Type | Required | Description |
|---|---|---|---|
| `expected` | string | Yes | The text `run.output` should be. |

A run scores 1 and passes when `run.output` is a string equal to `expected`
after trimming and ignoring case, and 0 otherwise. An output that isn't a
string fails; avp doesn't parse it as JSON.

### `structured-match`

```json
"scorer": { "name": "structured-match", "expected": { "$item": "answer" }, "threshold": 1 }
```

| Field | Type | Required | Description |
|---|---|---|---|
| `expected` | object | Yes | The keys and values `run.output` should have. |
| `threshold` | number | No | The `value` a run needs to pass, from 0 to 1. Default 1. |

`run.output` must be an object, normally from the Commission's
`output_schema`. `value` is the share of `expected`'s keys whose value in
`run.output` is equal: strings as [`match`](#match) compares them, numbers
within 0.000001, and nested objects and arrays as a whole, with the same rules
inside them. Keys that `expected` doesn't have are ignored.

### `command`

| Field | Type | Required | Description |
|---|---|---|---|
| `command` | list of strings | Yes | The command and its arguments. Placeholders in them are filled. |
| `config` | object | No | Anything the command needs, passed to it as `config`. Placeholders in it are filled. Default `{}`. |

avp runs the command once for each run, in the eval file's directory, writes
the [input](#input) to its stdin as JSON, and reads the [score](#score) from its
stdout as JSON. When the command exits with a non-zero code or prints something
other than a score, the scorer failed.

The command runs on your machine, not in a sandbox, with your environment.
Running an eval file runs its scorer's command, so run only eval files you
trust.

A command scorer in Python, `scorers/words.py`, next to the eval file. It
scores the share of the item's `words` in the output, and fails a run that
called more tools than `max_tool_calls`. The comment at the top lets `uv run`
install the AVP SDK for it, whose types parse the Trajectory:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["agent-voyager-project"]
# ///
import json
import sys

from avp.trajectory import ToolInvokedEvent, parse_trajectory_event

data = json.load(sys.stdin)
run, config = data["run"], data["config"]

events = [parse_trajectory_event(e) for e in run["trajectory"]]
tool_calls = sum(isinstance(e, ToolInvokedEvent) for e in events)
output = str(run["output"] or "").lower()
missing = [w for w in run["item"]["words"] if w.lower() not in output]

reasons = [f"missing {w!r}" for w in missing]
if tool_calls > config["max_tool_calls"]:
    reasons.append(f"{tool_calls} tool calls, more than {config['max_tool_calls']}")
value = 1 - len(missing) / len(run["item"]["words"])
json.dump({"value": value, "passed": not reasons, "reasons": reasons}, sys.stdout)
```

The eval file's scorer and an item:

```json
"scorer": {
  "name": "command",
  "command": ["uv", "run", "scorers/words.py"],
  "config": { "max_tool_calls": 3 }
},
"dataset": [{ "id": "paris", "text": "...", "words": ["Paris", "France"] }]
```
