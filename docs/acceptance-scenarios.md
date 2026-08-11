# Acceptance scenarios

These scenarios apply to both production host bundles and their generated develop counterparts. Use mocks or dry runs for mutations; do not create production links or change production selectors during validation.

## A. Bundle and discovery

| ID | Scenario | Expected result |
| --- | --- | --- |
| A1 | Inspect either host bundle | Exactly four skills and one shared OAuth MCP registration exist. |
| A2 | Inspect tool metadata | Six current tools are documented and minimum plugin version is 0.3.1. |
| A3 | Build develop artifact | Four `-dev` skills, `lihi-dev` identities, and develop endpoint appear; production runtime remains unchanged. |
| A4 | Inspect requests with `Origin` | The contract does not reject solely because `Origin` is present and does not overclaim browser support. |

## B. Account status

| ID | Request/result | Expected result |
| --- | --- | --- |
| B1 | General account status | Call only `account_status`; show usage, plan, renewal, group, and domain in order. |
| B2 | Current group or current domain | Call only `account_status`; show only requested selector lines and no pricing guidance. |
| B3 | Available groups | Call only `group_options`; require one current entry and list requested choices. |
| B4 | Status plus available groups | Call both read-only tools; preserve a valid section if the other fails. |
| B5 | Null status values | Render unlimited/no-expiration/dash-renewal/personal-group/unknown-domain text; `next_renewal_on:null` becomes `續訂日期：-`, and `group_name:null` becomes `目前工作群組：我的群組` without inferring a numeric ID. |
| B6 | Non-null server labels | Preserve `group_name`, domain, and option names exactly; do not append a personal suffix. |

## C. Group switching

| ID | Scenario | Expected result |
| --- | --- | --- |
| C1 | User asks to switch groups | Fetch fresh `group_options` before presenting or resolving a target. |
| C2 | Only one current entry exists | Report the only group and make no mutation call. |
| C3 | Duplicate names or null names | Keep duplicate names separate by ID; apply only the documented null fallbacks. |
| C4 | Valid selection | Send the exact ID, including null, to `account_switch_group`; display returned AccountStatus without lookup. |
| C5 | Target has no domain | Treat the exact error as atomic rejection; offer another group/configuration/cancel, not domain switching under the old group. |
| C6 | Possibly dispatched switch | Never replay blindly; verify the target ID once with fresh `group_options.is_current`. |

## D. Domain switching

| ID | Scenario | Expected result |
| --- | --- | --- |
| D1 | User says「更換短網址網域」 | Trigger `lihi-switch-domain` and fetch `domain_options` first. |
| D2 | User merely reads a URL | Do not trigger domain switching. |
| D3 | Mixed/duplicate options | Sort owned before public, preserve within-type order, deduplicate exact hostname, keep owned for cross-type duplicates, and label types as `專屬網域 (owned)` / `公用網域 (public)` in Chinese. |
| D4 | Selection list, including public-only options | Use the complete numbered prompt, append the dedicated-domain recommendation and `https://lihidomain.com/`, then ask for a number or hostname without selecting an option or shortening the guidance URL. |
| D5 | Hostname selection | Pass the exact case-sensitive hostname as `{domain}`; never normalize it or send an opaque selector. |
| D6 | Successful switch | Require returned domain to be non-null and exactly equal the submitted hostname; display full AccountStatus without lookup. |
| D7 | Concurrent/stale selector error | Refetch domains and require a fresh choice; old numbers are invalid. |
| D8 | Current group unavailable | Hand off once to group switching; for explicit domain change, refetch domains after group recovery. |
| D9 | Possibly dispatched switch | Verify once with `account_status.domain`; never blindly replay. |

## E. Automatic shortening

