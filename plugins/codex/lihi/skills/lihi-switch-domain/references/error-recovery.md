# lihi domain-switch error recovery

Read this file completely only when `domain_options` or `account_switch_domain` cannot be resolved or fails, a successful result does not validate, or switch dispatch is uncertain. Do not load it during the normal successful flow.

## Preserve and classify state

- Preserve the last fully validated domain snapshot, selected exact case-sensitive hostname, caller workflow, whether dispatch was confirmed, and all authentication and selector-remediation budgets.
- Treat a top-level JSON-RPC error separately from a tool result. Treat `result.isError: true` as failure even with HTTP 200.
- Trim only surrounding transport whitespace before exact-matching a tool-error text. Do not translate, normalize, or guess future variants.
- Enter authentication recovery only with a host/server authentication signal or evidence of a legacy token missing the required tool grant, after the tool-availability classification below. Read [the host-specific OAuth recovery rules](oauth-recovery.md) completely before authentication recovery; that reference decides whether refresh or interactive authentication is warranted.

## Tool availability before authentication

- A tool absent from the current callable catalog is not proof of missing authorization or a missing tool grant. Use the host's tool discovery once if available and not already attempted for this failure. If the tool becomes callable, return to the interrupted flow under the preserved dispatch rules; resolving a tool does not prove authentication recovered.
- If it remains unavailable, report that the host has not exposed the required tool and preserve the selector snapshot and dispatch state. Use available read-only MCP connection status to distinguish pending startup, a disabled/filtered tool, or a failed connection. An empty resource listing does not establish tool availability. Do not fabricate a tool call, change host configuration, or start login solely to make a tool appear.
- A server `tools/list` omission or JSON-RPC `Unknown tool name.` alone does not establish a legacy grant: an unregistered name and a missing grant can produce the same result. Without evidence of a legacy grant or an authentication signal, report the discovery/configuration mismatch and stop without refresh or login.
- A tool-endpoint HTTP 401 or host-level `Auth required` is an authentication signal, not proof that no prior authorization exists or that the refresh token is invalid. A failed MCP connection can also remove tools from the host catalog; classify the underlying error before choosing recovery.

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
- A validated `account_switch_domain` AccountStatus result with the exact returned domain commits the selector and never enters this recovery file. Do not make a follow-up lookup after that success.
