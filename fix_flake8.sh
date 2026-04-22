#!/bin/bash
sed -i '/_keywords = security_criteria/d' configs/claude/scripts/parallel_agent.py
sed -i '/_patterns = bug_criteria/d' configs/claude/scripts/parallel_agent.py
sed -i '/_task = progress.add_task/d' configs/claude/scripts/parallel_agent.py
