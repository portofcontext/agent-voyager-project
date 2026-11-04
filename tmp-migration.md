# v0.1 release work

The specs, Python and TypeScript SDKs, eight retained adapters, and new CLI are
on `spec-v0.1-cleanup`. The retired implementations, workspace, template, and
release machinery have been removed. Each maintained project owns its lockfile.

Remaining work is tracked in GitHub:

- #100: supervisor-owned Commission fields.
- #109 and #110: LLM judge and structured-match scorers.
- #112: Commission commands and saved Commissions.
- #113: TUI.
- #116: beta SDK and CLI publication.
- #114: agents consume published SDKs.
- #117: built-in agent installation without a checkout.

Review conformance coverage by rule with `avp conformance list`. Review the
TypeScript SDK and adapters before release, run the native checks, and remove
temporary planning files before merging the release branch into main.
