# OpenAI Platform skill packaging

The public lihi directory submission uses the OpenAI Platform **With MCP**
flow. The submission portal owns the production MCP registration, listing
information, and brand assets. The repository packager produces only the four
final skill bundles.

## Build the skill ZIPs

Run from the repository root:

```bash
python3 scripts/package_openai_platform_bundle.py \
  --output-dir dist/openai-platform
```

The script derives the shared `major.minor.patch` version from the Codex and
Claude production manifests. For version `0.3.1`, the only outputs are:

```text
dist/openai-platform/lihi-shorten-0.3.1.zip
dist/openai-platform/lihi-account-0.3.1.zip
dist/openai-platform/lihi-switch-group-0.3.1.zip
dist/openai-platform/lihi-switch-domain-0.3.1.zip
```

Each ZIP contains exactly one same-named top-level skill directory. For
example, `lihi-shorten-0.3.1.zip` contains `lihi-shorten/SKILL.md` plus that
skill's approved `agents/`, `references/`, and `scripts/` files.

The packager does not accept an app ID and does not create a complete plugin,
Developer marketplace, manifest, shared asset, `.mcp.json`, or `.app.json`.
The checked-in images under `packaging/openai-platform/assets/` remain
available for manual use in the submission portal, but are not packaging
inputs and do not block skill builds.

The source skills remain unchanged and are the single source of truth. The
packager reads approved files directly from each Codex production skill,
stages exact host-neutral rewrites, and validates each archive before replacing
any existing generated skill ZIP. All four archives use sorted files, fixed ZIP
timestamps, and consistent permissions for reproducible bytes.

The public skill bundles remove the pricing and dedicated-domain promotional
link sentences without inserting replacement service copy. Quota recovery
keeps its existing account-limit explanation without directing users to a
sales page.

## Build the production marketplace bundle

The production marketplace for Codex and Claude Code is packaged separately:

```bash
python3 scripts/package_production_bundle.py \
  --output-dir dist/production
```

For version `0.3.1`, this creates:

```text
dist/production/lihi-agent-0.3.1/
```

This installable directory retains the production `lihi@lihi` marketplace,
the `lihi` MCP identity, all four production skill names, and
`https://app.lihi.io/mcp/v1/tools`. It contains both Codex and Claude Code
plugin roots. The existing `package_develop_bundle.py` remains isolated to the
`lihi-dev` identity and the lihidev endpoint.

## Build from a release tag

Pushing a SemVer tag runs `.github/workflows/package-openai-platform.yml`.
Both `v0.3.1` and `0.3.1` tag forms are accepted. The tag must match the shared
Codex and Claude production manifest version.

```bash
git tag v0.3.1
git push origin v0.3.1
```

The workflow runs unit tests, syntax checks, host parity checks, and whitespace
validation. It uploads two GitHub Actions artifacts for 90 days:

- `lihi-openai-skills-<tag>` contains the four individual skill ZIPs.
- `lihi-agent-production-<tag>` contains the installable production
  marketplace bundle.

The workflow does not create or modify a GitHub Release.

## Submit with MCP

In the OpenAI submission portal:

1. Choose **With MCP** and provide
   `https://app.lihi.io/mcp/v1/tools` as the production server URL.
2. Upload each final skill ZIP in its corresponding skill upload flow.
3. Provide the listing logo, website, support, privacy, and terms information
   directly in the portal.
4. Complete the domain-verification challenge and production tool scan.
5. Provide exactly five positive test cases, three negative test cases,
   release notes, and any requested demo recording.
6. Confirm every tool publishes accurate `readOnlyHint`, `openWorldHint`, and
   `destructiveHint` annotations with justifications.
7. Provide reviewer-ready demo credentials for the OAuth flow.

A successful local build validates only the static skill and marketplace
artifacts. It does not validate the live MCP server, domain challenge, reviewer
credentials, policy attestations, or portal review.

See the official OpenAI documentation for
[plugin submission](https://developers.openai.com/plugins/deploy/submission)
and
[submission validation errors](https://developers.openai.com/plugins/deploy/submission-errors).
