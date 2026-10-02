# shellcheck shell=bash disable=SC2016

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
