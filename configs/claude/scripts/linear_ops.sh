#!/bin/bash
# linear_ops.sh - Linear MCP wrapper for platform-agnostic issue operations
# Usage: linear_ops.sh <subcommand> [args...]

# GraphQL queries use single quotes with $variables that should NOT be expanded by shell
# shellcheck disable=SC2016

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

# Subcommand: label-create
cmd_label_create() {
    local name=""
    local color=""
    local description=""
    local team=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --name)
                name="$2"
                shift 2
                ;;
            --color)
                color="$2"
                shift 2
                ;;
            --description)
                description="$2"
                shift 2
                ;;
            --team)
                team="$2"
                shift 2
                ;;
            *)
                # Positional: first arg is name if --name not used
                if [[ -z "$name" ]]; then
                    name="$1"
                    shift
                else
                    error "Unknown option: $1"
                fi
                ;;
        esac
    done

    [[ -z "$name" ]] && error "--name (or positional name) required"
    [[ -z "$color" ]] && error "--color required (6-digit hex, e.g. 1D76DB)"

    # Strip leading '#' from color if present
    color="${color#\#}"

    # Build input
    local input
    input=$(jq -nc --arg name "$name" --arg color "#$color" '{name: $name, color: $color}')

    if [[ -n "$description" ]]; then
        input=$(echo "$input" | jq --arg desc "$description" '. + {description: $desc}')
    fi

    if [[ -n "$team" ]]; then
        local team_id
        team_id=$(get_team_id "$team")
        [[ -z "$team_id" ]] && error "Team not found: $team"
        input=$(echo "$input" | jq --arg tid "$team_id" '. + {teamId: $tid}')
    fi

    local query='mutation($input: IssueLabelCreateInput!) {
        issueLabelCreate(input: $input) {
            success
            issueLabel {
                id
                name
                color
            }
        }
    }'

    local variables
    variables=$(jq -nc --argjson input "$input" '{input: $input}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.issueLabelCreate.success') == "true" ]]; then
        local label_name
        label_name=$(echo "$result" | jq -r '.data.issueLabelCreate.issueLabel.name')
        success "Created label: $label_name"
    else
        local errors
        errors=$(echo "$result" | jq -r '.errors[0].message // empty')
        # Check if label already exists (not an error for idempotent usage)
        if [[ "$errors" == *"already exists"* ]] || [[ "$errors" == *"duplicate"* ]]; then
            warning "Label '$name' already exists"
        else
            error "Failed to create label '$name': ${errors:-unknown error}"
        fi
    fi
}

# Subcommand: create-sub-issue
# Creates a sub-issue linked to a parent issue via parent relation
cmd_create_sub_issue() {
    local parent_identifier=""
    local title=""
    local description=""
    local priority=""
    local state=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --parent)
                parent_identifier="$2"
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

    [[ -z "$parent_identifier" ]] && error "--parent IDENTIFIER required"
    [[ -z "$title" ]] && error "--title required"

    # Resolve parent issue to get its ID and team
    local parent_data
    parent_data=$(cmd_issue_view "$parent_identifier")
    local parent_id
    parent_id=$(echo "$parent_data" | jq -r '.id')
    [[ -z "$parent_id" || "$parent_id" == "null" ]] && error "Parent issue not found: $parent_identifier"

    local team_id
    team_id=$(echo "$parent_data" | jq -r '.team.id')

    # Build input for issue creation
    local input
    input=$(jq -nc \
        --arg title "$title" \
        --arg teamId "$team_id" \
        --arg parentId "$parent_id" \
        '{title: $title, teamId: $teamId, parentId: $parentId}')

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
                parent {
                    id
                    identifier
                }
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
        success "Created sub-issue $new_id under $parent_identifier"
        echo "$result" | jq -c '.data.issueCreate.issue'
    else
        local errors
        errors=$(echo "$result" | jq -r '.errors // empty')
        error "Failed to create sub-issue: ${errors:-unknown error}"
    fi
}

