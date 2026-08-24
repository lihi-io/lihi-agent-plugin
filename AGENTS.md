# Repository guide for agents

These instructions apply to the entire repository.

## Documentation audience

- `README.md` is the English production guide; `README.zh-TW.md` is Traditional Chinese. Keep installation, authentication, normal interaction, updates, restarts, and new-conversation guidance there.
- Keep protocol, implementation, packaging, validation, and CI detail in this file or `docs/`.
- Plugin-internal READMEs describe installed capabilities and host-specific authentication without installation steps.
- Always render the brand exactly as `lihi` in lowercase.

## Purpose and identities

This repository packages one lihi plugin for Codex and one for Claude Code. Each has four skills behind one host-managed OAuth MCP registration:

| Capability | Production | Develop artifact |
| --- | --- | --- |
| Marketplace / plugin / MCP | `lihi` | `lihi-dev` |
| Shortening | `lihi-shorten` | `lihi-shorten-dev` |
| Account status | `lihi-account` | `lihi-account-dev` |
| Group switch | `lihi-switch-group` | `lihi-switch-group-dev` |
| Domain switch | `lihi-switch-domain` | `lihi-switch-domain-dev` |

Production endpoint: `https://app.lihi.io/mcp/v1/tools`.
Develop endpoint: `https://app.lihidev.com/mcp/v1/tools`.

Checked-in runtime files must remain production-only. Develop identities and endpoints may appear in packaging code, CI, tests, and generated artifacts. The server advertises minimum plugin version `0.3.1` through `tools/list` metadata.

## Host and skill responsibilities

- Each host bundle owns exactly one `.mcp.json` and one logical MCP server key.
- `lihi-account` uses `account_status` for general status and current group/domain; it uses `group_options` only for available-group listings.
- `lihi-switch-group` fetches fresh `group_options`, selects by exact ID, calls `account_switch_group`, and displays its AccountStatus result without a follow-up lookup.
- `lihi-switch-domain` runs only after an explicit user request, fetches fresh `domain_options`, selects by exact hostname, calls `account_switch_domain`, and displays its AccountStatus result without a follow-up lookup. In Chinese selection lists, label owned as `專屬網域 (owned)` and public as `公用網域 (public)`, recommend a dedicated domain, and show `https://lihidomain.com/` as non-selecting workflow metadata.
- Switch `SKILL.md` files contain only the normal flow and one failure handoff. Load their `references/error-recovery.md` only after a tool failure, invalid successful output, or uncertain dispatch; that reference loads host-specific OAuth rules only for an authentication branch.
- `lihi-shorten` runs the local detector on the current outbound-copy snapshot during revision or before release and automatically creates every eligible new unique URL.
- OAuth references are host-specific. Codex uses `codex mcp login lihi` when interactive authentication is required and available; Claude Code uses `/mcp` and **Authenticate**.
- Codex `agents/openai.yaml` declares UI metadata and the shared MCP dependency.

The Codex and Claude detector scripts, shortening workflow references, and matching switch error-recovery references must remain byte-for-byte identical. Detector code must remain executable and Python 3.8-compatible. Other skill files need semantic parity while preserving host-specific OAuth wording.

## Authorization boundaries

Keep these decisions independent:

1. OAuth grants access to lihi tools; it does not authorize content release.
2. Automatic shortening applies to every eligible new URL in the exact inspected outbound-content snapshot.
3. Group selection applies only to the latest `group_options` snapshot.
4. Domain selection applies only to the latest `domain_options` snapshot.
5. External release occurs only after an explicit release request and confirmation of the exact complete final content.

Creation disclosure and the current-batch mapping summary are workflow metadata. Never scan, shorten, publish, or include them in the confirmed content snapshot.

## Copy revision and shortening

