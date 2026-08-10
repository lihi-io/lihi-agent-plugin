# Claude Code OAuth recovery

- Let Claude Code manage OAuth. Never request or store passwords, authorization codes, access tokens, refresh tokens, or client secrets in chat or project files.
- Classify failures from the host-visible endpoint, HTTP status, OAuth `error`, and `error_description`.
- For an existing authorization, allow one Claude Code host-managed refresh for tool-endpoint `401 invalid_token` or host-level `Auth required`. After a successful refresh, retry only the interrupted `account_status` or `group_options` lookup once. A second authentication failure in the same incident stops.
- Start interactive reauthentication only when the refresh-token exchange at `/mcp/v1/token` returns HTTP 401, or a readable error explicitly says the refresh token is invalid, expired, revoked, or unusable. `invalid_grant` qualifies only for that refresh-token exchange.
- If no prior authorization exists, start initial authentication instead of refresh recovery.
- For initial authentication or qualifying reauthentication, explain that lihi access is required or needs restoration, then ask the user to open `/mcp`, select the lihi plugin server, and choose **Authenticate**. Never run or recommend a Codex command.
- After successful initial authentication or qualifying reauthentication, resume the interrupted lookup once. Allow at most one host refresh, one qualifying interactive authentication, and one resumed lookup per incident.
- Present any other readable description and apply only the matching rule above. When none matches, report the error and preserve validated results without starting interactive authentication.
