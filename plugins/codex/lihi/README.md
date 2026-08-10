# Codex lihi client bundle

Other languages: [Traditional Chinese guide](README.zh-TW.md).

This Codex plugin registers the remote MCP server `lihi` at:

```text
https://app.lihi.com/mcp/v1/tools
```

Its four skills share this single registration:

- `lihi-account` reads account status, current group and domain, and available groups.
- `lihi-switch-group` switches the active work group from fresh `group_options`.
- `lihi-switch-domain` switches the short URL domain from fresh `domain_options`.
- `lihi-shorten` automatically shortens eligible new URLs in revised outbound copy.

## Authenticate

Codex owns OAuth and token refresh. With prior authorization, an ordinary tool-endpoint `401 invalid_token` or host-level `Auth required` first receives one host-managed refresh attempt. Initial authentication, or a confirmed invalid, expired, revoked, or unusable refresh token, uses `codex mcp login lihi` once when available. If assisted login cannot complete, run that command in your terminal; use **MCP settings → lihi → Authenticate** only when the command is unavailable. Unmatched errors are reported with workflow state preserved and do not start interactive authentication.

## Account and selector behavior

`account_status` provides usage, plan, renewal, current work group, and current short URL domain. `group_options` is used only for available-group lists. Both selector skills fetch fresh options before mutation and display the complete AccountStatus returned by a successful switch without another lookup. A Chinese domain selection list distinguishes dedicated domains (`owned`) from public domains (`public`), recommends a dedicated domain, and links to `https://lihidomain.com/` without selecting an option.

A selector change may revoke the current access token while leaving refresh authorization valid. Codex refreshes only when the next lihi request needs access. Possibly dispatched switch calls are never replayed blindly.

## URL-shortening behavior

For human-facing outbound copy, `lihi-shorten` detects HTTP(S) URLs in the current content snapshot without waiting for final or stable copy, discloses the current creation batch, and automatically calls `site_create` once for each unique new long URL. Later edits preserve exact confirmed short URLs and reuse confirmed mappings from this conversation; lihi does not provide cross-conversation long-URL reuse. Non-idempotent calls are not retried after an uncertain dispatch.

An unavailable group/account, unavailable domain, or work-group quota limit stops the shortening batch and any requested release. The plugin shows the original inspected copy unchanged and waits for the user to start the recommended group or domain switch explicitly before shortening is invoked again.

The plugin never publishes unless the user explicitly requested release and confirmed the exact final content. Creation disclosures and current-batch mapping summaries remain outside published content.