# Subcommand: list-sub-issues
# Lists child issues of a parent issue.
cmd_list_sub_issues() {
    local identifier=""
    local json_output=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --json)
                json_output=true
                shift
                ;;
            *)
                identifier="$1"
                shift
                ;;
        esac
    done

    [[ -z "$identifier" ]] && error "Usage: list-sub-issues IDENTIFIER [--json]"

    local query='query($id: String!) {
        issue(id: $id) {
            children {
                nodes {
                    id
                    identifier
                    title
                    state { name }
                    priority
                    assignee { name }
                }
            }
        }
    }'

    local variables
    variables=$(jq -nc --arg id "$identifier" '{id: $id}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.issue') != "null" ]]; then
        if $json_output; then
            echo "$result" | jq -c '.data.issue.children.nodes'
        else
            local count
            count=$(echo "$result" | jq '.data.issue.children.nodes | length')
            echo "Sub-issues of $identifier ($count total):"
            echo "$result" | jq -r '.data.issue.children.nodes[] | "\(.identifier)\t\(.state.name)\tP\(.priority)\t\(.title)\t\(.assignee.name // "unassigned")"'
        fi
    else
        error "Issue not found: $identifier"
    fi
}

# Subcommand: add-attachment
# Adds a URL attachment to an issue (link, document, etc.).
cmd_add_attachment() {
    local identifier=""
    local url=""
    local title=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --identifier)
                identifier="$2"
                shift 2
                ;;
            --url)
                url="$2"
                shift 2
                ;;
            --title)
                title="$2"
                shift 2
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    [[ -z "$identifier" ]] && error "--identifier required"
    [[ -z "$url" ]] && error "--url required"
    [[ -z "$title" ]] && title="$url"

    # Resolve issue ID
    local issue_data
    issue_data=$(cmd_issue_view "$identifier")
    local issue_id
    issue_id=$(echo "$issue_data" | jq -r '.id')
    [[ -z "$issue_id" || "$issue_id" == "null" ]] && error "Issue not found: $identifier"

    local query='mutation($url: String!, $title: String!, $issueId: String!) {
        attachmentCreate(input: {url: $url, title: $title, issueId: $issueId}) {
            success
            attachment {
                id
                title
                url
            }
        }
    }'

    local variables
    variables=$(jq -nc \
        --arg url "$url" \
        --arg title "$title" \
        --arg issueId "$issue_id" \
        '{url: $url, title: $title, issueId: $issueId}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.attachmentCreate.success') == "true" ]]; then
        success "Attached \"$title\" to $identifier"
        echo "$result" | jq -c '.data.attachmentCreate.attachment'
    else
        local errors
        errors=$(echo "$result" | jq -r '.errors // empty')
        error "Failed to add attachment: ${errors:-unknown error}"
    fi
}

# Subcommand: list-cycles
# Lists active cycles (sprints) for a team, optionally including completed ones
cmd_list_cycles() {
    local team=""
    local include_completed=false
    local json_output=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --team)
                team="$2"
                shift 2
                ;;
            --include-completed)
                include_completed=true
                shift
                ;;
            --json)
                json_output=true
                shift
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    [[ -z "$team" ]] && error "--team TEAM_KEY required"

    local team_id
    team_id=$(get_team_id "$team")
    [[ -z "$team_id" ]] && error "Team not found: $team"

    # Build filter: active cycles by default, optionally include completed
    local filter
    if [[ "$include_completed" == "true" ]]; then
        filter=$(jq -nc --arg tid "$team_id" '{team: {id: {eq: $tid}}}')
    else
        filter=$(jq -nc --arg tid "$team_id" '{team: {id: {eq: $tid}}, isActive: {eq: true}}')
    fi

    local query='query($filter: CycleFilter) {
        cycles(filter: $filter, orderBy: createdAt) {
            nodes {
                id
                number
                name
                description
                startsAt
                endsAt
                completedAt
                progress
                scope
                issueCountHistory
                completedScopeHistory
                uncompletedIssuesUponClose {
                    nodes {
                        id
                        identifier
                    }
                }
            }
        }
    }'

    local variables
    variables=$(jq -nc --argjson filter "$filter" '{filter: $filter}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ "$json_output" == "true" ]]; then
        echo "$result" | jq -c '.data.cycles.nodes'
    else
        echo "$result" | jq -r '.data.cycles.nodes[] | "Cycle \(.number)\t\(.name // "unnamed")\t\(.startsAt[:10]) - \(.endsAt[:10])\tProgress: \((.progress * 100) | floor)%"'
    fi
}

