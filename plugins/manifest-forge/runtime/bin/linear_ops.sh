#!/bin/bash
# linear_ops.sh - Linear MCP wrapper for platform-agnostic issue operations
# Usage: linear_ops.sh <subcommand> [args...]
#
# GraphQL query bodies below are single-quoted intentionally throughout this
# file: they use GraphQL's own $var syntax (query($filter: TeamFilter) {...}),
# which must stay literal for the server to parse — shell must never expand
# it. Variables are passed separately via `jq` into the `variables` JSON arg.
# shellcheck disable=SC2016

set -euo pipefail

FORGE_RUNTIME_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
FORGE_CONFIG_DIR="$FORGE_RUNTIME_DIR/config"
FORGE_STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/manifest/forge"
export FORGE_RUNTIME_DIR FORGE_CONFIG_DIR FORGE_STATE_DIR

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Error handling (canonical err() convention; error() exits, warning() continues)
err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "linear-ops: $*" >&2; else printf '%s\n' "linear-ops: $*" >&2; fi; }
error() {
    err "$1"
    exit 1
}

warning() {
    if [[ -t 2 ]]; then printf '\033[0;33m%s\033[0m\n' "linear-ops: Warning: $1" >&2; else printf '%s\n' "linear-ops: Warning: $1" >&2; fi
}

success() {
    echo -e "${GREEN}$1${NC}" >&2
}

# Check authentication.
# This script talks to the Linear API via raw curl, so a usable API key is
# required — a Linear MCP registration is irrelevant here and previously
# short-circuited this check into sending an empty Bearer token (issue #312).
check_auth() {
    # Credentials are supplied by the caller's environment only. The runtime
    # never reads or writes CLI credential stores.
    if [[ -n "${LINEAR_API_KEY:-}" ]]; then
        return 0
    fi

    error "Linear authentication required. Set the LINEAR_API_KEY environment variable.
Get an API key from: https://linear.app/settings/api"
}

# Execute GraphQL query via Linear API
graphql_query() {
    local query="$1"
    local variables="${2:-{}}"

    if [[ -z "${LINEAR_API_KEY:-}" ]]; then
        check_auth
    fi

    curl -s -X POST https://api.linear.app/graphql \
        -H "Authorization: Bearer ${LINEAR_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "{\"query\": $(jq -Rs . <<< "$query"), \"variables\": $variables}"
}

# Get team ID from team key (e.g., "ENG" -> UUID)
get_team_id() {
    local team_key="$1"

    local query='query($filter: TeamFilter) {
        teams(filter: $filter) {
            nodes {
                id
                key
                name
            }
        }
    }'

    local variables
    variables=$(jq -nc --arg key "$team_key" '{filter: {key: {eq: $key}}}')
    local result
    result=$(graphql_query "$query" "$variables")

    echo "$result" | jq -r '.data.teams.nodes[0].id // empty'
}

# Get state ID from state name (team-specific)
get_state_id() {
    local team_id="$1"
    local state_name="$2"

    local query='query($filter: WorkflowStateFilter) {
        workflowStates(filter: $filter) {
            nodes {
                id
                name
                type
            }
        }
    }'

    local variables
    variables=$(jq -nc --arg teamId "$team_id" --arg name "$state_name" \
        '{filter: {team: {id: {eq: $teamId}}, name: {eq: $name}}}')
    local result
    result=$(graphql_query "$query" "$variables")

    echo "$result" | jq -r '.data.workflowStates.nodes[0].id // empty'
}

# Subcommand: team-list
cmd_team_list() {
    local json_output=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --json)
                json_output=true
                shift
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    local query='query {
        teams {
            nodes {
                id
                key
                name
                description
            }
        }
    }'

    local result
    result=$(graphql_query "$query")

    if [[ "$json_output" == "true" ]]; then
        echo "$result" | jq -c '.data.teams.nodes'
    else
        echo "$result" | jq -r '.data.teams.nodes[] | "\(.key)\t\(.name)"'
    fi
}

