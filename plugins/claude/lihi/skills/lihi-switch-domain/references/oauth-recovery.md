# Claude Code OAuth recovery for domain switching

Read only after switch error recovery identifies an authentication branch.

Let Claude Code manage OAuth and token storage. Never request credentials or tokens.
Own only authentication recovery and its budget. Do not call any lihi lookup or mutation tool; return control to the calling error-recovery reference for discovery, verification, or retry. A validated switch never enters this reference. Its token may be revoked; recovery belongs to a later independent request.

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

- For initial authentication or qualifying reauthentication, ask the user to open `/mcp`, select the lihi plugin server, and choose **Authenticate**. Never run or recommend a Codex command.

## Return control

- Return `authentication_recovered` only after the host confirms refresh or interactive authentication succeeded. Otherwise return `authentication_not_recovered`; the caller must not resume its operation.
