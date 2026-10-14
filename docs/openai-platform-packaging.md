# OpenAI Platform plugin packaging

The public lihi directory submission uses one complete portable plugin ZIP.
The package contains all four skills, the production OAuth MCP connection,
listing metadata, and approved brand assets. The submission portal handles
domain verification, authentication, tool scans, and review.

## Build the plugin and skill ZIPs

Run from the repository root:

```bash
python3 scripts/package_openai_platform_bundle.py \
  --output-dir dist/openai-platform
```

The script derives the shared `major.minor.patch` version from the Codex and
Claude production manifests. For version `0.3.2`, it produces five artifacts:

```text
dist/openai-platform/lihi-0.3.2.zip
dist/openai-platform/lihi-shorten-0.3.2.zip
dist/openai-platform/lihi-account-0.3.2.zip
dist/openai-platform/lihi-switch-group-0.3.2.zip
dist/openai-platform/lihi-switch-domain-0.3.2.zip
```

The complete plugin archive has one plugin root directly at the ZIP root:

```text
plugin.json
mcp.json
assets/
  composer-icon.png
  logo.png
skills/
  lihi-shorten/
  lihi-account/
  lihi-switch-group/
  lihi-switch-domain/
```

`plugin.json` declares the Agent Plugins 1.0.0 plugin schema and the production
`lihi` identity. Publisher and listing metadata come from the Codex production
manifest. The generated description is host-neutral, and the listing subtitle
fits the public directory's 30-character limit. OpenAI presentation lives in
`extensions.com.openai.interface`, with `./assets/` paths for the included PNGs.
The generated `supportURL` points to `https://lihistatus.com/contact`, the
customer support page linked from lihi's privacy policy. Portable packages
discover the root `skills/` and `mcp.json` automatically.

`mcp.json` declares the Agent Plugins 1.0.0 MCP schema and exactly one `lihi`
server at `https://app.lihi.io/mcp/v1/tools`. Its transport is
`streamable-http`; OAuth is declared under the server's
`extensions.com.openai.auth`. Optional client registration, endpoint, and scope
overrides are omitted so connection setup can use discovery. Credentials are
never included in the package.

The packager does not accept an app ID. It does not emit a marketplace,
`.app.json`, lifecycle hooks, or legacy host manifests.
The approved images under `packaging/openai-platform/assets/` are required
packaging inputs and are copied unchanged.

Each individual skill ZIP contains one same-named top-level directory, such as
`lihi-shorten/SKILL.md`, plus that skill's approved supporting files. It contains
no plugin manifest, MCP configuration, or shared brand assets. Its files are
byte-identical to the corresponding skill under `skills/` in the complete plugin
ZIP, including the executable detector. Use the complete plugin ZIP for the
public plugin submission flow; the individual ZIPs are standalone skill exports.

The Codex production skills remain the source of truth. The packager stages
approved files and exact host-neutral rewrites without modifying either host
bundle. Public skills remove the pricing and dedicated-domain promotional
link sentences while preserving recovery behavior and domain recommendations.

All files use sorted archive paths, fixed ZIP timestamps, and consistent
permissions for reproducible bytes. The detector remains executable and
byte-identical to production. All five archives are validated and hashed before
replacing any existing ZIPs of the same version. If publication fails midway,
the previous artifact set is restored. Temporary archives are removed after a
failed build. Older artifacts already in the output directory are left in place;
use a fresh output directory when checking the five-archive release set.

## Build the production marketplace bundle

The production marketplace for Codex and Claude Code is packaged separately:

```bash
python3 scripts/package_production_bundle.py \
  --output-dir dist/production
```

For version `0.3.2`, this creates `dist/production/lihi-agent-0.3.2/`.
It retains both production host plugins, their `lihi@lihi` marketplace
identity, all four skills, and the production MCP endpoint.

The develop packager remains isolated to `lihi-dev` and the lihidev endpoint.
Only its staged Codex develop manifest adds `+codex.<build-number>`;
production manifests and the staged Claude develop manifest keep plain versions.

## Build from a release tag

Pushing a SemVer tag runs `.github/workflows/package-openai-platform.yml`.
Both `v0.3.2` and `0.3.2` tag forms are accepted. The tag must match the shared
production manifest version.

The workflow runs unit tests, syntax checks, host parity checks, and whitespace
validation. It uploads two GitHub Actions artifacts for 90 days:

- `lihi-openai-bundles-<tag>` contains the complete plugin ZIP and four individual
  skill ZIPs.
- `lihi-agent-production-<tag>` contains the production marketplace bundle.

The workflow does not create or modify a GitHub Release.

## Submit the complete plugin

In the OpenAI submission portal:

1. Select the owning organization, project, and verified developer identity.
2. Choose **Upload new or existing plugin** and upload `lihi-<version>.zip`.
3. Review the imported listing metadata and all four bundled skills.
4. Under **MCPs**, connect the production server, complete domain verification
   and OAuth setup, and inspect the tool scan.
5. Provide exactly five positive and three negative test cases, release notes,
   a demo recording, and reviewer OAuth credentials.
   These review materials and private credentials are not generated by this build.
6. Confirm every tool publishes accurate `readOnlyHint`, `openWorldHint`, and
   `destructiveHint` annotations with justifications, and resolve scan findings.
7. Complete the required policy attestations and submit the draft for review.

A successful local build validates the static package. Live MCP connectivity,
OAuth discovery, domain verification, reviewer access, and portal approval
still require testing in the submission portal. Changes to packaged skills or
metadata require uploading a new complete ZIP with the same plugin identity.

See the official OpenAI documentation for
[plugin packaging](https://developers.openai.com/plugins/build/plugins),
[plugin submission](https://developers.openai.com/plugins/deploy/submission), and
[submission validation errors](https://developers.openai.com/plugins/deploy/submission-errors).
