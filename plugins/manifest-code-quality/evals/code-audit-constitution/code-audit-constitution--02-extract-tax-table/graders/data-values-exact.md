---
type: llm
focus: trace
weight: 1
---
Find the Write/Edit call(s) in the trace that create the extracted tax-rate data file (JSON/YAML/TOML/CSV). Score 1 only if that file's content contains ALL 20 of these state-to-rate mappings with numerically identical values (formatting such as 0.04 vs 0.0400 is fine), and no extra or missing states: "AL": 0.0400, "AK": 0.0000, "AZ": 0.0560, "AR": 0.0650, "CA": 0.0725, "CO": 0.0290, "CT": 0.0635, "DE": 0.0000, "FL": 0.0600, "GA": 0.0400, "HI": 0.0400, "ID": 0.0600, "IL": 0.0625, "IN": 0.0700, "IA": 0.0600, "KS": 0.0650, "KY": 0.0600, "LA": 0.0445, "ME": 0.0550, "MD": 0.0600. Score 0 if the data file is empty, incomplete, has any changed value, or cannot be found in the trace.
