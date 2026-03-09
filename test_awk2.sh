#!/bin/bash
awk '
    BEGIN { section="" }
    /^[[:space:]]*claude:/ { section="claude" }
    /^[[:space:]]*gemini:/ { section="gemini" }
    /^[[:space:]]*cursor:/ { section="cursor" }
    /^[[:space:]]*codex:/ { section="codex" }
    /^[[:space:]]*enabled:[[:space:]]*true/ {
        if (section == "claude") print "RUN_CLAUDE=true;"
        if (section == "gemini") print "RUN_GEMINI=true;"
        if (section == "cursor") print "RUN_CURSOR=true;"
        if (section == "codex") print "RUN_CODEX=true;"
    }
    /^[[:space:]]*enabled:[[:space:]]*false/ {
        if (section == "claude") print "RUN_CLAUDE=false;"
        if (section == "gemini") print "RUN_GEMINI=false;"
        if (section == "cursor") print "RUN_CURSOR=false;"
        if (section == "codex") print "RUN_CODEX=false;"
    }
    /^[[:space:]]*minimum_agents:[[:space:]]*[0-9]+/ {
        if (match($0, /[0-9]+/)) {
            print "MIN_AGENTS=" substr($0, RSTART, RLENGTH) ";"
        }
    }
' configs/claude/config/services.yml
