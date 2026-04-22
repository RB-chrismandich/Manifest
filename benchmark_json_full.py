import timeit
import json
import re

synthesis_text = "Here is some text\n```json\n{\"foo\": \"bar\", \"baz\": 123}\n```\nMore text" * 10

def parse_with_regex():
    json_match = re.search(r"```json\s*\n(.*?)\n```", synthesis_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))

def parse_with_string_methods():
    start_idx = synthesis_text.find("```json")
    if start_idx != -1:
        end_idx = synthesis_text.find("```", start_idx + 7)
        if end_idx != -1:
            return json.loads(synthesis_text[start_idx + 7:end_idx].strip())
    return None

regex_time = timeit.timeit("parse_with_regex()", globals=globals(), number=100000)
str_time = timeit.timeit("parse_with_string_methods()", globals=globals(), number=100000)

print(f"Regex time: {regex_time:.4f}s")
print(f"String methods time: {str_time:.4f}s")
print(f"Improvement: {(regex_time - str_time) / regex_time * 100:.2f}%")
