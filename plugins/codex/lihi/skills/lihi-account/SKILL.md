---
name: lihi-account
description: Retrieve and summarize read-only lihi account information. Use for account status; account email; short URL usage, quota, plan, expiration, or renewal; the current lihi work group; the current short URL domain; or available work groups, including Chinese prompts containing「帳號資訊」、「帳號狀態」、「帳號 email」、「額度」、「訂閱」、「工作群組」或「短網址網域」. Use `account_status` for status and current selectors, and `group_options` only when available groups are requested. Do not switch selectors; use `lihi-switch-group` or `lihi-switch-domain`.
---

# lihi account information

Always render the brand name exactly as `lihi` in lowercase in every user-facing message and generated copy.

## Choose the minimum tools

- Call `account_status` with `{}` for general account information or status, account email, usage, quota, plan, expiration, renewal, the current work group, or the current short URL domain.
- Call `group_options` with `{}` only when the user asks which work groups are available or asks for the group list.
- Call both only when the request asks for account status or a current selector and also asks for available groups. Run the independent calls in parallel when the host permits.

Do not call unrelated lihi tools. Do not call `account_switch_group` or `account_switch_domain`; switching belongs to `lihi-switch-group` and `lihi-switch-domain`.

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

Require `group_options.groups` to be a non-empty array whose entries contain a positive-integer-or-null `id`, string-or-null `name`, and boolean `is_current`. Reject zero or negative IDs and reject the complete result unless exactly one entry is current. Treat `id` as identity and `name` only as a display label.

If authentication is missing, expired, or rejected, read [the Codex OAuth recovery rules](references/oauth-recovery.md) completely before recovery, then retry only the interrupted lookup.

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
- `{id:<integer>,name:null}`: `未命名工作群組（ID：<id>）`.

Keep duplicate non-null names as separate entries identified by ID. List non-current groups only when requested. If one of two requested lookups fails, present the validated section and clearly identify the unavailable section without inventing data.
