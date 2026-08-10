# Codex OAuth recovery for shortening

Read this file only when lihi authentication is missing, expired, or rejected.

- Let Codex manage OAuth. Never request or store passwords, authorization codes, access tokens, refresh tokens, or client secrets.
- Preserve the exact content snapshot, detector result, pending URL, confirmed ledger, uncertain states, authentication-recovery budget, and external-action intent.
- Classify failures from the host-visible endpoint, HTTP status, OAuth `error`, and `error_description`.
- For an existing authorization, allow one host-managed refresh for tool-endpoint `401 invalid_token` or host-level `Auth required`.
- Retry the interrupted `site_create` after refresh only when HTTP 401 conclusively rejected it before dispatch or the host explicitly confirms no dispatch.
- Timeout, connection loss, malformed or incomplete output, or any possibly dispatched `site_create` remains uncertain and must never be replayed.
- Start interactive reauthentication only when the refresh-token exchange at `/mcp/v1/token` returns HTTP 401, or a readable error explicitly says the refresh token is invalid, expired, revoked, or unusable. `invalid_grant` qualifies only for that exchange. Use initial authentication only when no prior authorization exists.
- For initial authentication or qualifying reauthentication, explain that lihi access is opening. Run `codex mcp login lihi` once when shell execution is available. If it cannot start or complete, ask the user to run it and do not retry automatically; use **MCP settings → lihi → Authenticate** only when the command is unavailable.
- When no create call succeeded or may have dispatched, tell the user in their language that no link has been created or published. In Chinese: `lihi 驗證已失效，我現在為你開啟 OAuth 登入；目前尚未建立或發布任何連結。` Otherwise distinguish confirmed and possibly created current-batch links and state that nothing was published.
- After successful authentication, resume the one interrupted operation once under the same dispatch guard. Allow at most one host refresh, one qualifying interactive authentication, and one resumed operation per incident. A second authentication failure stops.
- Present unmatched readable errors and preserve state without starting interactive authentication.
