# lihi MCP client contract

This document defines the 0.3.2 agent-side contract for the production Streamable HTTP endpoint:

```text
https://app.lihi.io/mcp/v1/tools
```

Codex and Claude Code own transport and OAuth. Each plugin registers one MCP server and exposes the same six tools through four skills. `tools/list` advertises `_meta["lihi/plugin"].minVersion` as `0.3.2`.

Requests containing an `Origin` header are not rejected solely for that header. This contract does not claim complete browser or CORS support.

## Common result handling

- Prefer `result.structuredContent`. If absent, parse a JSON object from the first text content block.
- Treat `result.isError:true` as failure even when HTTP is 200.
- Treat top-level JSON-RPC errors separately from tool-result errors.
- Reject malformed fields instead of inferring values.
- All display strings and selector identities are case-sensitive and are preserved exactly unless a fallback is explicitly defined here.

## Tools

### `site_create`

Input is exactly:

```json
{"url":"https://example.com/long"}
```

`url` is the only required property. The output contains `short_url` and `long_url`. Both must be absolute HTTP(S) URLs without embedded user information, and `long_url` must exactly equal the submitted value.

The operation is non-idempotent. The server does not reuse an existing long URL: every accepted call creates a new record and generated alias. The client therefore calls once per unique fresh URL in a conversation batch and never replays an uncertain dispatch.

### `account_status`

Input is `{}`. Output is exactly the AccountStatus shape:

```json
{
  "email": "non-empty string",
  "group_name": "string or null",
  "domain": "string or null",
  "short_urls": {"used": 0, "quota": "non-negative integer or null"},
  "plan": {
    "name": "string",
    "expires_on": "YYYY-MM-DD or null",
    "next_renewal_on": "YYYY-MM-DD or null"
  }
}
```

`quota:null` means unlimited. Null dates do not imply cancellation or payment failure. `group_name` is display-only: render `group_name:null` as `我的群組`, but never infer a numeric group ID from it. Preserve `email` and non-null `group_name` and `domain` exactly.

For a full Chinese status, render in this order:

1. `帳號 Email：<email>`.
2. `短網址用量：<used> / <quota>`; null quota → `無上限`.
3. `目前方案：<name>（到期日：<expires_on>）`; null expiration → `目前方案：<name>（無到期日）`.
4. `續訂日期：<next_renewal_on>`; null → `續訂日期：-`.
5. `目前工作群組：<group_name>`; null → `目前工作群組：我的群組`.
6. `目前短網址網域：<domain>`; null → `目前短網址網域：未回傳可用網域`.

Show pricing guidance only when usage, plan, or renewal is included.

### `group_options`

Input is `{}`. Output is:

```json
{"groups":[{"id":null,"name":"我的群組","is_current":true}]}
```

Every item requires:

- `id`: integer `1..4294967295` or `null`.
- `name`: string or `null`.
- `is_current`: boolean.

The client requires a non-empty list and exactly one current entry. Treat `id` as internal identity. Preserve all non-null names byte-for-byte. Only null names receive client fallbacks: null ID → `我的群組`; integer ID → `未命名工作群組`. Keep duplicate and unnamed entries separate with contiguous display numbers. Never include group IDs in assistant-written lists, confirmations, diagnostics, or copied tool payloads; classify raw errors before omitting IDs from displayed diagnostics.

While awaiting a switch selection, a bare integer is only a number from that exact menu, never an ID or numeric group name. Without a current switch menu, fetch and present choices. Account-list numbers cannot authorize a later switch. Explicitly supplied names or IDs may be resolved against fresh options, but IDs are never offered as an input method or echoed. This presentation rule does not remove IDs from the MCP response or required selector arguments; host-rendered tool traces are outside the skill's control.

### `account_switch_group`

Input is exactly `{group_id:<id>}`, where the value comes from a fresh `group_options` result and may be `null`. Output is AccountStatus.

Successful output commits the selector and is displayed directly without a follow-up lookup. A changed selector revokes the current access token but leaves normal host refresh available for a later request.

`選取的工作群組目前沒有可用網域，請先設定網域。` is an atomic rejection and leaves the old group/domain unchanged.

### `domain_options`

Input is `{}`. Output is:

```json
{"domains":[{"hostname":"go.example.com","type":"owned"}]}
```

