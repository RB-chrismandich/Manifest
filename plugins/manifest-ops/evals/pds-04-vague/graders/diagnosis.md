---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It says to first confirm a real stall by comparing a progress proxy (output size, newest cache-file mtime, item counter) across two checks a minute or two apart.
2. It says to read the process's state and CPU (e.g. `ps -o pid,stat,%cpu,etime`) and classify: R/~100% CPU = CPU-bound; S/0% CPU = blocked on I/O (check sockets with lsof).
3. It says to fix the measured cause rather than guessing, and to make sure partial work is cached so a restart resumes.
