---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It recommends a probe that doesn't need curl/wget: the image's stdlib HTTP client (e.g. `python -c "import urllib.request; print(urllib.request.urlopen('http://api:8000/health').read())"`).
2. It runs the probe from a throwaway `docker run --rm --network shop_internal ...` container (reusing the service's image or python slim) addressing `api:8000`, or explains this as the approach alongside exec.
3. It prints the response body to confirm the payload, not merely exit status.
