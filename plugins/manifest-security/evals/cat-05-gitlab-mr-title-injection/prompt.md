---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Review our GitLab CI for security issues:

```yaml
# .gitlab-ci.yml
workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
changelog:
  stage: test
  script:
    - echo "Entry: $CI_MERGE_REQUEST_TITLE" >> CHANGELOG.md
    - eval "notify --msg '$CI_MERGE_REQUEST_TITLE'"
    - curl -H "PRIVATE-TOKEN: $RELEASE_BOT_TOKEN" -X POST "$CI_API_V4_URL/projects/$CI_PROJECT_ID/releases"
```
We run pipelines for merge requests from forks in the parent project. RELEASE_BOT_TOKEN is not marked protected.
