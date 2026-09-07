# lihi agent plugin

Other languages: [Traditional Chinese guide](README.zh-TW.md).

Use lihi account status, group and short URL domain switching, and URL shortening from one Codex or Claude Code plugin.

## Plugin

### `lihi@lihi`

- Shows the account email, short URL usage, quota, subscription dates, current work group, and current short URL domain.
- Switches the active work group or short URL domain after checking fresh choices.
- Works while polishing copy or preparing human-facing content for release.
- Automatically shortens every eligible new long URL detected in that content.
- Uses the short URL domain configured for the current lihi client.
- Never publishes content unless you explicitly requested it and confirmed the final result.
- Registers the `lihi` MCP server exactly once for all bundled skills.

The production Streamable HTTP endpoint is:

```text
https://app.lihi.io/mcp/v1/tools
```

## Install

The production marketplace is available from [lihi-io/lihi-agent-plugin.git](https://github.com/lihi-io/lihi-agent-plugin.git). The plugin selector is `lihi@lihi`, displayed as `lihi`.

### Install directly from GitHub

#### Codex

```bash
codex plugin marketplace add https://github.com/lihi-io/lihi-agent-plugin.git
codex plugin add lihi@lihi
```

#### Claude Code

```bash
claude plugin marketplace add https://github.com/lihi-io/lihi-agent-plugin.git
claude plugin install lihi@lihi
```

### Install after downloading to local disk

1. Download the repository archive from GitHub and extract it. A local Git clone works as well.
2. Locate the extracted repository root containing `.agents/plugins/marketplace.json` and `.claude-plugin/marketplace.json`.
3. Replace `/absolute/path/to/lihi-agent-plugin` below with that repository root.

#### Codex

```bash
codex plugin marketplace add /absolute/path/to/lihi-agent-plugin
codex plugin add lihi@lihi
```

#### Claude Code

```bash
claude plugin marketplace add /absolute/path/to/lihi-agent-plugin
claude plugin install lihi@lihi
```

Do not pass the downloaded ZIP file itself to the marketplace command. Extract it first and use the absolute path to the extracted root.

## Authenticate

If a group or domain switch reports that a tool is unavailable, this does not by itself mean you need to sign in again. The plugin checks available connection information before deciding how to recover.

### Codex

Codex may ask you to authenticate lihi during installation or the first time the plugin is used. If a task still detects that initial authentication is required, or detects a qualifying refresh-token failure that requires reauthentication, Codex first assists by running `codex mcp login lihi` once. If that assisted command cannot start or does not complete authentication, run `codex mcp login lihi` yourself in a terminal. If the command is unavailable, open **MCP settings → lihi → Authenticate**. With prior lihi authorization, an ordinary tool-endpoint `401 invalid_token` or `Auth required` first uses one host-managed refresh attempt and does not by itself start interactive login.

After installing or updating, start a new Codex conversation before using the plugin. If the Codex app still shows the old plugin version, fully quit and reopen the application as a fallback, then start another new conversation.

If Codex reports that stored refresh credentials lack an issuer or cannot be bound to it, the plugin reports a Codex authorization-state problem and stops automatic recovery. Check the lihi connection in MCP settings; updating the plugin alone does not repair that stored authorization, and a previously confirmed switch remains completed.

### Claude Code

When authentication is required, open `/mcp`, select lihi, and choose **Authenticate**.

After installing or updating, start a new Claude Code conversation.

## View account information

Ask for the specific information you need:

```text
Show my short URL quota and subscription plan.
```

```text
Which work group am I currently using?
```

```text
Show my lihi account information.
```

The last, general request uses `account_status` and displays the account email first, followed by short URL usage, current plan, renewal date, current work group, and current short URL domain. Ask for available groups separately when you need the full list.

To switch the active work group:

```text
Switch my lihi work group.
```

The plugin checks `group_options` first. An empty or inconsistent list is treated as a server anomaly, while a one-entry list reports that only one work group is available and stops. It calls `account_switch_group` only with an exact returned ID, then displays the complete updated account status without another lookup.

To switch the short URL domain:

```text
Switch my lihi short URL domain.
```

The plugin always fetches `domain_options` first and calls `account_switch_domain` with the exact selected hostname. Chinese selection lists distinguish dedicated domains (`owned`) from public domains (`public`), recommend a dedicated domain, and link to `https://lihidomain.com/`; this guidance does not select an option. Changing a group or domain can require a normal host-managed token refresh on the next lihi request.

## Shorten URLs

Ask Codex or Claude Code to polish copy containing links, or to prepare that content for release. For example:

```text
Polish this post and shorten its links:
...
```

The plugin will:

1. Detect eligible HTTP(S) URLs in the current content snapshot without waiting for the copy to be final or stable.
2. Disclose which new long URLs it is about to create and continue automatically.
3. Reuse confirmed mappings from this conversation and call `site_create` once for each other unique URL.
4. Show the current updated content plus a separate list of links newly created in this batch.

Confirmed short URLs and mappings are retained across later edits in the same conversation, so only newly eligible long URLs need creation. lihi has no cross-conversation long-URL reuse lookup; processing the same long URL in another conversation creates another permanent short URL and consumes quota. The plugin still requires exact final-content confirmation before an explicitly requested publication.

If shortening reports an unavailable group/account, unavailable domain, or work-group quota limit, it stops the batch and any requested release, makes no automatic selector change, and shows the original inspected copy unchanged. Follow the prompt to switch the group or domain explicitly, then invoke shortening again or ask the agent to polish or rewrite the copy again.

For host-specific authentication and behavior details, see the [Codex guide](plugins/codex/lihi/README.md) or [Claude Code guide](plugins/claude/lihi/README.md).
