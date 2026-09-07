# lihi group-switch error recovery

Read this file completely only when `group_options` or `account_switch_group` cannot be resolved or fails, a successful result does not validate, or switch dispatch is uncertain. Do not load it during the normal successful flow.

## Preserve and classify state

- Preserve the last fully validated group snapshot, selected exact ID, whether dispatch was confirmed, and all authentication recovery budgets.
- Treat a top-level JSON-RPC error separately from a tool result. Treat `result.isError: true` as failure even with HTTP 200.
- Trim only surrounding transport whitespace before exact-matching a tool-error text. Classify the raw error internally; omit group IDs from displayed diagnostics. Do not translate, normalize, or guess future variants during classification.
- Tool availability and authentication are separate. Use the observed failure to choose the branch below.

## Resolve a missing tool

Use callable tools directly. For a missing required tool, try host tool discovery once if available and not already attempted for this failure. If resolved with no outstanding authentication failure, return directly to the interrupted normal flow under its dispatch rules. No authentication confirmation or budget is needed. If an authentication failure remains outstanding, route it to OAuth recovery; tool discovery cannot clear it.

If still unavailable, inspect available read-only MCP connection status. Report pending startup, filtering, configuration, or connection failure only when supported. Empty resources, `tools/list` omissions, and `Unknown tool name.` alone establish neither missing authorization nor a legacy grant. Do not invent a call, change configuration, or start login to expose a tool.

An observed authentication signal or confirmed legacy grant failure routes to [the host-specific OAuth recovery rules](oauth-recovery.md). That reference alone decides refresh versus interactive authentication. `Auth required` does not prove no prior authorization exists. If recovery returns `authentication_not_recovered`, stop with state preserved; do not resume discovery, verification, or mutation.

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
- If authentication recovery fails or cannot be confirmed, or the verification tool remains unavailable, stop with dispatch uncertainty preserved. Do not claim that the selector is unchanged or that the switch succeeded.
- After any needed host refresh, call `group_options` once and verify whether the selected exact ID has `is_current: true`. If verified, report the current state without replaying. If not verified or still unresolved, show fresh choices and ask before any new attempt.