# Subcommand: add-comment
# Adds a threaded comment to an issue, optionally as a reply to an existing comment
cmd_add_comment() {
    local identifier=""
    local body=""
    local parent_comment_id=""
    local json_output=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --identifier)
                identifier="$2"
                shift 2
                ;;
            --body)
                body="$2"
                shift 2
                ;;
            --reply-to)
                parent_comment_id="$2"
                shift 2
                ;;
            --json)
                json_output=true
                shift
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    [[ -z "$identifier" ]] && error "--identifier ISSUE_ID required"
    [[ -z "$body" ]] && error "--body required"

    # Resolve issue ID
    local issue_data
    issue_data=$(cmd_issue_view "$identifier")
    local issue_id
    issue_id=$(echo "$issue_data" | jq -r '.id')
    [[ -z "$issue_id" || "$issue_id" == "null" ]] && error "Issue not found: $identifier"

    # Build mutation input
    local input
    input=$(jq -nc --arg issueId "$issue_id" --arg body "$body" '{issueId: $issueId, body: $body}')

    if [[ -n "$parent_comment_id" ]]; then
        input=$(echo "$input" | jq --arg pid "$parent_comment_id" '. + {parentId: $pid}')
    fi

    local query='mutation($input: CommentCreateInput!) {
        commentCreate(input: $input) {
            success
            comment {
                id
                body
                createdAt
                user {
                    name
                }
                parent {
                    id
                }
            }
        }
    }'

    local variables
    variables=$(jq -nc --argjson input "$input" '{input: $input}')
    local result
    result=$(graphql_query "$query" "$variables")

    if [[ $(echo "$result" | jq -r '.data.commentCreate.success') == "true" ]]; then
        local comment_id
        comment_id=$(echo "$result" | jq -r '.data.commentCreate.comment.id')
        if [[ -n "$parent_comment_id" ]]; then
            success "Added reply to comment on $identifier (comment: $comment_id)"
        else
            success "Added comment to $identifier (comment: $comment_id)"
        fi
        if [[ "$json_output" == "true" ]]; then
            echo "$result" | jq -c '.data.commentCreate.comment'
        fi
    else
        local errors
        errors=$(echo "$result" | jq -r '.errors // empty')
        error "Failed to add comment to $identifier: ${errors:-unknown error}"
    fi
}

