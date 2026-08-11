# lihi group-switch error recovery

Read this file completely only when `group_options` or `account_switch_group` fails, a successful result does not validate, or switch dispatch is uncertain. Do not load it during the normal successful flow.

## Preserve and classify state

- Preserve the last fully validated group snapshot, selected exact ID, whether dispatch was confirmed, and all authentication recovery budgets.
- Treat a top-level JSON-RPC error separately from a tool result. Treat `result.isError: true` as failure even with HTTP 200.
- Trim only surrounding transport whitespace before exact-matching a tool-error text. Do not translate, normalize, or guess future variants.
- If authentication is missing, expired, rejected, or the tool grant is unavailable, read [the host-specific OAuth recovery rules](oauth-recovery.md) completely and apply their single-recovery budgets.

## Discovery failures

- A malformed or empty `group_options` result, malformed entry, or missing/non-unique current entry is a server anomaly. Do not present choices or call `account_switch_group`; report the invalid result and retry only from a new fresh discovery.
- Authentication failure during discovery follows the OAuth reference. After it returns `authentication_recovered`, this reference owns one resumed fresh `group_options` call.

## Conclusive mutation failures

- `選取的工作群組目前沒有可用網域，請先設定網域。`: the switch was atomically rejected and the current selector did not change. Ask the user to choose another group, configure a domain for the target group, or cancel. Do not run domain switching under the still-current group as a repair.
- `找不到可切換的有效帳號群組。`: the target is no longer valid. Refetch `group_options`, discard old numbers, and require a fresh selection. Retry at most once; if the same class repeats, stop.
- `目前的 MCP 帳號授權無法切換群組。`: treat as authentication/client-state failure and follow the OAuth reference. Do not claim the target changed.
- Any other HTTP 200 tool error is a conclusive rejected result but has no documented automatic remediation. Present the readable message, preserve the current selector, and stop unless the user starts a new fresh selection.

## Uncertain mutation results

- HTTP 401 may be retried only when it conclusively occurred before dispatch or the host explicitly confirms no dispatch. Follow the OAuth reference; after it returns `authentication_recovered`, this reference refetches `group_options`, discards old numbers, re-resolves by exact ID, and retries the switch at most once.
- Timeout, connection loss, malformed or incomplete successful output, or any possibly dispatched call is uncertain. Never replay it blindly.
- After any needed host refresh, call `group_options` once and verify whether the selected exact ID has `is_current: true`. If verified, report the current state without replaying. If not verified or still unresolved, show fresh choices and ask before any new attempt.
- A validated `account_switch_group` AccountStatus result commits the selector and never enters this recovery file. Do not make a follow-up lookup after that success.
