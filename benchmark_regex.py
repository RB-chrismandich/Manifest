import timeit
import re

def run_inline(agent_results):
    for agent_name, result in agent_results.items():
        if result.get("status") != "complete": continue
        out = result.get("output", "").lower()

        secret_patterns = [
            r'api[_-]?key\s*=\s*["\'][^"\']+["\']',
            r'password\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
        ]
        sql_patterns = [r'execute\s*\(\s*["\'].*\+', r'query\s*\(\s*["\'].*\+']
        cmd_patterns = [
            r"exec\s*\(.*user.*\)",
            r"system\s*\(.*input.*\)",
            r"shell_exec",
        ]

        for pattern in secret_patterns:
            if re.search(pattern, out, re.IGNORECASE): pass
        for pattern in sql_patterns:
            if re.search(pattern, out, re.IGNORECASE): pass
        for pattern in cmd_patterns:
            if re.search(pattern, out, re.IGNORECASE): pass
        if re.search(r"except\s*:", out): pass


SECRET_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r'api[_-]?key\s*=\s*["\'][^"\']+["\']',
    r'password\s*=\s*["\'][^"\']+["\']',
    r'secret\s*=\s*["\'][^"\']+["\']',
    r'token\s*=\s*["\'][^"\']+["\']',
]]
SQL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r'execute\s*\(\s*["\'].*\+', r'query\s*\(\s*["\'].*\+'
]]
CMD_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r"exec\s*\(.*user.*\)",
    r"system\s*\(.*input.*\)",
    r"shell_exec",
]]
BARE_EXCEPT_PATTERN = re.compile(r"except\s*:")

def run_precompiled(agent_results):
    for agent_name, result in agent_results.items():
        if result.get("status") != "complete": continue
        out = result.get("output", "").lower()

        for pattern in SECRET_PATTERNS:
            if pattern.search(out): pass
        for pattern in SQL_PATTERNS:
            if pattern.search(out): pass
        for pattern in CMD_PATTERNS:
            if pattern.search(out): pass
        if BARE_EXCEPT_PATTERN.search(out): pass

output = "Here is some code:\napi_key = '12345'\nexecute('SELECT * FROM users WHERE id=' + user_id)\nexcept:\n    pass" * 100
agent_results = {
    'agent1': {'status': 'complete', 'output': output},
    'agent2': {'status': 'complete', 'output': output},
    'agent3': {'status': 'complete', 'output': output}
}

try:
    inline_time = timeit.timeit("run_inline(agent_results)", globals=globals(), number=1000)
    precompiled_time = timeit.timeit("run_precompiled(agent_results)", globals=globals(), number=1000)

    print(f"Inline regex time: {inline_time:.4f}s")
    print(f"Pre-compiled regex time: {precompiled_time:.4f}s")
    print(f"Improvement: {(inline_time - precompiled_time) / inline_time * 100:.2f}%")
except Exception as e:
    import traceback
    traceback.print_exc()
