---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
I run `docker run --rm -v $PWD/config:/cfg myapp:2.3 myapp validate` and it exits 0 with no output. Can I treat the config as valid and deploy?
