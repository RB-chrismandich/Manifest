#!/bin/bash
# linear_ops.sh - Linear MCP wrapper for platform-agnostic issue operations
# Usage: linear_ops.sh <subcommand> [args...]

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Error handling
error() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

warning() {
    echo -e "${YELLOW}Warning: $1${NC}" >&2
}

success() {
    echo -e "${GREEN}$1${NC}" >&2
}

# Check if Linear MCP is configured
check_linear_mcp() {
    # Check if Linear is in MCP servers config
    if [[ -f ~/.claude/config/mcp_servers.yml ]]; then
        if grep -q "linear:" ~/.claude/config/mcp_servers.yml; then
            return 0
        fi
    fi
    return 1
}

# Check authentication
check_auth() {
    # Try Linear MCP first
    if check_linear_mcp; then
        # Linear MCP should handle OAuth automatically
        return 0
    fi

    # Fallback to personal API key
    if [[ -f ~/.config/linear/token ]]; then
        LINEAR_API_KEY=$(cat ~/.config/linear/token)
        export LINEAR_API_KEY
        return 0
    fi

    error "Linear authentication required. Options:
1. Configure Linear MCP in ~/.claude/config/mcp_servers.yml
2. Set API key in ~/.config/linear/token

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

    local variables="{\"filter\": {\"key\": {\"eq\": \"$team_key\"}}}"
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

    local variables="{\"filter\": {\"team\": {\"id\": {\"eq\": \"$team_id\"}}, \"name\": {\"eq\": \"$state_name\"}}}"
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

    local variables="{\"teamId\": \"$team_id\"}"
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

    local variables="{\"identifier\": \"$identifier\"}"
    local result
    result=$(graphql_query "$query" "$variables")

    echo "$result" | jq -r '.data.issue'
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
cmd_issue_close() {
    local identifier="$1"
    shift

    local comment=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --comment)
                comment="$2"
                shift 2
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    # Get issue data
    local issue_data
    issue_data=$(cmd_issue_view "$identifier")
    local issue_id
    issue_id=$(echo "$issue_data" | jq -r '.id')
    local team_id
    team_id=$(echo "$issue_data" | jq -r '.team.id')

    # Get "Canceled" state ID
    local state_id
    state_id=$(get_state_id "$team_id" "Canceled")
    [[ -z "$state_id" ]] && error "Canceled state not found for team"

    # Update to canceled state
    local query='mutation($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
        }
    }'

    local variables
    variables=$(jq -nc --arg id "$issue_id" --arg stateId "$state_id" '{id: $id, input: {stateId: $stateId}}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.issueUpdate.success') == "true" ]]; then
        if [[ -n "$comment" ]]; then
            cmd_issue_comment "$identifier" --body "$comment"
        fi
        success "Closed $identifier"
    else
        error "Failed to close $identifier"
    fi
}

# Subcommand: issue-mark-duplicate
cmd_issue_mark_duplicate() {
    local identifier="$1"
    shift

    local duplicate_of=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --duplicate-of)
                duplicate_of="$2"
                shift 2
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    [[ -z "$duplicate_of" ]] && error "--duplicate-of required"

    # Get both issue IDs
    local issue_data
    issue_data=$(cmd_issue_view "$identifier")
    local issue_id
    issue_id=$(echo "$issue_data" | jq -r '.id')

    local parent_data
    parent_data=$(cmd_issue_view "$duplicate_of")
    local parent_id
    parent_id=$(echo "$parent_data" | jq -r '.id')

    # Create "duplicates" relation
    local query='mutation($issueId: String!, $relatedIssueId: String!) {
        issueRelationCreate(input: {issueId: $issueId, relatedIssueId: $relatedIssueId, type: "duplicate"}) {
            success
        }
    }'

    local variables
    variables=$(jq -nc --arg issueId "$issue_id" --arg relatedIssueId "$parent_id" '{issueId: $issueId, relatedIssueId: $relatedIssueId}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.issueRelationCreate.success') == "true" ]]; then
        # Also add comment
        cmd_issue_comment "$identifier" --body "Marked as duplicate of $duplicate_of"
        success "Marked $identifier as duplicate of $duplicate_of"
    else
        error "Failed to mark duplicate"
    fi
}

# Subcommand: label-list
cmd_label_list() {
    local team=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --team)
                team="$2"
                shift 2
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    local filter="{}"
    if [[ -n "$team" ]]; then
        local team_id
        team_id=$(get_team_id "$team")
        filter=$(echo "$filter" | jq --arg tid "$team_id" '. + {team: {id: {eq: $tid}}}')
    fi

    local query='query($filter: IssueLabelFilter) {
        issueLabels(filter: $filter) {
            nodes {
                id
                name
                description
                color
            }
        }
    }'

    local variables
    variables=$(jq -nc --argjson filter "$filter" '{filter: $filter}')
    local result
    result=$(graphql_query "$query" "$variables")

    echo "$result" | jq -r '.data.issueLabels.nodes[] | "\(.name)\t\(.description // "")"'
}

# Main command router
main() {
    [[ $# -eq 0 ]] && error "Usage: linear_ops.sh <subcommand> [args...]

Subcommands:
  team-list [--json]
  team-states TEAM_KEY
  issue-list [--team TEAM] [--state STATE] [--priority N] [--limit N] [--json]
  issue-view IDENTIFIER
  issue-update IDENTIFIER [--state STATE] [--priority N]
  issue-comment IDENTIFIER --body \"...\"
  issue-close IDENTIFIER [--comment \"...\"]
  issue-mark-duplicate IDENTIFIER --duplicate-of PARENT_ID
  label-list [--team TEAM]"

    local subcommand="$1"
    shift

    check_auth

    case "$subcommand" in
        team-list) cmd_team_list "$@" ;;
        team-states) cmd_team_states "$@" ;;
        issue-list) cmd_issue_list "$@" ;;
        issue-view) cmd_issue_view "$@" ;;
        issue-update) cmd_issue_update "$@" ;;
        issue-comment) cmd_issue_comment "$@" ;;
        issue-close) cmd_issue_close "$@" ;;
        issue-mark-duplicate) cmd_issue_mark_duplicate "$@" ;;
        label-list) cmd_label_list "$@" ;;
        *) error "Unknown subcommand: $subcommand" ;;
    esac
}

main "$@"