# Subcommand: team-states
cmd_team_states() {
    local team_key="$1"

    local team_id
    team_id=$(get_team_id "$team_key")
    [[ -z "$team_id" ]] && error "Team not found: $team_key"

    local query='query($teamId: String!) {
        workflowStates(filter: {team: {id: {eq: $teamId}}}) {
            nodes {
                id
                name
                type
                position
            }
        }
    }'

    local variables
    variables=$(jq -nc --arg teamId "$team_id" '{teamId: $teamId}')
    local result
    result=$(graphql_query "$query" "$variables")

    echo "$result" | jq -r '.data.workflowStates.nodes[] | "\(.name)\t\(.type)"'
}

# Subcommand: issue-list
cmd_issue_list() {
    local team=""
    local state=""
    local priority=""
    local limit=50
    local json_output=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --team)
                team="$2"
                shift 2
                ;;
            --state)
                state="$2"
                shift 2
                ;;
            --priority)
                priority="$2"
                shift 2
                ;;
            --limit)
                limit="$2"
                shift 2
                ;;
            --json)
                json_output=true
                shift
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    # Build filter
    local filter="{\"or\": [{\"state\": {\"type\": {\"neq\": \"completed\"}}}, {\"state\": {\"type\": {\"neq\": \"canceled\"}}}]}"

    if [[ -n "$team" ]]; then
        local team_id
        team_id=$(get_team_id "$team")
        [[ -z "$team_id" ]] && error "Team not found: $team"
        filter=$(echo "$filter" | jq --arg tid "$team_id" '. + {team: {id: {eq: $tid}}}')
    fi

    if [[ -n "$state" ]]; then
        filter=$(echo "$filter" | jq --arg st "$state" '. + {state: {type: {eq: $st}}}')
    fi

    if [[ -n "$priority" ]]; then
        filter=$(echo "$filter" | jq --argjson pri "$priority" '. + {priority: {eq: $pri}}')
    fi

    local query='query($filter: IssueFilter, $first: Int) {
        issues(filter: $filter, first: $first, orderBy: updatedAt) {
            nodes {
                id
                identifier
                title
                description
                priority
                createdAt
                updatedAt
                state {
                    id
                    name
                    type
                }
                team {
                    id
                    key
                    name
                }
                labels {
                    nodes {
                        id
                        name
                    }
                }
                relations {
                    nodes {
                        id
                        type
                        relatedIssue {
                            id
                            identifier
                        }
                    }
                }
            }
        }
    }'

    local variables
    variables=$(jq -nc --argjson filter "$filter" --argjson limit "$limit" '{filter: $filter, first: $limit}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ "$json_output" == "true" ]]; then
        echo "$result" | jq -c '.data.issues.nodes'
    else
        echo "$result" | jq -r '.data.issues.nodes[] | "\(.identifier)\t\(.title)"'
    fi
}

# Subcommand: issue-view
cmd_issue_view() {
    local identifier="$1"

    local query='query($identifier: String!) {
        issue(filter: {identifier: {eq: $identifier}}) {
            id
            identifier
            title
            description
            priority
            estimate
            createdAt
            updatedAt
            completedAt
            canceledAt
            state {
                id
                name
                type
            }
            team {
                id
                key
                name
            }
            assignee {
                id
                name
                email
            }
            labels {
                nodes {
                    id
                    name
                }
            }
            relations {
                nodes {
                    id
                    type
                    relatedIssue {
                        id
                        identifier
                        title
                    }
                }
            }
            comments {
                nodes {
                    id
                    body
                    createdAt
                    user {
                        name
                    }
                }
            }
        }
    }'

    local variables
    variables=$(jq -nc --arg identifier "$identifier" '{identifier: $identifier}')
    local result
    result=$(graphql_query "$query" "$variables")

    echo "$result" | jq -r '.data.issue'
}

