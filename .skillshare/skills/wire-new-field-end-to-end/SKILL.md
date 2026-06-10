---
name: wire-new-field-end-to-end
description: Use when adding a field to a data model, snapshot row, or context object that a downstream component (LLM prompt, API response, report) is supposed to consume — verifies the population site exists, not just the schema.
---
# Wire a New Data Field End-to-End

A recurring, silent bug: a new field is added to a schema/dataclass and to the
consumer that reads it, but nothing ever *writes* it at the join point — so the
consumer always sees `None`/default. This gap shipped twice (a backlog ratio and
a squeeze score both reached the LLM as `None`) before a cross-artifact analysis
caught it. Run this trace for every enrichment field.

## Steps

1. **Name the three sites.** For the new field, identify:
   - **Schema/storage** — column, migration, or dataclass field (where it lives).
   - **Producer** — the code that computes the value and persists/attaches it.
   - **Consumer** — the code that reads it (prompt builder, API serializer, report).
2. **Grep for the field name across all three.** If it appears only in schema +
   consumer but not in a producer that runs in the real path, that's the bug.
   Pay special attention to context objects assembled in a *different* module than
   where the field was defined (e.g. a pipeline that builds the context from
   upstream data and never reads the enriched snapshot row).
3. **Confirm the producer runs in the hot path**, not just in tests. A test that
   constructs the object with the field set proves nothing about production wiring.
4. **For frozen/immutable context objects**, the producer must use a copy-with
   (`dataclasses.replace`, spread, builder) — direct assignment silently fails or
   raises. Verify the replace call actually includes the new field.
5. **Add one integration assertion** that runs the real producer path and asserts
   the consumer sees a non-default value — distinct from the unit test that sets
   the field directly.
6. **When a spec/plan/tasks analysis lists a "coverage gap" for a field**, treat
   it as this bug until proven otherwise; add the missing population task.
