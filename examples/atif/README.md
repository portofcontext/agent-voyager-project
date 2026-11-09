# Use AVP runs with Harbor

The run's `trajectory.json` is already ATIF. This example uses Harbor's own
models, trace extractor, and viewer. It does not import an AVP converter.

Create a separate environment with the tested Harbor revision:

```sh
uv venv /tmp/avp-harbor
uv pip install --python /tmp/avp-harbor/bin/python \
  'harbor @ git+https://github.com/harbor-framework/harbor.git@9c7a39b991d7e2205019f6be0598cbd22d84bfc3'
/tmp/avp-harbor/bin/python examples/atif/consume.py path/to/trajectory.json \
  --jobs /tmp/avp-harbor-jobs --conversations /tmp/conversations.json
/tmp/avp-harbor/bin/harbor view /tmp/avp-harbor-jobs --jobs
```

`--jobs` creates a new directory with Harbor's job/trial metadata and copies the
original document byte for byte, plus its image assets. It never reruns the agent
or claims a verifier reward. `--conversations` invokes Harbor's text extractor
directly and preserves its behavior: episodes end at each root agent response,
and images are rejected. Omit that option for multimodal runs. Child trajectories
remain available in the original document; extracting their training episodes
is a separate choice for the dataset consumer.

Run `scripts/test-atif-ecosystem.py` with this same Python to check a Recorder
fixture against the independent Harbor model, trace extractor, viewer API,
and job scanner. AVP's ordinary `make check` uses the pinned schema and shared semantic
fixtures without installing Harbor or making model calls.
