import timeit
import json

def json_extract_regex():
    import re
    synthesis_text = "Here is some text\n```json\n{\"foo\": \"bar\", \"baz\": 123}\n```\nMore text"
    json_match = re.search(r"```json\s*\n(.*?)\n```", synthesis_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))

def json_extract_str():
    synthesis_text = "Here is some text\n```json\n{\"foo\": \"bar\", \"baz\": 123}\n```\nMore text"
    start_idx = synthesis_text.find("```json")
    if start_idx != -1:
        # Find next newline after ```json
        newline_idx = synthesis_text.find("\n", start_idx)
        if newline_idx != -1:
            end_idx = synthesis_text.find("```", newline_idx)
            if end_idx != -1:
                return json.loads(synthesis_text[newline_idx:end_idx].strip())
    return None

print(json_extract_regex())
print(json_extract_str())

try:
    regex_time = timeit.timeit("json_extract_regex()", globals=globals(), number=100000)
    str_time = timeit.timeit("json_extract_str()", globals=globals(), number=100000)

    print(f"Regex time: {regex_time:.4f}s")
    print(f"String methods time: {str_time:.4f}s")
    print(f"Improvement: {(regex_time - str_time) / regex_time * 100:.2f}%")
except Exception as e:
    import traceback
    traceback.print_exc()
