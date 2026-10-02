---
type: llm
focus: last_message
weight: 1
---
`slugify` has nothing to do with statistics — there is no stdev, z-score, normalization, or surge/ratio computation involved. Score 1 if the answer writes ordinary exact-value tests (e.g. `slugify("My Post") == "my-post"`, `slugify("  Hello World  ") == "hello-world"`) with no mention of variance, standard deviation, z-scores, or flat-fixture concerns. Score 0 if the answer brings up statistical fixture variance, zero-variance baselines, or anything from the z-score/stddev domain — none of it applies here.
