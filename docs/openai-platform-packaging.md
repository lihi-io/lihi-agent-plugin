# OpenAI Platform release packaging

The public lihi directory submission uses the OpenAI Platform **With MCP** flow. The repository package contains the plugin manifest and four skills; the submission portal owns the production MCP server registration.

## Required brand assets

Add the two approved production images at these fixed repository paths:

```text
packaging/openai-platform/assets/logo.png
packaging/openai-platform/assets/composer-icon.png
```

`logo.png` must be a valid 256×256 PNG and `composer-icon.png` must be a valid 48×48 PNG. Both files must be no larger than 5 MiB. The packager validates PNG chunks, CRC values, exact dimensions, and compressed image data. Missing or invalid assets stop the build before an artifact is replaced.

## Build the ZIP

Run from the repository root:

```bash
python3 scripts/package_openai_platform_bundle.py \
  --output-dir dist/openai-platform
```

The script derives the shared `major.minor.patch` version from the Codex and Claude production manifests. For version `0.3.1`, the command creates one complete plugin ZIP and four standalone skill ZIPs:

```text
dist/openai-platform/lihi-openai-platform-0.3.1.zip
dist/openai-platform/lihi-shorten-0.3.1.zip
dist/openai-platform/lihi-account-0.3.1.zip
dist/openai-platform/lihi-switch-group-0.3.1.zip
dist/openai-platform/lihi-switch-domain-0.3.1.zip
```

The complete plugin ZIP root contains `.codex-plugin/plugin.json`, `assets/`, and `skills/`. Each standalone skill ZIP contains exactly one same-named top-level directory, for example `lihi-shorten/SKILL.md` plus that skill's approved `agents/`, `references/`, and `scripts/` files. The standalone ZIPs do not contain a plugin manifest, shared assets, or another skill.

All five ZIPs intentionally contain no `.mcp.json`, `.app.json`, `mcpServers`, develop identity, host-specific authentication command, repository documentation, or build metadata. Files are ordered and timestamped deterministically so identical input produces identical ZIP bytes. Every ZIP is fully staged and validated before any final artifact is replaced. Validation failures preserve the previous set, and a caught filesystem failure during publication rolls back every ZIP already replaced in that run.

The source skills remain unchanged and remain the single source of truth. The packager reads the approved files directly from each Codex production skill directory, copies them into temporary staging, and applies only the exact host-neutral substitutions declared in the script. Every expected source fragment must occur exactly once or the build stops; no second skill tree is stored under `packaging/`.

The public package removes the pricing and dedicated-domain promotional-link sentences from skill instructions without inserting replacement service copy. Quota recovery keeps its existing account-limit explanation without directing users to a sales page.

## Build for ChatGPT Developer mode

First enable ChatGPT Developer mode, register the production MCP server at `https://app.lihi.io/mcp/v1/tools`, and copy the resulting technical ID. It begins with `plugin_asdk_app_`.

Pass that ID to the same packager:

```bash
python3 scripts/package_openai_platform_bundle.py \
  --output-dir dist/openai-developer \
  --app-id plugin_asdk_app_REPLACE_WITH_REGISTERED_ID
```

Supplying `--app-id` changes the output mode. Instead of the five public ZIPs, the script creates one content-addressed local marketplace directory such as:

```text
dist/openai-developer/
└── lihi-openai-developer-0.3.1+codex.dev.<hash>/
    ├── .agents/plugins/marketplace.json
    └── plugins/lihi/
        ├── .app.json
        ├── .codex-plugin/plugin.json
        ├── assets/
        └── skills/
```

The generated `.app.json` maps `lihi` to the supplied technical ID, and the Developer manifest points `apps` to `./.app.json`. Its deterministic `+codex.dev.<hash>` cachebuster changes when the staged plugin content or app ID changes. The registered app ID is written only to the generated Developer artifact and never to the public ZIP or checked-in production runtime files.

Install the generated marketplace root and plugin with the paths printed by the command:

```bash
codex plugin marketplace add \
  dist/openai-developer/lihi-openai-developer-0.3.1+codex.dev.<hash>
codex plugin add lihi@lihi-openai-developer
```

Restart the ChatGPT desktop app after adding the local marketplace, then test the plugin in a new chat. Rebuilding with identical inputs reuses the identical versioned directory; changed inputs produce a new content-addressed directory.

## Submit with MCP

In the OpenAI submission portal:

1. Choose **With MCP** and provide `https://app.lihi.io/mcp/v1/tools` as the production server URL.
2. Upload the complete versioned plugin ZIP as the final skill bundle. The four standalone skill ZIPs are also available when a workflow needs one skill archive at a time; each has a single same-named top-level skill directory.
3. Use the website, support, privacy, and terms URLs embedded in the public manifest.
4. Complete the generated domain-verification challenge and production tool scan.
5. Provide exactly five positive test cases, three negative test cases, release notes, and a demo recording.
6. Confirm every tool publishes accurate `readOnlyHint`, `openWorldHint`, and `destructiveHint` annotations with justifications.
7. Provide reviewer-ready demo credentials for the OAuth flow.

A successful local build validates only the static plugin package. It does not validate the live MCP server, domain challenge, reviewer credentials, policy attestations, or portal review.

See the official OpenAI documentation for [plugin packaging](https://developers.openai.com/plugins/build/plugins), [submission](https://developers.openai.com/plugins/deploy/submission), and [submission validation errors](https://developers.openai.com/plugins/deploy/submission-errors).
