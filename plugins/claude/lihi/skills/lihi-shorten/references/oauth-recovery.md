# Claude Code OAuth recovery for shortening

Read only for an unavailable required tool or an authentication signal, after local detection passed.

Let Claude Code manage OAuth. Never request or store passwords, authorization codes, access tokens, refresh tokens, or client secrets.
Preserve the exact content snapshot, detector result, pending URL, confirmed ledger, uncertain states, recovery budget, and release intent.

## Unavailable tool

- Try host tool discovery once for a missing required tool, unless already attempted for this failure. Skip discovery when the tool is already callable.
- If resolved with no outstanding authentication failure, return directly to the pending normal flow under its dispatch rules. No authentication confirmation or budget is needed. Never replay a possibly dispatched mutation.
- If an authentication failure remains outstanding, continue to authentication classification; finding the tool does not clear that failure.
- If still unavailable, inspect available read-only connection status. Report loading, filtering, configuration, or connection failure only when supported. Without an authentication signal, stop without login or configuration changes. Empty resources, `tools/list` omissions, and `Unknown tool name.` alone prove neither a missing grant nor missing authorization.

## Choose recovery from observed evidence

Use the current host/server endpoint, HTTP status, OAuth `error`, and `error_description`. Tool absence and `Auth required` alone prove neither first-time authorization nor an invalid refresh token.

| Evidence | Action |
| --- | --- |
| Stored refresh credentials lack an authorization-server issuer or cannot bind to it | Report a host credential-binding failure. Existing credentials are present; stop without automatic refresh, login, or credential changes. Host authorization-state repair is needed. |
| Host explicitly confirms no prior authorization exists | Initial authentication. |
| Refresh-token exchange at `/mcp/v1/token` returns HTTP 401, or explicitly says the refresh token is invalid, expired, revoked, or unusable | Qualifying interactive reauthentication. `invalid_grant` qualifies only for that exchange. |
| Existing authorization with a tool-endpoint 401, host-level `Auth required`, or a confirmed legacy token missing a required tool grant | Allow one host-managed refresh. |
| Other error or insufficient evidence | Report the readable error or missing evidence, preserve state, and stop without login. |

Host-managed refresh is not a lihi tool or an interactive login command. If the refresh mechanism or its outcome is unavailable, do not invent a refresh call, claim success, or start login merely as a fallback. A confirmed qualifying refresh-token failure follows the interactive branch above. A newly available tool alone does not confirm authentication recovered.

## Recovery limits by stage

Count stages, not every HTTP authentication error. Per incident, allow at most one host refresh, one qualifying interactive authentication stage with the documented host fallback, and one resumed logical operation.

- A tool authentication failure starts the incident. A failed refresh may enter interactive authentication only when it meets the qualifying refresh-token condition above; it does not consume the resumed-operation allowance.
- Failed or unconfirmed interactive authentication stops automatic recovery. Do not start another authentication stage.
- After confirmed authentication recovery, resume once under the caller's dispatch rules. For switching, fresh options and the permitted verification or retry are parts of that one logical operation.
- An authentication failure during the resumed operation ends the incident without another refresh or login, even if another stage's allowance was unused. Preserve the failure and dispatch state.

## Interactive authentication

- For initial authentication or qualifying reauthentication, explain that lihi access is required, then ask the user to open `/mcp`, select the lihi plugin server, and choose **Authenticate**. Never run or recommend a Codex command.

## Resume without duplicate creation

- This section applies only after an authentication failure or confirmed need for initial authorization, not tool resolution alone. After host-confirmed authentication recovery, resume only an operation known not to have dispatched. Retry an interrupted `site_create` only after a conclusive pre-dispatch 401 or host confirmation of non-dispatch.
- Timeout, connection loss, malformed or incomplete output, and any possibly dispatched `site_create` remain uncertain. Never replay them or release unresolved content.
- Describe the actual recovery: initial login, confirmed refresh-token failure, or blocked host recovery. Do not call initial authorization an expired session or say login is opening before it starts.
- When no create call succeeded or may have dispatched, say `目前尚未建立或發布任何連結。` in Chinese, or its equivalent in the user's language. Otherwise distinguish confirmed and possibly created links and state that nothing was published.
