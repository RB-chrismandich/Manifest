# shellcheck shell=bash disable=SC2016

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
    local target_state_data
    target_state_data=$(graphql_query "$target_state_query" \
        "$(jq -nc --arg id "$target_state_id" '{filter: {id: {eq: $id}}}')")
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
usage() {
    cat << 'USAGE'
Usage: linear_ops.sh <subcommand> [args...]

Subcommands:
  team-list            team-states          issue-list
  issue-view           issue-create         issue-update
  issue-comment        issue-close          issue-mark-duplicate
  create-sub-issue     list-sub-issues      add-attachment
  list-cycles          add-comment          transition-state
  label-list           label-create

Requires LINEAR_API_KEY. Run a subcommand with no args for its usage.
USAGE
}

main() {
    if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
        usage
        exit 0
    fi
    [[ $# -eq 0 ]] && error "Usage: linear_ops.sh <subcommand> [args...]

Subcommands:
  team-list [--json]
  team-states TEAM_KEY
  issue-list [--team TEAM] [--state STATE] [--priority N] [--limit N] [--json]
  issue-view IDENTIFIER
  issue-create --team TEAM_KEY --title \"...\" [--description \"...\"] [--priority N] [--state STATE]
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
        issue-create) cmd_issue_create "$@" ;;
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