Each entry requires only:

- `hostname`: non-empty string, at most 253 characters.
- `type`: `owned` or `public`.

For display and number binding, stable-sort owned before public, preserve server order within type, then deduplicate exact case-sensitive hostnames and keep the first. The API cannot select duplicate rows independently; server resolution also prefers owned for the same hostname.

In Chinese selection lists, render `owned` as `專屬網域 (owned)` and `public` as `公用網域 (public)`. After the numbered options, append `建議選擇專屬網域，有助於增加信任度。` and `專屬網域說明：https://lihidomain.com/`, even if all available options are public; then ask for the option number or hostname. This guidance is non-selecting workflow metadata and is never shortened or included in unrelated outbound content.

### `account_switch_domain`

Input is exactly `{domain:<hostname>}` using the exact case-sensitive hostname from fresh `domain_options`. Do not trim, normalize, lowercase, or derive another selector. Output is AccountStatus. A successful switch requires `domain` to be a non-null string exactly equal to the submitted hostname; null or mismatch is invalid and enters uncertain-switch recovery.

Successful output commits the selector and is displayed directly without another lookup. Re-selecting the same hostname is idempotent; changing it revokes the current access token.

## Skill routing

- General account status, account email, usage, plan, current group, or current domain → `account_status`.
- Available work-group list → `group_options`.
- Requests covering both status/current selectors and available groups → both read-only tools.
- Group mutation → fresh `group_options`, then `account_switch_group`.
- Domain mutation → fresh `domain_options`, then `account_switch_domain`.
- Current outbound-copy snapshot during revision or before release → local URL detector, then automatic `site_create` calls for fresh unique URLs.

## Automatic shortening state

A batch is the detector's first-seen unique URLs for one exact content snapshot, minus exact confirmed short URLs and exact long URLs with reusable confirmed mappings in the current conversation.

- The inspected snapshot need not be final or stable before shortening. Later edits retain confirmed short URLs and mappings, then form a new batch containing only newly eligible long URLs.
- Disclose the fresh batch once before the first call; this is not a confirmation prompt.
- Duplicate occurrences share one call and mapping.
- Keep the cumulative confirmed ledger private and conversation-scoped.
- After success, display the current updated content snapshot and a separate current-batch mapping list.
- On a documented group/account/domain termination, stop the batch and external release, display the exact unmodified inspected snapshot, and make no selector call or automatic retry. Retain earlier validated mappings privately for a later run, but do not apply or disclose them in the terminated run.
- The disclosure, pricing guidance, and mapping list are workflow metadata and are never detected, shortened, or published.
- A new conversation cannot determine previous mappings and may create another permanent short URL.
- Final-content confirmation remains mandatory only for an explicitly requested external release.

## Exact business-error routing

Trim only surrounding whitespace before matching these Traditional Chinese literals. The server currently supplies no language variants or stable machine-readable error code.

| Source | Exact text | Meaning and action |
| --- | --- | --- |
| `site_create` | `目前的 access token 沒有可用的預設 domain。` | Current group is gone or account is disabled; stop shortening, return the original snapshot, and suggest an explicit `lihi-switch-group` request, then `lihi-account` if no group is available. |
| `site_create` | `access token 的預設 domain 已不在目前可用網域清單中。` | Current domain is unavailable; stop shortening, return the original snapshot, and suggest an explicit `lihi-switch-domain` request. |
| `account_switch_domain` | `目前工作群組已無法使用。` | Hand off to group-switch remediation once. |
| `account_switch_domain` | `偵測到其他 tool call 已更新 MCP 帳號設定，請重新選擇 domain。` | Refetch domains and reselect. |
| `account_switch_domain` | `指定的 domain 不在目前工作群組的可用網域清單中。` | Refetch domains; do not infer group failure. |
| `account_switch_domain` | `目前的 MCP 帳號授權無法切換網域。` | Authentication/client-state failure. |

Exact work-group quota messages `The URL has reached the maximum limit specified by the workgroup`, `網址已達工作群組限定的最大上限`, and `网址已达工作群组限定的最大上限` stop shortening, return the original snapshot, and suggest an explicit `lihi-switch-group` request. Account quota messages `You have reach the maximum URLs you can create`, `網址已達上限`, and `网址已达上限` retain the pricing/resolve/unchanged/cancel flow and `https://knowledge.lihi.io/pricing`; do not scan that guidance URL.