| ID | Scenario | Expected result |
| --- | --- | --- |
| E1 | A current outbound-copy snapshot contains two URLs | Detect and create without waiting for the copy to be final or stable; disclose both and automatically create each unique fresh URL. |
| E2 | Same URL occurs multiple times | Call `site_create` once and replace all occurrences from the immutable snapshot. |
| E3 | Confirmed short URL is detected later | Preserve it and make no create call. |
| E4 | Confirmed long URL returns in the same conversation | Reuse its mapping automatically; do not call create again. |
| E5 | Same long URL appears in a new conversation | Do not claim reuse; server may create a new permanent short URL. |
| E6 | Successful batch | Show the current updated content snapshot and only the current batch's new mappings outside the content. |
| E7 | All mappings are reused | Make no create call and state that no new short URLs were created. |
| E8 | User edits content before dispatch | Discard stale disclosure/offsets, re-detect, rebuild, and disclose the changed batch. |
| E9 | Copy-only request | Show result without publishing. |
| E10 | Explicit release request | Release only after confirmation of the exact complete content; exclude workflow metadata. |
| E11 | User edits content after confirmed creation | Preserve confirmed short URLs, reuse confirmed mappings, and create only newly eligible long URLs in the new snapshot. |

## F. URL and failure safety

| ID | Scenario | Expected result |
| --- | --- | --- |
| F1 | Credential-bearing destination | Make no MCP call, block release, and redact copy-only output. |
| F2 | Detector failure | Make no MCP call; block release and warn on copy-only output. |
| F3 | `site_create` success with mismatched `long_url` | Reject result and do not replace content. |
| F4 | Timeout, 429, connection loss, malformed or incomplete create result | Record uncertainty, never replay, and never release partial content. |
| F5 | Account quota failure | Preserve original, show pricing guidance outside content, and ask retry-after-resolution/unchanged/cancel. |
| F6 | User chooses unchanged after a failure | Mark a snapshot-local exception so automatic processing does not immediately retry. |
| F7 | No usable default-domain literal | Classify as unavailable group/account; stop the batch and release, make no selector call or retry, suggest explicit group switching/account status, and show the exact original snapshot. |
| F8 | Stale default-domain literal | Classify as unavailable domain; stop the batch and release, make no selector call or retry, suggest explicit domain switching, and show the exact original snapshot. |
| F9 | Work-group quota failure | Stop the batch and release, suggest explicit group switching, and show the exact original snapshot. |
| F10 | Earlier URLs succeeded before F7–F9 | Keep validated mappings private for a later run, stop remaining calls, apply no mapping to the original snapshot, and show no mapping or side-effect summary. |

## G. Authentication recovery

| ID | Scenario | Expected result |
| --- | --- | --- |
| G1 | Ordinary tool 401/Auth required | One host-managed refresh and at most one resumed operation. |
| G2 | Invalid/expired/revoked/unusable refresh token | At most one interactive reauthentication; unrelated readable errors do not start login. |
| G3 | Switch authentication recovery | OAuth reference performs authentication only; error recovery alone owns fresh discovery, verification, or a permitted retry. |
| G4 | Second authentication failure in the incident | Stop with state preserved. |
| G5 | Codex interactive recovery | Run `codex mcp login lihi` once when available, then user-command fallback, then settings fallback only if unavailable. |
| G6 | Claude Code interactive recovery | Open `/mcp`, select lihi, and choose **Authenticate**; never reference Codex commands. |
| G7 | No create succeeded or may have dispatched | State in the user's language that no link was created or published; Chinese includes `目前尚未建立或發布任何連結。` |

## H. Static and package invariants

- Both detector scripts and both shortening workflows are byte-identical; detector syntax parses as Python 3.8.
- Codex metadata for all four skills points to the one production `lihi` MCP dependency; develop metadata points to `lihi-dev`.
- `DEVELOP_BUILD.skill_names` lists all four develop skills in canonical order; both singular aliases equal the first item.
- Active runtime and generated artifacts contain none of the removed selector/request fields or superseded skill/tool identities.
- Production runtime contains no develop endpoint or identity; develop runtime contains no production endpoint or runtime identity.
- English and Traditional Chinese guides remain language-separated, and plugin-internal guides contain no installation commands.
