## 2025-02-21 - Python Parsing Optimization
**Learning:** To improve performance when filtering large log files or line-delimited JSON data, calling `json.loads()` multiple times on the same line across different iterations is a significant bottleneck.
**Action:** Parse the JSON once per line during the initial pass and store the original line alongside the extracted data in a tuple or structure (e.g., `parsed_lines.append((ln, extracted_id))`) for subsequent O(1) checks.
