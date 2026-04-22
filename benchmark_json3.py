import timeit
import json

synthesis_text = "Here is some text\n```json\n{\"foo\": \"bar\", \"baz\": 123}\n```\nMore text"

def original():
    import re
    json_match = re.search(r"```json\s*\n(.*?)\n```", synthesis_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))

def optimized():
    start_idx = synthesis_text.find("```json\n")
    if start_idx != -1:
        start_idx += 8
        end_idx = synthesis_text.find("\n```", start_idx)
        if end_idx != -1:
            return json.loads(synthesis_text[start_idx:end_idx])

orig_time = timeit.timeit("original()", globals=globals(), number=100000)
opt_time = timeit.timeit("optimized()", globals=globals(), number=100000)

print(f"Original regex time: {orig_time:.4f}s")
print(f"Optimized string split time: {opt_time:.4f}s")
print(f"Improvement: {(orig_time - opt_time) / orig_time * 100:.2f}%")