1. Intercept any external action first. Do not wait for the rewrite or polish to finish before detecting or creating short URLs.
2. Run the bundled local detector against the exact current human-visible content snapshot; it need not be final or stable. It accepts valid HTTP(S) URLs up to 2048 characters, uses Unicode code-point offsets, rejects embedded credentials and malformed destinations, and excludes code by default.
3. Detector failure blocks release. Embedded credentials block every MCP call and release until replaced; copy-only output redacts the unsafe destination.
4. Exclude exact confirmed short URLs and reuse exact confirmed long→short mappings from the current conversation. Duplicate occurrences share one result.
5. Build the fresh creation batch in detector order, disclose it without asking a question, then call `site_create` once per unique URL with exactly `{url}`.
6. Validate exact matching `long_url` and a safe HTTP(S) `short_url` before replacement. Apply replacements from the end of the immutable snapshot.
7. Keep the cumulative ledger internal. If content changes after creation, preserve confirmed short URLs and reuse confirmed long→short mappings in the next snapshot; process only newly eligible long URLs. After a successful batch, report only mappings newly created in that batch beside the displayed content. A new conversation has no reuse lookup and creates a new short URL for the same long URL.
8. Never release partially replaced or unresolved content. A user may intentionally keep a failed URL unchanged for that exact snapshot; record the exception so automatic processing does not immediately repeat it.
9. A documented group/account/domain termination stops the entire batch and external release, makes no selector call or automatic retry, and displays the exact unmodified inspected snapshot. Keep earlier validated mappings in the ledger for a later run, but do not display or apply them in the terminated run.

Source code, configuration, tests, logs, docs, changelogs, code comments, research, and link reading do not trigger shortening unless explicitly identified as outbound human-facing copy.

## MCP contract

| Tool | Input | Result | Client rule |
| --- | --- | --- | --- |
| `site_create` | `{url}` | `{short_url,long_url}` | Non-idempotent; no server-side long-URL reuse. |
| `account_status` | `{}` | AccountStatus | Account email, current status, group name, and domain. |
| `group_options` | `{}` | `groups[{id,name,is_current}]` | Non-empty; exactly one current; select by ID. |
| `account_switch_group` | `{group_id}` | AccountStatus | Use only a fresh returned ID, including `null`. |
| `domain_options` | `{}` | `domains[{hostname,type}]` | Owned-first presentation; exact-hostname selection. |
| `account_switch_domain` | `{domain}` | AccountStatus | Pass an exact case-sensitive returned hostname. |

AccountStatus requires a non-empty `email:string`, `group_name:string|null`, `domain:string|null`, `short_urls.used`, nullable `short_urls.quota`, and `plan.name`, nullable `plan.expires_on`, and nullable `plan.next_renewal_on`.

- Prefer `structuredContent`; parse the first text JSON block only as compatibility fallback.
- Treat `result.isError:true` as failure even with HTTP 200, and keep top-level JSON-RPC errors separate.
- For a general account-status response, display `帳號 Email：<email>` first and preserve the value exactly.
- Render `plan.next_renewal_on:null` as `續訂日期：-`.
- Preserve non-null group/domain display values exactly. Render `group_name:null` as `我的群組`, but do not infer a numeric selector ID from it.
- For group options, preserve non-null names. Synthesize `我的群組` only for null personal names and `未命名工作群組（ID：x）` only for null named-group labels.
- Stable-sort domains owned before public, preserve order within type, and deduplicate exact hostname after sorting. The server's hostname-only selector also prefers owned for duplicates.
- A valid switch response commits the selector. Do not make a follow-up status lookup. For `account_switch_domain`, the returned `domain` must be a non-null string exactly equal to the submitted hostname.

## Failure and recovery safety

