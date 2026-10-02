---
type: regex
target: {source: file, path: tally/store.py}
match: contains
---
^"""SQLite persistence for events\."""\nimport sqlite3\n\n\ndef save\(records, db_path\):\n    (?:"""|''')\s*[^\s"'][\s\S]*?(?:"""|''')\n    con = sqlite3\.connect\(db_path\)\n    con\.execute\("CREATE TABLE IF NOT EXISTS events \(event TEXT, ts TEXT\)"\)\n    con\.executemany\("INSERT INTO events VALUES \(:event, :ts\)", records\)\n    con\.commit\(\)\n\n\ndef counts\(db_path\):\n    con = sqlite3\.connect\(db_path\)\n    return dict\(con\.execute\("SELECT event, COUNT\(\*\) FROM events GROUP BY event"\)\)\n\n*$
