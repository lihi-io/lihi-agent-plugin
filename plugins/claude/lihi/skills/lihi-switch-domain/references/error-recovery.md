# lihi domain-switch error recovery

Read this file completely only when `domain_options` or `account_switch_domain` cannot be resolved or fails, a successful result does not validate, or switch dispatch is uncertain. Do not load it during the normal successful flow.

## Preserve and classify state

- Preserve the last fully validated domain snapshot, selected exact case-sensitive hostname, caller workflow, whether dispatch was confirmed, and all authentication and selector-remediation budgets.
- Treat a top-level JSON-RPC error separately from a tool result. Treat `result.isError: true` as failure even with HTTP 200.
- Trim only surrounding transport whitespace before exact-matching a tool-error text. Classify the raw error internally; omit group IDs from displayed diagnostics. Do not translate, normalize, or guess future variants during classification.
- Tool availability and authentication are separate. Use the observed failure to choose the branch below.

## Resolve a missing tool

Use callable tools directly. For a missing required tool, try host tool discovery once if available and not already attempted for this failure. If resolved with no outstanding authentication failure, return directly to the interrupted normal flow under its dispatch rules. No authentication confirmation or budget is needed. If an authentication failure remains outstanding, route it to OAuth recovery; tool discovery cannot clear it.

If still unavailable, inspect available read-only MCP connection status. Report pending startup, filtering, configuration, or connection failure only when supported. Empty resources, `tools/list` omissions, and `Unknown tool name.` alone establish neither missing authorization nor a legacy grant. Do not invent a call, change configuration, or start login to expose a tool.

An observed authentication signal or confirmed legacy grant failure routes to [the host-specific OAuth recovery rules](oauth-recovery.md). That reference alone decides refresh versus interactive authentication. `Auth required` does not prove no prior authorization exists. If recovery returns `authentication_not_recovered`, stop with state preserved; do not resume discovery, verification, or mutation.

## Discovery failures

- A malformed or empty `domain_options` result or malformed entry is a server anomaly. Do not present choices or call `account_switch_domain`; report the invalid result and retry only from a new fresh discovery.
- Authentication failure during discovery follows the OAuth reference. After it returns `authentication_recovered`, this reference owns one resumed fresh `domain_options` call.

## Conclusive mutation failures

- `偵測到其他 tool call 已更新 MCP 帳號設定，請重新選擇 domain。`: refetch `domain_options`, discard old numbers, and require a fresh selection. Retry at most once; if the same class repeats, stop.
- `指定的 domain 不在目前工作群組的可用網域清單中。`: refetch and reselect once. This does not prove the group is unavailable; if the same class repeats, stop.
- `目前工作群組已無法使用。`: hand off once to `lihi-switch-group`. After that skill displays a validated AccountStatus and returns control, refetch `domain_options`, discard the old domain snapshot and numbers, and require a fresh domain selection. This recovery belongs only to the explicit domain-switch workflow; never resume a shortening workflow.
- `目前的 MCP 帳號授權無法切換網域。`: treat as authentication/client-state failure and follow the OAuth reference. Do not reinterpret it as a missing group.
- Any other HTTP 200 tool error is a conclusive rejected result but has no documented automatic remediation. Present the readable message, preserve the current selector, and stop unless the user starts a new fresh selection.

## Uncertain mutation results

- HTTP 401 may be retried only when it conclusively occurred before dispatch or the host explicitly confirms no dispatch. Follow the OAuth reference; after it returns `authentication_recovered`, this reference refetches `domain_options`, discards old numbers, re-resolves the exact hostname, and retries the switch at most once.
- Timeout, connection loss, malformed or incomplete successful output, returned-domain null or mismatch, or any possibly dispatched call is uncertain. Never replay it blindly.
- If authentication recovery fails or cannot be confirmed, or the verification tool remains unavailable, stop with dispatch uncertainty preserved. Do not claim that the selector is unchanged or that the switch succeeded.
- After any needed host refresh, call `account_status` once and compare its exact `domain` with the selected hostname. If verified, report the current state without replaying. If not verified or still unresolved, show fresh options and ask before any new attempt.
