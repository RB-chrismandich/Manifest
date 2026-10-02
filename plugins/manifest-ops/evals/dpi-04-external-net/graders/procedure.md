---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It uses the network name `shared_internal` as-is (external networks are not project-prefixed), optionally confirming with `docker network ls`.
2. It runs a throwaway `--rm` container on that network to fetch the URL and print the body.
3. For DNS debugging it suggests an interactive container on the network (`docker run --rm -it --network shared_internal <image> sh`) with nslookup/getent or repeated probes.
