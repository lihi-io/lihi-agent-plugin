---
name: lihi-switch-group
description: Switch the active lihi MCP work group. Use when the user asks to switch, change, select, or move to another lihi work group, including「切換 lihi 工作群組」、「切換工作群組」or「換到另一個群組」in a lihi context, and when another lihi workflow hands off a confirmed group-unavailable error. Always fetch `group_options`, submit only an exact returned ID to `account_switch_group`, and display its AccountStatus result without a follow-up lookup.
---

# Switch the lihi work group

Always render the brand name exactly as `lihi` in lowercase in every user-facing message and generated copy.

## Flow

1. Resolve `group_options` from the host's callable tools, using its tool discovery if needed, then call it with `{}` and validate the complete fresh snapshot.
2. Stop without mutation when only one group exists or when the requested target is already current.
3. Resolve an explicitly named target against the fresh snapshot. Otherwise show the current group and numbered alternatives, then wait for one valid selection or cancellation.
4. Call `account_switch_group` once with the selected entry's exact `id` as `group_id`.
5. On success, validate and display the returned AccountStatus directly, then complete the group-switch operation without a follow-up MCP call. For a standalone request, stop; when domain-switch error recovery invoked this skill, return control to that caller after display.
6. If a required tool cannot be resolved, discovery or mutation fails, successful output does not validate, or dispatch is uncertain, leave the normal flow and read [the switch error recovery rules](references/error-recovery.md) completely before taking another action.

## Fetch and validate current choices

Call `group_options` with `{}` before every selection. Never switch from a remembered list.

Prefer `structuredContent`; otherwise parse the JSON object in the first text block. Require a non-empty `groups` array and exactly one current entry. Every entry must contain:

- `id`: `null` or an integer from `1` through `4294967295`.
- `name`: a string or `null`.
- `is_current`: a boolean.

Treat `id` as identity. Preserve every non-null `name` byte-for-byte. Render only null names as `{id:null}` → `我的群組` or `{id:<integer>}` → `未命名工作群組（ID：<id>）`. Keep duplicate names as distinct entries.

If there is exactly one entry, report `目前只有一個工作群組：<label>` and stop without mutation.

## Resolve the target

For multiple entries, exclude the current entry from the selectable list and preserve returned order. Resolve a user-supplied target only by exact ID, an exact unique non-null name, or `我的群組` matching the personal entry. If it is current, report that state and stop. Otherwise display current group plus a contiguous numbered list and ask for one number or `取消`; ask even when only one alternative exists.

Bind numbers only to this exact `group_options` snapshot. Invalid or ambiguous input re-displays the same list. Any refresh or new discovery invalidates every old number. A fresh target must resolve by ID, never by old number or display label.

## Switch and validate

Call `account_switch_group` once with `{group_id:<exact returned id>}`, preserving `null`. Never send a display number.

Validate a successful response as AccountStatus:

- `email`: a non-empty string.
- `group_name` and `domain`: string or `null`.
- `short_urls.used`: non-negative integer; `short_urls.quota`: non-negative integer or `null`.
- `plan.name`: string; `plan.expires_on` and `plan.next_renewal_on`: `YYYY-MM-DD` string or `null`.

A valid result commits the selector. Do not call `group_options`, `account_status`, or another MCP tool to verify it, and never infer an ID from `group_name`.

Display the full returned status in this order:

1. `帳號 Email：<email>`.
2. `短網址用量：<used> / <quota>`; render `quota:null` as `短網址用量：<used> / 無上限`.
3. `目前方案：<plan>（到期日：<expires_on>）`; render `expires_on:null` as `目前方案：<plan>（無到期日）`.
4. `續訂日期：<next_renewal_on>`; render null as `續訂日期：-`.
5. `目前工作群組：<group_name>`; render null as `目前工作群組：我的群組`.
6. `目前短網址網域：<domain>`; render null as `目前短網址網域：未回傳可用網域`.

Preserve `email` and every non-null display value exactly and append `訂閱方案說明：https://knowledge.lihi.io/pricing` because usage and plan are displayed.
