import timeit
import re

agent_results = {
    'agent1': {'status': 'complete', 'output': 'some output ' * 1000},
    'agent2': {'status': 'complete', 'output': 'api_key="123" ' + 'more ' * 1000},
    'agent3': {'status': 'complete', 'output': 'normal ' * 1000}
}

def original():
    issues = []
    for agent_name, result in agent_results.items():
        if result.get("status") != "complete": continue
        output = result.get("output", "").lower()

        secret_patterns = [
            r'api[_-]?key\s*=\s*["\'][^"\']+["\']',
            r'password\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
        ]
        for pattern in secret_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                issues.append(f"[{agent_name}] Potential hardcoded secret detected")
                break

        sql_patterns = [r'execute\s*\(\s*["\'].*\+', r'query\s*\(\s*["\'].*\+']
        for pattern in sql_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                issues.append(f"[{agent_name}] Potential SQL injection vulnerability")
                break

        cmd_patterns = [
            r"exec\s*\(.*user.*\)",
            r"system\s*\(.*input.*\)",
            r"shell_exec",
        ]
        for pattern in cmd_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                issues.append(f"[{agent_name}] Potential command injection vulnerability")
                break
    return issues

# Precompile patterns
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

def optimized():
    issues = []
    for agent_name, result in agent_results.items():
        if result.get("status") != "complete": continue
        output = result.get("output", "").lower()

        for pattern in SECRET_PATTERNS:
            if pattern.search(output):
                issues.append(f"[{agent_name}] Potential hardcoded secret detected")
                break

        for pattern in SQL_PATTERNS:
            if pattern.search(output):
                issues.append(f"[{agent_name}] Potential SQL injection vulnerability")
                break

        for pattern in CMD_PATTERNS:
            if pattern.search(output):
                issues.append(f"[{agent_name}] Potential command injection vulnerability")
                break
    return issues

print(original())
print(optimized())

orig_time = timeit.timeit("original()", globals=globals(), number=1000)
opt_time = timeit.timeit("optimized()", globals=globals(), number=1000)

print(f"Original time: {orig_time:.4f}s")
print(f"Optimized time: {opt_time:.4f}s")
print(f"Improvement: {(orig_time - opt_time) / orig_time * 100:.2f}%")
