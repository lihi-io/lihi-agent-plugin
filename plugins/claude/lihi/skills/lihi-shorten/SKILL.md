---
name: lihi-shorten
description: Inspect human-facing outbound copy for HTTP(S) URLs while Claude Code adjusts, rewrites, or polishes it, including 調整文案、潤飾文案、改寫文案、優化文案, or before Claude Code sends, publishes, posts, uploads, schedules, or otherwise releases it, including 發送、發布、公開、貼文、寄出、上線、排程. Run local detection on the current content snapshot without waiting for final copy and automatically shorten every eligible new long URL through lihi. Never infer publication from copy-only work. Exclude source code, configuration, tests, logs, README or API documentation, changelogs, code comments, research, and link reading unless the user explicitly identifies human-facing outbound copy.
---

# Detect and shorten URLs in outbound copy

The bundled `lihi` MCP client is eager, so the host may start OAuth when the plugin is installed or enabled. Authentication grants tool access; it does not authorize publication.

Always render the brand name exactly as `lihi` in lowercase in every user-facing message and generated copy, including when the user uses another capitalization.

## Flow

1. For an external release, intercept before any external side effect. Do not wait for the requested copy adjustment to finish before detecting or creating short URLs.
2. Prepare the exact current human-visible content snapshot, including every currently available relevant field and every URL introduced by Claude Code so far. It need not be final or stable.
3. Run the Python 3.8+ `scripts/detect_urls.py` from this skill directory through standard input or with a UTF-8 file path. Never interpolate untrusted content into a shell command. Detection is local and makes no lihi call.
4. Keep code exclusions. Use `--include-code` only when the user explicitly intends code URLs to be clickable outbound content.
5. If detection fails or JSON is invalid, make no lihi call and block external release. Copy-only output may be shown with an incomplete-check warning.
6. Explain rejected reasons without echoing credentials. Any `embedded_credentials` rejection blocks every lihi call and external release until the user supplies a safe URL; redact that destination from copy-only output.
7. Consult the cumulative confirmed-generated ledger for this conversation. Exclude and preserve every exact confirmed `short_url`. Automatically reuse a confirmed mapping when its exact `long_url` returns. Never treat an uncertain result as confirmed.
8. Build the current creation batch from the detector's first-seen unique URLs after removing confirmed short URLs and reusable long URLs. Duplicate occurrences share one result. The ledger is conversation-scoped: a new conversation has no cross-conversation lookup and the server will create a new short URL for the same long URL.
9. If there are no fresh creations, apply reusable mappings from greatest detector offset to smallest, show the current updated content snapshot, and state outside the content that no new short URLs were created when mappings were reused. For an explicitly requested external action, obtain confirmation of the exact complete final content before release.
10. When fresh creations remain, read [the lihi shortening workflow](references/shortening-workflow.md) completely before the first lihi tool call. Carry the exact content snapshot, detector JSON, ordered batch, external-action intent, confirmed ledger, and uncertain states. The workflow automatically calls `site_create` once per new long URL; it does not ask the user to choose URLs or a domain.
11. If lihi authentication is missing, expired, or rejected, read [the Claude Code OAuth recovery rules](references/oauth-recovery.md) completely before recovery, then resume only within its retry budgets.
12. Whenever content or batch membership changes before dispatch, discard stale batch state, return to step 2, and issue a new batch disclosure. After a confirmed creation, preserve exact confirmed short URLs and mappings across later edits, then re-detect the edited snapshot and process only newly eligible long URLs. Re-detect again before external release.

Keep final-content confirmation separate from automatic short-link creation. A copy-only request never implies publication. Never publish the workflow disclosure or current-batch mapping summary as part of the user's content.