# Subcommand: issue-create
cmd_issue_create() {
    local team=""
    local title=""
    local description=""
    local priority=""
    local state=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --team)
                team="$2"
                shift 2
                ;;
            --title)
                title="$2"
                shift 2
                ;;
            --description)
                description="$2"
                shift 2
                ;;
            --priority)
                priority="$2"
                shift 2
                ;;
            --state)
                state="$2"
                shift 2
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    [[ -z "$team" ]] && error "--team TEAM_KEY required"
    [[ -z "$title" ]] && error "--title required"

    local team_id
    team_id=$(get_team_id "$team")
    [[ -z "$team_id" ]] && error "Team not found: $team"

    local input
    input=$(jq -nc --arg title "$title" --arg teamId "$team_id" '{title: $title, teamId: $teamId}')

    if [[ -n "$description" ]]; then
        input=$(echo "$input" | jq --arg desc "$description" '. + {description: $desc}')
    fi

    if [[ -n "$priority" ]]; then
        input=$(echo "$input" | jq --argjson pri "$priority" '. + {priority: $pri}')
    fi

    if [[ -n "$state" ]]; then
        local state_id
        state_id=$(get_state_id "$team_id" "$state")
        [[ -z "$state_id" ]] && error "State not found: $state"
        input=$(echo "$input" | jq --arg sid "$state_id" '. + {stateId: $sid}')
    fi

    local query='mutation($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue {
                id
                identifier
                title
            }
        }
    }'

    local variables
    variables=$(jq -nc --argjson input "$input" '{input: $input}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.issueCreate.success') == "true" ]]; then
        local new_id
        new_id=$(echo "$result" | jq -r '.data.issueCreate.issue.identifier')
        success "Created $new_id"
        echo "$result" | jq -c '.data.issueCreate.issue'
    else
        local errors
        errors=$(echo "$result" | jq -r '.errors // empty')
        error "Failed to create issue: ${errors:-unknown error}"
    fi
}

# Subcommand: issue-update
cmd_issue_update() {
    local identifier="$1"
    shift

    local state=""
    local priority=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --state)
                state="$2"
                shift 2
                ;;
            --priority)
                priority="$2"
                shift 2
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    # Get issue ID from identifier
    local issue_data
    issue_data=$(cmd_issue_view "$identifier")
    local issue_id
    issue_id=$(echo "$issue_data" | jq -r '.id')
    [[ -z "$issue_id" ]] && error "Issue not found: $identifier"

    local input="{}"

    if [[ -n "$state" ]]; then
        local team_id
        team_id=$(echo "$issue_data" | jq -r '.team.id')
        local state_id
        state_id=$(get_state_id "$team_id" "$state")
        [[ -z "$state_id" ]] && error "State not found: $state"
        input=$(echo "$input" | jq --arg sid "$state_id" '. + {stateId: $sid}')
    fi

    if [[ -n "$priority" ]]; then
        input=$(echo "$input" | jq --argjson pri "$priority" '. + {priority: $pri}')
    fi

    local query='mutation($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                identifier
            }
        }
    }'

    local variables
    variables=$(jq -nc --arg id "$issue_id" --argjson input "$input" '{id: $id, input: $input}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.issueUpdate.success') == "true" ]]; then
        success "Updated $identifier"
    else
        error "Failed to update $identifier"
    fi
}

# Subcommand: issue-comment
cmd_issue_comment() {
    local identifier="$1"
    shift

    local body=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --body)
                body="$2"
                shift 2
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    [[ -z "$body" ]] && error "--body required"

    # Get issue ID
    local issue_data
    issue_data=$(cmd_issue_view "$identifier")
    local issue_id
    issue_id=$(echo "$issue_data" | jq -r '.id')
    [[ -z "$issue_id" ]] && error "Issue not found: $identifier"

    local query='mutation($issueId: String!, $body: String!) {
        commentCreate(input: {issueId: $issueId, body: $body}) {
            success
            comment {
                id
            }
        }
    }'

    local variables
    variables=$(jq -nc --arg issueId "$issue_id" --arg body "$body" '{issueId: $issueId, body: $body}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.commentCreate.success') == "true" ]]; then
        success "Added comment to $identifier"
    else
        error "Failed to add comment to $identifier"
    fi
}

# Subcommand: issue-close

# Remaining provider commands are sourced from the same bundle.
# shellcheck disable=SC1091
source "$FORGE_RUNTIME_DIR/bin/lib/linear_issue_extras.sh"
# shellcheck disable=SC1091
source "$FORGE_RUNTIME_DIR/bin/lib/linear_workflow.sh"