- Never replay a possibly dispatched `site_create`. Timeout, connection loss, HTTP 429, malformed output, or incomplete output may have created a link.
- Exact `site_create` error `目前的 access token 沒有可用的預設 domain。` means the current group is gone or the account is disabled. Stop shortening, display the original snapshot, and tell the user to start `lihi-switch-group` explicitly; if no group is available, suggest `lihi-account` for status.
- Exact `site_create` error `access token 的預設 domain 已不在目前可用網域清單中。` means the current domain is unavailable. Stop shortening, display the original snapshot, and tell the user to start `lihi-switch-domain` explicitly.
- Exact work-group quota errors `The URL has reached the maximum limit specified by the workgroup`, `網址已達工作群組限定的最大上限`, and `网址已达工作群组限定的最大上限` stop shortening with the same original-snapshot behavior and tell the user to start `lihi-switch-group`; account quota errors keep the pricing/resolve/unchanged/cancel flow.
- Exact `目前工作群組已無法使用。` from domain switching routes once to `lihi-switch-group`.
- Exact selector error classification trims only surrounding transport whitespace. Unknown variants use generic failure handling; do not guess.
- Group switch rejection `選取的工作群組目前沒有可用網域，請先設定網域。` leaves the current selector unchanged; do not repair it by switching a domain under the old group.
- A conclusive pre-dispatch switch 401 may refresh, refetch options, re-resolve stable identity, and retry once. A possibly dispatched switch is verified once read-only (`group_options.is_current` or `account_status.domain`) and never blindly replayed.
- Switch OAuth references own authentication only and return control without calling a lihi lookup or mutation tool. Switch error-recovery references alone own refetch, verification, and retry after authentication returns.
- Per authentication incident, allow at most one host refresh, one qualifying interactive reauthentication, and one resumed operation. A second authentication failure stops.
- Interactive reauthentication is limited to a refresh-token exchange returning HTTP 401 or explicitly reporting the refresh token invalid, expired, revoked, or unusable. Unmatched readable errors are reported without login.
- Requests containing `Origin` are no longer rejected solely because of that header. Do not infer complete browser or CORS support from this fact.
- If compaction removes state required for a safe next operation, fail closed and recover the exact state before mutation or release.

## Release packaging and versioning

CI runs Python 3.8 unit tests and parity checks. Develop-branch CI builds a
develop marketplace for 14-day retention. SemVer tag CI builds four public
OpenAI skill ZIPs plus one production marketplace bundle for 90-day retention.

The develop packager:

- derives a shared `major.minor.patch` core from both host manifests;
- rewrites copied identities, endpoints, four skill folders, manifests, marketplaces, and Codex metadata only inside staging;
- emits `DEVELOP_BUILD.json`, where authoritative `skill_names` contains all four develop skills;
- retains singular `skill_name` at root and `plugins[0]` as a deprecated alias equal to `skill_names[0]` for 0.3 compatibility;
- excludes caches and preserves source runtime files unchanged.

The production marketplace packager copies the checked-in production
marketplaces, both host plugins, and public installation guides without
rewriting identities or endpoints. It emits `lihi-agent-<major.minor.patch>`
and fails rather than overwriting an existing output directory.

The OpenAI Platform packager emits exactly four individual skill ZIPs. Each
archive has one same-named top-level skill directory. It does not accept an app
ID and does not emit a complete plugin ZIP, marketplace, manifest, MCP config,
app config, or shared asset.

Both manifests must share core version `0.3.1`. Codex may add one cachebuster suffix. When modifying the Codex bundle, run the plugin-creator cachebuster helper last and validate the plugin. Reinstall only when explicitly requested; after reinstall, test from a new conversation.

Never commit `dist/`, a develop/localhost runtime URL, or a develop identity in production runtime configuration.

## Validation

Run at least:

```bash
python3 -m unittest discover -s tests -v
cmp plugins/codex/lihi/skills/lihi-shorten/scripts/detect_urls.py plugins/claude/lihi/skills/lihi-shorten/scripts/detect_urls.py
cmp plugins/codex/lihi/skills/lihi-shorten/references/shortening-workflow.md plugins/claude/lihi/skills/lihi-shorten/references/shortening-workflow.md
git diff --check
```

For packaging changes, also build locally with
`scripts/package_develop_bundle.py`, `scripts/package_production_bundle.py`,
and `scripts/package_openai_platform_bundle.py`. Validate all host plugins,
production/develop identity isolation, endpoint isolation, metadata aliases,
the four skill-only OpenAI archives, and absence of removed tool fields and
stale policies.
