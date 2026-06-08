<!-- configs/claude/prompts/skillclaw_evolve.md -->
# SkillClaw Distillation Prompt

You are distilling reusable Claude Code **skills** from real agent sessions.

A skill is a `SKILL.md` file with YAML frontmatter (`name`, `description`) and a
markdown body describing a repeatable procedure the agent should follow.

## Existing skill library (do NOT duplicate these names unless improving them)

{{LIBRARY}}

## Sessions (scrubbed, noise-truncated)

{{SESSIONS}}

## Your task

Identify recurring, generalizable workflows in these sessions that are NOT already
well covered by the existing library. For each, emit one skill.

Output ONLY a sequence of skill blocks in this exact fenced format, nothing else:

~~~skill name=<kebab-case-name>
---
name: <kebab-case-name>
description: <one line: when to use this skill>
---
# <Title>

<body: numbered, concrete steps>
~~~

If nothing rises to a reusable skill, output the single line: NO_SKILLS
