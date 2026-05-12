# AVP-RFC-NNNN: Short, descriptive title

<!-- Keep the title short, simple, descriptive. A good title is part of any review. -->

## Summary

<!--
One paragraph. What is this proposal? Should be readable by someone with no
prior context on the proposal. A glance at the title and Summary tells the
reader whether to keep going.
-->

## Motivation

<!--
Why are we doing this? What problem does it solve? What are the use cases?

Include concrete examples. Cite supervisor / agent / supervisor-framework
needs you've observed.
-->

### Goals

<!-- Bulleted list of measurable outcomes. -->

### Non-goals

<!-- What this proposal is explicitly NOT trying to do. Just as important. -->

## Proposal

<!--
The design. Include:
  - The wire shape (JSON examples, schema deltas)
  - The semantic rules (MUSTs / SHOULDs / MAYs)
  - Backwards compatibility and migration story
  - How it composes with the other specs

If the proposal touches multiple specs, organize by spec.
-->

### Wire format changes

<!-- New event types, new fields, schema deltas. Include JSON examples. -->

### Conformance impact

<!--
Does this proposal add MUST/SHOULD criteria? Which spec's conformance
section gains them? Are new conformance cases required?
-->

### Reference-implementation impact

<!--
What changes in:
  - python/avp/ (wire types + reference agent)
  - python/agents/avp-anthropic/
  - python/agents/avp-claude-agent-sdk/
  - Other bindings (Rust, TypeScript)
  - The conformance suite
-->

## Alternatives considered

<!--
Other designs you considered and why you chose this one. Reviewers will ask;
pre-empt the question.
-->

## Open questions

<!--
List unresolved questions for reviewers to chime in on. Use <<[UNRESOLVED]>>
inline if needed:

  <<[UNRESOLVED how do we handle the case where ...]>>
  Stuff that is being argued.
  <<[/UNRESOLVED]>>
-->

## Drawbacks

<!--
Real costs of this proposal. Not "this could fail" but "this makes X worse".
Forces honest weighing.
-->

## Implementation plan

<!--
If the proposal is `accepted` or beyond, what's the order of operations?
Which PRs land first? What can be split?
-->

## References

<!-- Links to related AVP-RFCs, upstream specs, prior art, issue discussions. -->
