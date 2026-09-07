---
name: lihi-account
description: Read lihi account status, email, short URL usage and subscription, current work group or domain, and available work groups. Use for「帳號資訊」、「帳號狀態」、「帳號 email」、「額度」、「訂閱」or questions about current selectors and available groups. Switching belongs to `lihi-switch-group` or `lihi-switch-domain`.
---

# lihi account information

Always render the brand name exactly as `lihi` in lowercase in every user-facing message and generated copy.

Keep group IDs internal: use them only for identity matching and required MCP arguments. Never display or echo them in lists, confirmations, errors, or copied tool payloads. Use group names and snapshot-local menu numbers in user-facing output. Classify raw errors before removing any group IDs from displayed diagnostics.

## Choose the minimum tools

- Call `account_status` with `{}` for general account information or status, account email, usage, quota, plan, expiration, renewal, the current work group, or the current short URL domain.
- Call `group_options` with `{}` only when the user asks which work groups are available or asks for the group list.
- Call both only when the request asks for account status or a current selector and also asks for available groups. Run the independent calls in parallel when the host permits.

Call tools directly when available; use host tool discovery only for a missing required tool. Do not call `account_switch_group` or `account_switch_domain`; switching belongs to `lihi-switch-group` and `lihi-switch-domain`.

## Validate results

Prefer `structuredContent`; otherwise parse the JSON object in the first text content block. Treat a top-level JSON-RPC error or `result.isError: true` as failure.

Require `account_status` to contain:

- `email`: a non-empty string.
- `group_name`: a string or `null`.
- `domain`: a string or `null`.
- `short_urls.used`: a non-negative integer.
- `short_urls.quota`: a non-negative integer or `null`; `null` means unlimited.
- `plan.name`: a string.
- `plan.expires_on`: a `YYYY-MM-DD` string or `null`.
- `plan.next_renewal_on`: a `YYYY-MM-DD` string or `null`.

Require `group_options.groups` to be a non-empty array whose entries contain an `id` of `null` or an integer from `1` through `4294967295`, string-or-null `name`, and boolean `is_current`. Reject the complete result unless exactly one entry is current. Treat `id` as identity and `name` only as a display label.

If a required tool is unavailable or an authentication signal is reported, read [the Claude Code OAuth recovery rules](references/oauth-recovery.md) before recovery. Invalid successful output is a response anomaly, not an authentication signal; report it without inventing missing fields or starting login.

## Present the answer

Show only requested fields. For a general account-status request, show all six lines in this order:

1. `帳號 Email：<email>`.
2. `短網址用量：<used> / <quota>`; render `quota:null` as `短網址用量：<used> / 無上限`.
3. `目前方案：<plan>（到期日：<expires_on>）`; render `expires_on:null` as `目前方案：<plan>（無到期日）`.
4. `續訂日期：<next_renewal_on>`; render null as `續訂日期：-`.
5. `目前工作群組：<group_name>`; render null as `目前工作群組：我的群組`.
6. `目前短網址網域：<domain>`; render null as `目前短網址網域：未回傳可用網域`.

Preserve `email` and every non-null `group_name` and `domain` exactly. Treat `group_name:null` as the personal-group display label `我的群組`, but never infer a numeric group ID from it. Do not infer missing domain configuration, cancellation, or payment failure from another null value. When usage, plan, or renewal is shown, append `訂閱方案說明：https://knowledge.lihi.io/pricing`; omit it for email/group/domain-only answers.

For `group_options`, render every non-null `name` byte-for-byte without suffixes or normalization. Synthesize a label only for a null name:

- `{id:null,name:null}`: `我的群組`.
- `{id:<integer>,name:null}`: `未命名工作群組`.

Keep duplicate and unnamed groups as separate entries. Number displayed groups contiguously in returned order; numbers are presentation labels, not IDs or reusable switch selections. A later switch must fetch its own options. List non-current groups only when requested. If one of two requested lookups fails, present the validated section and clearly identify the unavailable section without inventing data.
