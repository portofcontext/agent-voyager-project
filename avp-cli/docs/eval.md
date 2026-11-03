# Eval files

An eval file, `<name>.eval.json`, runs Commissions on a dataset and scores each
run. Each item in the dataset fills placeholders in the Commission, so one
Commission makes a different run for every item.

```json
{
  "eval_version": "0.1",
  "name": "capitals",
  "agents": "pd",
  "commission": "capitals.json",
  "dataset": [
    { "id": "paris", "text": "Paris is the capital of France.", "answer": { "city": "Paris" } },
    { "id": "tokyo", "text": "Tokyo is the capital of Japan.", "answer": { "city": "Tokyo" } }
  ],
  "scorer": {}
}
```

`capitals.json`, next to the eval file:

```json
{
  "avp_version": "0.1",
  "model": { "provider": "anthropic", "id": "claude-haiku-4-5" },
  "prompt": "Name the city in: {item.text}"
}
```

The `paris` item's run gets the prompt `Name the city in: Paris is the capital
of France.`

## Fields

| Field | Required | Description |
|---|---|---|
| `eval_version` | Yes | `"0.1"`. |
| `name` | Yes | The eval's name. |
| `agents` | No | An installed agent's name, or a list of them. `--agent` replaces it; one of the two is required. |
| `commission` | Yes | The Commission to run, or a list of them to compare. |
| `dataset` | Yes | The items, at least one. |
| `scorer` | Yes | How each run is scored. ⬜ Its shape comes with the scorers. |

Every Commission runs on every agent for every item.

A Commission is given as one of:

- A path to its JSON file, relative to the eval file. A string with a `/`
  or ending in `.json` is a path.
- An inline Commission object.
- ⬜ A saved Commission's name. Saved Commissions aren't supported yet.

Each Commission has a name, used on the scoreboard and in its runs' IDs: its
file's name without `.json`, its saved name, or `inline-1`, `inline-2`, and so
on by its place in the list. Two Commissions can't have the same name, and a
file's name must be a valid name: lowercase letters, digits, `.`, `_`, and
`-`.

A Commission file can leave out `run_id` and `supervisor`. avp sets them for
each run and replaces any value the file gives.

## Items

An item is an object with an `id` and any other fields. The `id` names the
item's runs and its row on the scoreboard, so it must be unique and stay the
same when the dataset changes. It must be a valid name, as above.

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
| `run` | ⬜ The scorer | The finished run: `run.response`, the agent's final text, and `run.output`, its structured output or `null`. |

`{run.…}` and `{"$run": …}` in a Commission are errors, since the run hasn't
happened yet.

## Checking

avp fills every Commission for every item and validates the result before any
run starts, and reports every error it finds with where it is:

```text
item paris, commission.capitals.prompt: item has no field 'country'
item tokyo, commission.capitals.model.id: Input should be a valid string
```
