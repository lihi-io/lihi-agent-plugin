# lihi client bundle

Other languages: [Traditional Chinese guide](README.zh-TW.md).

This plugin connects Claude to your lihi account for short URL management. It works in Claude Code, on claude.ai, and in Cowork. It registers the remote MCP server `lihi` at:

```text
https://app.lihi.io/mcp/v1/tools
```

Its four skills share this single registration:

- `lihi-account` reads the account email and status, current group and domain, and available groups.
- `lihi-switch-group` switches the active work group from fresh `group_options`.
- `lihi-switch-domain` switches the short URL domain from fresh `domain_options`.
- `lihi-shorten` automatically shortens eligible new URLs in revised outbound copy.

## Authenticate

The plugin signs in to lihi with OAuth. The Claude app owns the sign-in flow and token refresh; the plugin never stores or asks for a password or token.

- **Claude Code**: when authentication is required, open `/mcp`, select the lihi plugin server, and choose **Authenticate**.
- **claude.ai and Cowork**: authorize lihi through the app's connector sign-in when it is requested.

With prior authorization, an ordinary tool-endpoint `401 invalid_token` or host-level `Auth required` first receives one host-managed refresh attempt. Interactive authentication is requested only for initial sign-in or a confirmed invalid, expired, revoked, or unusable refresh token. Unmatched errors are reported with workflow state preserved and do not start interactive authentication.

## Data sent to lihi

All requests go only to `https://app.lihi.io/mcp/v1/tools`, the lihi production MCP server:

- `site_create` sends each long URL selected for shortening and receives its short URL.
- `account_status`, `group_options`, and `domain_options` read the account email, usage, plan, renewal date, work groups, and short URL domains.
- `account_switch_group` and `account_switch_domain` send the chosen group ID or domain hostname.

The surrounding copy is never sent; only the detected URLs are. URL detection runs locally through the bundled `skills/lihi-shorten/scripts/detect_urls.py` script, which reads the current content snapshot and makes no network request. On claude.ai and in Cowork, that script needs code execution to be enabled.

See the lihi [privacy policy](https://knowledge.lihi.io/privacy-policy/) and [terms of service](https://knowledge.lihi.io/terms/). For support, contact lihi at [lihistatus.com/contact](https://lihistatus.com/contact).

## Account and selector behavior

`account_status` provides the account email, usage, plan, renewal, current work group, and current short URL domain. General status answers display the account email first. `group_options` is used only for available-group lists. Both selector skills fetch fresh options before mutation and display the complete AccountStatus returned by a successful switch without another lookup. A Chinese domain selection list distinguishes dedicated domains (`owned`) from public domains (`public`), recommends a dedicated domain, and links to `https://lihidomain.com/` without selecting an option.

A selector change may revoke the current access token while leaving refresh authorization valid. The host refreshes only when the next lihi request needs access. Possibly dispatched switch calls are never replayed blindly.

## URL-shortening behavior

For human-facing outbound copy, `lihi-shorten` detects HTTP(S) URLs in the current content snapshot without waiting for final or stable copy, discloses the current creation batch, and automatically calls `site_create` once for each unique new long URL. Each call creates a permanent short URL and counts toward the lihi quota. Later edits preserve exact confirmed short URLs and reuse confirmed mappings from this conversation; lihi does not provide cross-conversation long-URL reuse. Non-idempotent calls are not retried after an uncertain dispatch.

An unavailable group/account, unavailable domain, or work-group quota limit stops the shortening batch and any requested release. The plugin shows the original inspected copy unchanged and waits for the user to start the recommended group or domain switch explicitly before shortening is invoked again.

The plugin never publishes unless the user explicitly requested release and confirmed the exact final content. Creation disclosures and current-batch mapping summaries remain outside published content.

## License

Released under the [MIT License](LICENSE).
