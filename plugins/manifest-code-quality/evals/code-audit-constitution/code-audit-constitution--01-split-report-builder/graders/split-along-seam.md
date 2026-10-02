---
type: llm
focus: {source: file, path: report_builder.py}
weight: 1
---
The original function did three separable jobs in sequence: validate/clean the input rows, compute aggregates (total/average/top-5/etc.), and format the text report. Score 1 only if the resulting file replaces the single long function with at least two extracted helper functions along that seam (e.g. one for cleaning/validating rows, one for computing aggregates, one for formatting output) called from a `build_report` function that remains the public entry point, AND no single function in the file is anywhere near 60+ lines any more (each piece should be well under it). Score 0 if it is still one large function, or if the split is arbitrary (e.g. cut at the halfway line without following the validate/aggregate/format seam), or if `build_report` was renamed/removed instead of kept as the public entry point.
