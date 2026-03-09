#!/bin/bash
awk '
    BEGIN { section=""; subsection="" }
    /^[[:space:]]*claude:/ { section="claude"; subsection="" }
    /^[[:space:]]*gemini:/ { section="gemini"; subsection="" }
    /^[[:space:]]*cursor:/ { section="cursor"; subsection="" }
    /^[[:space:]]*codex:/ { section="codex"; subsection="" }
    /^[[:space:]]*git_cli:/ { section="git_cli"; subsection="" }
    /^[[:space:]]*github:/ { if (section == "git_cli") subsection="github" }
    /^[[:space:]]*gitlab:/ { if (section == "git_cli") subsection="gitlab" }
    /^[[:space:]]*enabled:[[:space:]]*true/ {
        if (section == "claude") print "FILE_CLAUDE=true"
        if (section == "gemini") print "FILE_GEMINI=true"
        if (section == "cursor") print "FILE_CURSOR=true"
        if (section == "codex") print "FILE_CODEX=true"
        if (section == "git_cli" && subsection == "github") print "FILE_GH=true"
        if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=true"
    }
    /^[[:space:]]*enabled:[[:space:]]*false/ {
        if (section == "claude") print "FILE_CLAUDE=false"
        if (section == "gemini") print "FILE_GEMINI=false"
        if (section == "cursor") print "FILE_CURSOR=false"
        if (section == "codex") print "FILE_CODEX=false"
        if (section == "git_cli" && subsection == "github") print "FILE_GH=false"
        if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=false"
    }
    /^[[:space:]]*enabled:[[:space:]]*auto/ {
        if (section == "git_cli" && subsection == "github") print "FILE_GH=auto"
        if (section == "git_cli" && subsection == "gitlab") print "FILE_GLAB=auto"
    }
' configs/claude/config/services.yml
