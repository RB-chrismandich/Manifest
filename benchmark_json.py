import timeit
import json

def parse_with_regex():
    import re
    synthesis_text = "Here is some text\n```json\n{\"foo\": \"bar\", \"baz\": 123}\n```\nMore text" * 10
    json_match = re.search(r"```json\s*\n(.*?)\n```", synthesis_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))

def parse_with_split():
    synthesis_text = "Here is some text\n```json\n{\"foo\": \"bar\", \"baz\": 123}\n```\nMore text" * 10
    # Find the start of the JSON block
    start_idx = synthesis_text.find("```json")
    if start_idx != -1:
        # Find the end of the JSON block
        start_idx += 7 # len("```json")
        end_idx = synthesis_text.find("```", start_idx)
        if end_idx != -1:
            json_str = synthesis_text[start_idx:end_idx].strip()
            return json.loads(json_str)
    return None

try:
    regex_time = timeit.timeit("parse_with_regex()", globals=globals(), number=10000)
    split_time = timeit.timeit("parse_with_split()", globals=globals(), number=10000)

    print(f"Regex time: {regex_time:.4f}s")
    print(f"Split time: {split_time:.4f}s")
    print(f"Improvement: {(regex_time - split_time) / regex_time * 100:.2f}%")
except Exception as e:
    import traceback
    traceback.print_exc()
