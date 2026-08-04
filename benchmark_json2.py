import json
import timeit

line = '{"ts": "123", "event": "foo", "run_id": "test_123"}\n'

def with_loads():
    for _ in range(2500):
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                continue
            rid = obj.get("run_id")
        except:
            pass

def fast_str_check():
    for _ in range(2500):
        if '"run_id"' not in line:
            pass
        else:
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    continue
                rid = obj.get("run_id")
            except:
                pass

print(f"With loads: {timeit.timeit(with_loads, number=100)}")
print(f"Fast check: {timeit.timeit(fast_str_check, number=100)}")
