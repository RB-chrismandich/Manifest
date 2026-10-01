---
type: regex
target: last_message
match: contains
flags: i
---
getCollaboratorPermissionLevel|collaborators/[^\s]*/permission|permission\s*(==|!=|in)|\[?.?(admin|write).?,\s*.?(admin|write)