Unknown text follows generic error handling. Do not silently route a future localization to a selector skill.

## Retry and OAuth state machine

- All skills use callable tools directly and available host discovery only for a missing required tool. Switch skills route failures through error recovery; account and shortening route tool unavailability or authentication signals to their recovery reference. Shortening always completes local detection first. Resource listings are not tool listings.
- Tool absence, a server `tools/list` omission, or JSON-RPC `Unknown tool name.` alone is not evidence of missing authorization or a legacy grant. Check available read-only connection status and distinguish loading/filtering/configuration failures from an underlying authentication error. Attempt host tool discovery at most once per availability failure; do not fabricate a tool or change configuration to expose it.
- A validated switch is never replayed or verified with another lookup.
- A switch 401 may be retried once only when non-dispatch is conclusive; refetch options and re-resolve by stable ID or exact hostname first.
- A possibly dispatched switch is not replayed. Verify once with `group_options.is_current` for group or `account_status.domain` for domain, then require a fresh choice if unresolved.
- A possibly dispatched `site_create` is never replayed or converted into confirmed state.
- Switch OAuth references recover authentication and return control without calling lihi tools. Switch error-recovery references alone own the fresh discovery, read-only verification, or permitted retry.
- Per authentication incident, allow one host refresh, one qualifying interactive authentication stage with its documented host fallback, and one resumed logical operation. A qualifying refresh failure may enter interactive authentication and does not count as failure of the resumed operation. Failed/unconfirmed interactive authentication or authentication failure during the resumed operation stops automatic recovery without another refresh/login cycle. Fresh switch options and the permitted verification or retry belong to the single resumed logical operation.
- Interactive reauthentication is limited to an HTTP 401 refresh-token exchange or explicit invalid/expired/revoked/unusable refresh-token error. `invalid_grant` qualifies only in that exchange.
- Initial authentication requires the host to confirm no prior authorization exists. Unknown state and `Auth required` alone do not qualify. A refreshed tool catalog also does not prove authentication recovered.
- Tool resolution with no outstanding authentication failure returns directly to the pending normal flow, under its dispatch rules, without authentication confirmation or consuming an authentication budget. An outstanding authentication failure still requires authentication recovery; a newly available tool cannot clear it.
- Host-managed refresh is not an agent-callable lihi tool or a login command. If the host cannot perform or confirm refresh, preserve the interrupted operation and report that recovery is unconfirmed; do not return `authentication_recovered` or start interactive login as a fallback.
- A stored credential missing its authorization-server issuer or unable to bind to that issuer blocks host refresh. This is a host credential-binding failure, not proof that the refresh token itself is invalid. Preserve selector and dispatch state, report that host authorization-state repair is needed, and do not automatically refresh, log in, modify credentials, or resume the operation.
- Switch OAuth recovery returns `authentication_not_recovered` when recovery is blocked or unconfirmed; the caller must not resume discovery, verification, or mutation. Account recovery preserves any separately successful lookup. Shortening recovery never calls initial authorization an expired session or announces login before it starts.

Codex diagnostics such as `stored OAuth refresh credentials could not be bound to their issuer` and `OAuth refresh credentials for server lihi are missing an authorization server issuer` belong to that credential-binding branch, even when the host also says `authorization required`. A later `invalid_token` or unavailable tool catalog does not turn those diagnostics into an invalid-refresh-token response. Selector changes intentionally revoke the old access token, so this host failure can become visible immediately after a successful switch.

### OAuth interactive authentication — Codex

Use `codex mcp login lihi` once when shell execution is available. If it cannot start or complete, ask the user to run the same command. Use **MCP settings → lihi → Authenticate** only when the command is unavailable.

### OAuth interactive authentication — Claude Code

Ask the user to open `/mcp`, select the lihi plugin server, and choose **Authenticate**. Do not run or recommend a Codex command.

## Compaction and release

Missing exact content, detector offsets, confirmed mapping, uncertain dispatch state, selector snapshot, target identity, recovery budget, or release intent fails closed. Recover or reacquire the state before mutation. Never publish a partial replacement or infer release permission from copy revision alone.