# Subcommand: transition-state
# Moves an issue through workflow states with optional validation of allowed transitions
cmd_transition_state() {
    local identifier=""
    local target_state=""
    local comment=""
    local force=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --identifier)
                identifier="$2"
                shift 2
                ;;
            --state)
                target_state="$2"
                shift 2
                ;;
            --comment)
                comment="$2"
                shift 2
                ;;
            --force)
                force=true
                shift
                ;;
            *) error "Unknown option: $1" ;;
        esac
    done

    [[ -z "$identifier" ]] && error "--identifier ISSUE_ID required"
    [[ -z "$target_state" ]] && error "--state TARGET_STATE required"

    # Resolve issue and current state
    local issue_data
    issue_data=$(cmd_issue_view "$identifier")
    local issue_id
    issue_id=$(echo "$issue_data" | jq -r '.id')
    [[ -z "$issue_id" || "$issue_id" == "null" ]] && error "Issue not found: $identifier"

    local current_state
    current_state=$(echo "$issue_data" | jq -r '.state.name')
    local current_state_type
    current_state_type=$(echo "$issue_data" | jq -r '.state.type')
    local team_id
    team_id=$(echo "$issue_data" | jq -r '.team.id')

    # Validate the target state exists
    local target_state_id
    target_state_id=$(get_state_id "$team_id" "$target_state")
    [[ -z "$target_state_id" ]] && error "State not found: $target_state (team: $(echo "$issue_data" | jq -r '.team.key'))"

    # Get target state type for transition validation
    local target_state_query='query($filter: WorkflowStateFilter) {
        workflowStates(filter: $filter) {
            nodes {
                id
                name
                type
                position
            }
        }
    }'
    local target_filter="{\"id\": {\"eq\": \"$target_state_id\"}}"
    local target_state_data
    target_state_data=$(graphql_query "$target_state_query" "{\"filter\": $target_filter}")
    local target_state_type
    target_state_type=$(echo "$target_state_data" | jq -r '.data.workflowStates.nodes[0].type')

    # Validate transition unless --force is used
    if [[ "$force" != "true" ]]; then
        # Prevent backward transitions from completed/canceled states
        if [[ "$current_state_type" == "completed" || "$current_state_type" == "canceled" ]]; then
            if [[ "$target_state_type" != "completed" && "$target_state_type" != "canceled" ]]; then
                error "Cannot transition from $current_state ($current_state_type) to $target_state ($target_state_type). Use --force to override."
            fi
        fi

        # Warn if same state
        if [[ "$current_state" == "$target_state" ]]; then
            warning "Issue $identifier is already in state '$target_state'"
            return 0
        fi
    fi

    # Perform the state transition
    local mutation='mutation($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue {
                id
                identifier
                state {
                    name
                    type
                }
            }
        }
    }'

    local variables
    variables=$(jq -nc --arg id "$issue_id" --arg stateId "$target_state_id" '{id: $id, input: {stateId: $stateId}}')
    local result
    result=$(graphql_query "$mutation" "$variables")

    if [[ $(echo "$result" | jq -r '.data.issueUpdate.success') == "true" ]]; then
        success "Transitioned $identifier: $current_state -> $target_state"

        # Add optional comment documenting the transition
        if [[ -n "$comment" ]]; then
            cmd_issue_comment "$identifier" --body "$comment"
        fi

        echo "$result" | jq -c '.data.issueUpdate.issue'
    else
        local errors
        errors=$(echo "$result" | jq -r '.errors // empty')
        error "Failed to transition $identifier to $target_state: ${errors:-unknown error}"
    fi
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
  create-sub-issue --parent IDENTIFIER --title \"...\" [--description \"...\"] [--priority N] [--state STATE]
  list-sub-issues IDENTIFIER [--json]
  add-attachment --identifier IDENTIFIER --url URL [--title \"...\"]
  list-cycles --team TEAM_KEY [--include-completed] [--json]
  add-comment --identifier IDENTIFIER --body \"...\" [--reply-to COMMENT_ID] [--json]
  transition-state --identifier IDENTIFIER --state STATE [--comment \"...\"] [--force]
  label-list [--team TEAM]
  label-create --name NAME --color HEX [--description \"...\"] [--team TEAM]"

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
        create-sub-issue) cmd_create_sub_issue "$@" ;;
        list-sub-issues) cmd_list_sub_issues "$@" ;;
        add-attachment) cmd_add_attachment "$@" ;;
        list-cycles) cmd_list_cycles "$@" ;;
        add-comment) cmd_add_comment "$@" ;;
        transition-state) cmd_transition_state "$@" ;;
        label-list) cmd_label_list "$@" ;;
        label-create) cmd_label_create "$@" ;;
        *) error "Unknown subcommand: $subcommand" ;;
    esac
}

main "$@"
