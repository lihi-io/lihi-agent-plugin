---
name: lihi-switch-domain
description: Switch the active lihi short URL domain on an explicit request, including「更換短網址網域」、「切換短網址網域」or「選擇 lihi 網域」. A shortening error alone does not trigger this skill; wait for a new explicit domain-switch request. Do not trigger for merely reading a URL.
---

# Switch the lihi short URL domain

Always render the brand name exactly as `lihi` in lowercase in every user-facing message and generated copy.

Keep group IDs internal: use them only for identity matching and required MCP arguments. Never display or echo them in lists, confirmations, errors, or copied tool payloads. Use group names and snapshot-local menu numbers in user-facing output. Classify raw errors before removing any group IDs from displayed diagnostics.

## Flow

1. Call `domain_options` with `{}` and validate the complete fresh result. Use host tool discovery only if this tool is not callable.
2. Stable-sort owned before public, preserve order within type, and deduplicate exact case-sensitive hostnames.
3. Resolve an explicitly supplied exact hostname against this snapshot. Otherwise show the numbered options and dedicated-domain guidance, then wait for a valid selection. If the user says to cancel, stop without mutation.
4. Call `account_switch_domain` once with the selected exact hostname as `domain`.
5. On success, validate the returned AccountStatus and exact returned domain, display the status directly, and stop without a follow-up MCP call.
6. For an unavailable tool, failed call, invalid result, or uncertain dispatch, read [the switch error recovery rules](references/error-recovery.md) before recovery.

## Fetch and validate options

Call `domain_options` with `{}` before every selection. Never switch from a remembered list.

Prefer `structuredContent`; otherwise parse the JSON object in the first text block. Require a non-empty `domains` array. Require these selection fields on every entry; unrelated fields do not affect selection:

- `hostname`: a non-empty string no longer than 253 characters.
- `type`: exactly `owned` or `public`.

Stable-sort owned entries before public entries while preserving server order within each type. Then deduplicate exact, case-sensitive hostnames and keep the first entry. This mirrors the server selector: duplicate rows are not separately addressable, and owned wins over public for the same hostname.

## Resolve the target

If the user already supplied a hostname, accept it only when it exactly matches one fresh option. Do not trim, lowercase, normalize, or derive an opaque value. Otherwise display the deduplicated options as one contiguous numbered list, label both hostname and type, and ask for one number or an exact hostname. If the user replies `取消`, stop without mutation; the fixed prompt intentionally does not advertise cancellation. Ask even when only one option remains because `domain_options` has no current marker.

For Chinese, map `owned` to `專屬網域 (owned)` and `public` to `公用網域 (public)`. Use this complete prompt whenever asking for a selection, including when every option is public:

```text
請選擇要使用的 lihi 網域：

1. <owned-hostname> — 專屬網域 (owned)
2. <public-hostname> — 公用網域 (public)

建議選擇專屬網域，有助於增加信任度。
專屬網域說明：https://lihidomain.com/

請回覆選項編號（例如 1），也可以回覆網域名稱。
```

Render one numbered line per actual option. The two placeholder lines demonstrate both type labels; omit any type that is not present and keep numbering contiguous.

The guidance is workflow metadata: it does not select an option and must not be sent through URL shortening or included in unrelated outbound content.

Bind numbers only to this exact snapshot. Invalid, conflicting, or ambiguous input re-displays the same list. Any refresh or refetch invalidates old numbers.

## Switch and validate

Call `account_switch_domain` once with `{domain:<exact hostname>}`. Never send a display number, type, or removed `value` field.

Validate a successful response as AccountStatus:

- `email`: a non-empty string.
- `group_name`: a string or `null`.
- `domain`: a non-null string that exactly equals the submitted hostname. A null or mismatched value is invalid and enters error recovery as a possibly dispatched switch.
- `short_urls.used`: a non-negative integer; `short_urls.quota`: a non-negative integer or `null`.
- `plan.name`: a string; `plan.expires_on` and `plan.next_renewal_on`: `YYYY-MM-DD` strings or `null`.

A valid result commits the selector. Do not call `account_status`, `domain_options`, or another MCP tool to verify it. A same-hostname selection is idempotent; a changed hostname may revoke the current access token for the next lihi request.

Display the full returned status in this order:

1. `帳號 Email：<email>`.
2. `短網址用量：<used> / <quota>`; render `quota:null` as `短網址用量：<used> / 無上限`.
3. `目前方案：<plan>（到期日：<expires_on>）`; render `expires_on:null` as `目前方案：<plan>（無到期日）`.
4. `續訂日期：<next_renewal_on>`; render null as `續訂日期：-`.
5. `目前工作群組：<group_name>`; render null as `目前工作群組：我的群組`.
6. `目前短網址網域：<domain>`.

Preserve `email` and every non-null display value exactly, never infer a group ID from `group_name`, and append `訂閱方案說明：https://knowledge.lihi.io/pricing` because usage and plan are displayed.
