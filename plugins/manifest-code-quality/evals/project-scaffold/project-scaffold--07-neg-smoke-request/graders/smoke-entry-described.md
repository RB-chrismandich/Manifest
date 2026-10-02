---
type: llm
weight: 1
---
Score 1 only if the answer describes a concrete smoke-test entry for the `billing` app in the Lite tier that sends `POST /api/login` and expects HTTP 200 (e.g. a smoke-catalog YAML entry with the method, path and expected status), rather than scaffolding a new project (lint configs, test directories, pre-commit, CI templates). Score 0 if it proposes project scaffolding instead, or gives no concrete smoke-test definition.
