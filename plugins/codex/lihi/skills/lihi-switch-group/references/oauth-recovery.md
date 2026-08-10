# Codex OAuth recovery for group switching

Read this file only from the switch error-recovery reference after it classifies an authentication branch.

- Let Codex manage OAuth and token storage. Never request credentials or tokens.
- Own only authentication recovery and its budget. Do not call any lihi lookup or mutation tool, refetch selector options, verify dispatch, or replay an operation from this reference; return control to the calling error-recovery reference after authentication succeeds or fails.
- A validated switch result never enters OAuth recovery. A changed selector may revoke the access token; refresh only when a later independent lihi request needs access.
- Classify authentication from the host-visible endpoint, HTTP status, OAuth `error`, and `error_description`. Do not classify mutation dispatch or selector state here.
- For an existing authorization, allow one host-managed refresh when the calling error-recovery reference reports a conclusive pre-dispatch HTTP 401, host-level `Auth required`, or a legacy token missing the required tool grant.
- After a successful refresh, return one `authentication_recovered` outcome to the caller. The caller may resume one operation under its own fresh-option and dispatch rules; this reference does not perform that operation.
- Start interactive reauthentication only when `/mcp/v1/token` returns HTTP 401 for a refresh-token exchange or a readable error explicitly says the refresh token is invalid, expired, revoked, or unusable. Initial authentication applies only when no prior authorization exists.
- For initial authentication or qualifying reauthentication, run `codex mcp login lihi` once when shell execution is available. If it cannot start or complete, ask the user to run it; use **MCP settings → lihi → Authenticate** only when that command is unavailable.
- After successful interactive authentication, return one `authentication_recovered` outcome to the caller without making an MCP call. Allow at most one host refresh, one qualifying interactive authentication, and one resumed operation by the caller per incident. A second authentication failure stops.
- For any unmatched readable error, report it and preserve state without starting interactive authentication.
