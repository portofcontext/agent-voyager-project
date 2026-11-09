# Upstream ATIF schema

`schema.json` is generated from Harbor's `Trajectory.model_json_schema()` at
commit `9c7a39b991d7e2205019f6be0598cbd22d84bfc3`, whose default is ATIF-v1.8.
The schema's `$schema` and `$comment` record its dialect and provenance.
It is test data, not an AVP wire schema or an SDK runtime dependency.

Source: [Harbor trajectory models](https://github.com/harbor-framework/harbor/tree/9c7a39b991d7e2205019f6be0598cbd22d84bfc3/src/harbor/models/trajectories).
Harbor's Apache-2.0 license is included as `LICENSE.harbor`.

After installing that Harbor revision as described in the
[export guide](../../docs/atif.md#validation), regenerate from the repository root:

```sh
avp-sdk/python/.venv/bin/python - <<'PY'
import json
from pathlib import Path
from harbor.models.trajectories import Trajectory

schema = Trajectory.model_json_schema()
schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
schema['$comment'] = 'Generated from harbor-framework/harbor 9c7a39b991d7e2205019f6be0598cbd22d84bfc3, Trajectory.model_json_schema(). Apache-2.0; see LICENSE.harbor. Do not edit by hand.'
Path('avp-sdk/testdata/atif/schema.json').write_text(json.dumps(schema, indent=2) + '\n')
PY
```

When updating, change the pinned revision and license together, regenerate the
schema, and rerun the ATIF tests and upstream validator. Do not edit schema
fields by hand. The offline tests supplement the schema with checks for call
references and sequential IDs, which Harbor implements as Pydantic validators.
