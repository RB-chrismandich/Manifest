import timeit

setup = """
import yaml
try:
    from yaml import CSafeLoader
except ImportError:
    CSafeLoader = None

yaml_data = '''
rate_limits:
  claude:
    requests_per_minute: 60
    burst_size: 5
  gemini:
    requests_per_minute: 30
    burst_size: 3
  cursor:
    requests_per_minute: 100
    burst_size: 10
  codex:
    requests_per_minute: 100
    burst_size: 10
timeouts:
  default: 120
  review: 600
model_tiers:
  claude:
    haiku: claude-haiku-4-5-20251001
    sonnet: claude-sonnet-4-5-20250929
    opus: claude-opus-4-6
  gemini:
    flash: gemini-3-flash-preview
    pro: gemini-3-pro-preview
  codex:
    mini: o4-mini
    flash: o3
    advanced: o3-pro
credit_fallback:
  claude:
    - opus
    - sonnet
    - haiku
  cursor:
    - advanced
    - flash
    - mini
  gemini:
    - pro
    - flash
  codex:
    - advanced
    - flash
    - mini
validation:
  consensus_threshold:
    high: 0.8
    medium: 0.5
'''
"""

test_safe_load = """
yaml.safe_load(yaml_data)
"""

test_c_safe_load = """
if CSafeLoader:
    yaml.load(yaml_data, Loader=CSafeLoader)
else:
    yaml.safe_load(yaml_data)
"""

try:
    safe_load_time = timeit.timeit(test_safe_load, setup=setup, number=1000)
    c_safe_load_time = timeit.timeit(test_c_safe_load, setup=setup, number=1000)

    print(f"yaml.safe_load(): {safe_load_time:.4f}s")
    print(f"yaml.load(CSafeLoader): {c_safe_load_time:.4f}s")
    print(f"Improvement: {(safe_load_time - c_safe_load_time) / safe_load_time * 100:.2f}%")
except Exception as e:
    import traceback
    traceback.print_exc()
