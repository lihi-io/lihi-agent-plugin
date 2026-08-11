import json
import re
import unittest
from pathlib import Path


PRODUCTION_ENDPOINT = "https://app.lihi.io/mcp/v1/tools"
SKILLS = (
    "lihi-shorten",
    "lihi-account",
    "lihi-switch-group",
    "lihi-switch-domain",
)
TOOLS = (
    "site_create",
    "account_status",
    "group_options",
    "account_switch_group",
    "domain_options",
    "account_switch_domain",
)
GROUP_ACCOUNT_ERROR = "目前的 access token 沒有可用的預設 domain。"
DOMAIN_ERROR = "access token 的預設 domain 已不在目前可用網域清單中。"
GROUP_SWITCH_ERROR = "目前工作群組已無法使用。"
WORK_GROUP_QUOTA_ERRORS = (
    "The URL has reached the maximum limit specified by the workgroup",
    "網址已達工作群組限定的最大上限",
    "网址已达工作群组限定的最大上限",
)


class AccountPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.roots = {
            "codex": cls.repo_root / "plugins/codex/lihi",
            "claude": cls.repo_root / "plugins/claude/lihi",
        }

    def read(self, path):
        return path.read_text(encoding="utf-8")

    def skill(self, host, name):
        return self.read(self.roots[host] / "skills" / name / "SKILL.md")

    def recovery(self, host, name):
        return self.read(
            self.roots[host]
            / "skills"
            / name
            / "references/oauth-recovery.md"
        )

    def error_recovery(self, host, name):
        return self.read(
            self.roots[host]
            / "skills"
            / name
            / "references/error-recovery.md"
        )

    def test_manifests_share_version_and_one_mcp_registration(self):
        codex = json.loads(
            self.read(self.roots["codex"] / ".codex-plugin/plugin.json")
        )
        claude = json.loads(
            self.read(self.roots["claude"] / ".claude-plugin/plugin.json")
        )
        self.assertEqual(codex["name"], "lihi")
        self.assertEqual(claude["name"], "lihi")
        self.assertTrue(codex["version"].startswith("0.3.1"))
        self.assertEqual(claude["version"], "0.3.1")
        self.assertEqual(codex["version"].split("+")[0], claude["version"])
        self.assertLessEqual(len(codex["interface"]["defaultPrompt"]), 3)
        self.assertTrue(
            any("domain" in prompt.lower() for prompt in codex["interface"]["defaultPrompt"])
        )
        self.assertTrue(
            any("automatically" in prompt.lower() for prompt in codex["interface"]["defaultPrompt"])
        )

        for root in self.roots.values():
            config = json.loads(self.read(root / ".mcp.json"))
            self.assertEqual(list(config["mcpServers"]), ["lihi"])
            self.assertEqual(config["mcpServers"]["lihi"]["url"], PRODUCTION_ENDPOINT)
            self.assertEqual(config["mcpServers"]["lihi"]["auth"], "oauth")
            self.assertEqual(list(root.rglob(".mcp.json")), [root / ".mcp.json"])
            self.assertEqual(
                {path.name for path in (root / "skills").iterdir() if path.is_dir()},
                set(SKILLS),
            )

    def test_marketplaces_expose_only_production_lihi(self):
        paths = (
            self.repo_root / ".agents/plugins/marketplace.json",
            self.repo_root / ".claude-plugin/marketplace.json",
        )
        for path in paths:
            marketplace = json.loads(self.read(path))
            self.assertEqual(marketplace["name"], "lihi")
            self.assertEqual([item["name"] for item in marketplace["plugins"]], ["lihi"])
        codex = json.loads(self.read(paths[0]))
        claude = json.loads(self.read(paths[1]))
        self.assertEqual(codex["plugins"][0]["source"]["path"], "./plugins/codex/lihi")
        self.assertEqual(claude["plugins"][0]["source"], "./plugins/claude/lihi")

    def test_all_skills_have_valid_identity_and_no_placeholders(self):
        for host in self.roots:
            for name in SKILLS:
                with self.subTest(host=host, skill=name):
                    content = self.skill(host, name)
                    self.assertIn("\nname: {0}\n".format(name), content)
                    self.assertIn("Always render the brand name exactly as `lihi`", content)
                    self.assertNotIn("TODO", content)

    def test_account_routing_and_account_status_shape(self):
        required = (
            "Call `account_status` with `{}` for general account information",
            "Call `group_options` with `{}` only when",
            "Call both only when",
            "`group_name`: a string or `null`",
            "`domain`: a string or `null`",
            "短網址用量：<used> / 無上限",
            "目前方案：<plan>（無到期日）",
            "續訂日期：-",
            "目前工作群組：我的群組",
            "目前短網址網域：未回傳可用網域",
            "Preserve every non-null `group_name` and `domain` exactly",
        )
        for host in self.roots:
            content = self.skill(host, "lihi-account")
            for marker in required:
                self.assertIn(marker, content)
            self.assertLess(content.index("短網址用量"), content.index("目前方案"))
            self.assertLess(content.index("目前方案"), content.index("續訂日期"))
            self.assertLess(content.index("續訂日期"), content.index("目前工作群組"))
            self.assertLess(content.index("目前工作群組"), content.index("目前短網址網域"))
            self.assertNotIn("<name>（個人群組）", content)
            self.assertNotIn("續訂日期：未回傳已確認的排程日期", content)
            self.assertNotIn("目前工作群組：未回傳可用名稱", content)

    def test_group_options_and_switch_contract(self):
        required = (
            "Call `group_options` with `{}` before every selection",
            "exactly one current entry",
            "Preserve every non-null `name` byte-for-byte",
            "Keep duplicate names as distinct entries",
            "目前只有一個工作群組：<label>",
            "Bind numbers only to this exact `group_options` snapshot",
            "Call `account_switch_group` once with `{group_id:<exact returned id>}`",
            "Validate a successful response as AccountStatus",
            "never infer an ID from `group_name`",
            "references/error-recovery.md",
        )
        for host in self.roots:
            content = self.skill(host, "lihi-switch-group")
            for marker in required:
                self.assertIn(marker, content)
            self.assertIn("續訂日期：-", content)
            self.assertIn("目前工作群組：我的群組", content)
            self.assertIn("目前短網址網域：未回傳可用網域", content)
            self.assertIn("訂閱方案說明：https://knowledge.lihi.io/pricing", content)

    def test_domain_options_and_switch_contract(self):
        required = (
            "Call `domain_options` with `{}` before every selection",
            "`hostname`: a non-empty string",
            "`type`: exactly `owned` or `public`",
            "Stable-sort owned entries before public entries",
            "deduplicate exact, case-sensitive hostnames",
            "Do not trim, lowercase, normalize, or derive an opaque value",
            "Call `account_switch_domain` once with `{domain:<exact hostname>}`",
            "`domain`: a non-null string that exactly equals the submitted hostname",
            "A null or mismatched value is invalid",
            "references/error-recovery.md",
        )
        for host in self.roots:
            content = self.skill(host, "lihi-switch-domain")
            for marker in required:
                self.assertIn(marker, content)
            self.assertIn("Do not trigger for merely reading a URL", content)
            self.assertIn("請選擇要使用的 lihi 網域：", content)
            self.assertIn("1. <owned-hostname> — 專屬網域 (owned)", content)
            self.assertIn("2. <public-hostname> — 公用網域 (public)", content)
            self.assertIn("建議選擇專屬網域，有助於增加信任度。", content)
            self.assertIn("專屬網域說明：https://lihidomain.com/", content)
            self.assertIn("請回覆選項編號（例如 1），也可以回覆網域名稱。", content)
            self.assertIn("including when every option is public", content)
            self.assertIn("does not select an option", content)
            self.assertIn("omit any type that is not present", content)
            self.assertLess(
                content.index("請選擇要使用的 lihi 網域："),
                content.index("1. <owned-hostname> — 專屬網域 (owned)"),
            )
            self.assertLess(
                content.index("2. <public-hostname> — 公用網域 (public)"),
                content.index("建議選擇專屬網域，有助於增加信任度。"),
            )
            self.assertLess(
                content.index("專屬網域說明：https://lihidomain.com/"),
                content.index("請回覆選項編號（例如 1），也可以回覆網域名稱。"),
            )
            self.assertIn("續訂日期：-", content)
            self.assertIn("目前工作群組：我的群組", content)
            self.assertIn("短網址用量：<used> / 無上限", content)
            self.assertIn("目前方案：<plan>（無到期日）", content)
            self.assertIn("訂閱方案說明：https://knowledge.lihi.io/pricing", content)

    def test_switch_skills_render_complete_account_status_consistently(self):
        shared_markers = (
            "Display the full returned status in this order",
            "短網址用量：<used> / <quota>",
            "短網址用量：<used> / 無上限",
            "目前方案：<plan>（到期日：<expires_on>）",
            "目前方案：<plan>（無到期日）",
            "續訂日期：<next_renewal_on>",
            "續訂日期：-",
            "目前工作群組：<group_name>",
            "目前工作群組：我的群組",
            "目前短網址網域：<domain>",
            "訂閱方案說明：https://knowledge.lihi.io/pricing",
            "Preserve every non-null display value exactly",
        )
        for host in self.roots:
            for skill_name in ("lihi-switch-group", "lihi-switch-domain"):
                with self.subTest(host=host, skill=skill_name):
                    content = self.skill(host, skill_name)
                    for marker in shared_markers:
                        self.assertIn(marker, content)
                    positions = [content.index(marker) for marker in (
                        "短網址用量：<used> / <quota>",
                        "目前方案：<plan>（到期日：<expires_on>）",
                        "續訂日期：<next_renewal_on>",
                        "目前工作群組：<group_name>",
                        "目前短網址網域：<domain>",
                    )]
                    self.assertEqual(positions, sorted(positions))

    def test_switch_skills_have_explicit_ordered_flows(self):
        contracts = {
            "lihi-switch-group": ("group_options", "account_switch_group"),
            "lihi-switch-domain": ("domain_options", "account_switch_domain"),
        }
        for host in self.roots:
            for skill_name, (discovery, mutation) in contracts.items():
                with self.subTest(host=host, skill=skill_name):
                    content = self.skill(host, skill_name)
                    self.assertIn("## Flow\n", content)
                    flow = content.split("## Flow\n", 1)[1].split("\n## ", 1)[0]
                    for step in range(1, 7):
                        self.assertIn("{0}. ".format(step), flow)
                    self.assertLess(flow.index(discovery), flow.index(mutation))
                    self.assertLess(flow.index(mutation), flow.index("On success"))
                    self.assertIn("read [the switch error recovery rules]", flow)
                    self.assertIn("references/error-recovery.md", flow)
                    self.assertNotIn("OAuth", flow)

    def test_switch_errors_are_progressively_disclosed_in_references(self):
        group_errors = (
            "選取的工作群組目前沒有可用網域，請先設定網域。",
            "找不到可切換的有效帳號群組。",
            "目前的 MCP 帳號授權無法切換群組。",
        )
        domain_errors = (
            "偵測到其他 tool call 已更新 MCP 帳號設定，請重新選擇 domain。",
            "指定的 domain 不在目前工作群組的可用網域清單中。",
            GROUP_SWITCH_ERROR,
            "目前的 MCP 帳號授權無法切換網域。",
        )
        for host in self.roots:
            group_skill = self.skill(host, "lihi-switch-group")
            group_recovery = self.error_recovery(host, "lihi-switch-group")
            domain_skill = self.skill(host, "lihi-switch-domain")
            domain_recovery = self.error_recovery(host, "lihi-switch-domain")

            for error in group_errors:
                self.assertNotIn(error, group_skill)
                self.assertIn(error, group_recovery)
            for error in domain_errors:
                self.assertNotIn(error, domain_skill)
                self.assertIn(error, domain_recovery)

            for skill_content, recovery_content in (
                (group_skill, group_recovery),
                (domain_skill, domain_recovery),
            ):
                self.assertNotIn("## Uncertain mutation results", skill_content)
                self.assertIn("## Uncertain mutation results", recovery_content)
                self.assertIn("oauth-recovery.md", recovery_content)
                self.assertIn("Never replay it blindly", recovery_content)
                self.assertIn("Do not load it during the normal successful flow", recovery_content)

        for skill_name in ("lihi-switch-group", "lihi-switch-domain"):
            codex = (
                self.roots["codex"]
                / "skills"
                / skill_name
                / "references/error-recovery.md"
            )
            claude = (
                self.roots["claude"]
                / "skills"
                / skill_name
                / "references/error-recovery.md"
            )
            self.assertEqual(codex.read_bytes(), claude.read_bytes())

    def test_shortening_is_automatic_and_site_create_has_one_argument(self):
        skill_markers = (
            "automatically shorten every eligible new long URL",
            "Do not wait for the requested copy adjustment to finish",
            "It need not be final or stable",
            "Build the current creation batch",
            "a new conversation has no cross-conversation lookup",
            "does not ask the user to choose URLs or a domain",
            "Never publish the workflow disclosure",
        )
        workflow_markers = (
            "lihi 將為本批次偵測到的 <N> 個新長網址建立短網址",
            "Call `site_create` exactly once per fresh unique URL",
            "with exactly `{url:<long URL>}`",
            "The server has no long-URL reuse lookup",
            "Group or account unavailable",
            "Domain unavailable",
            "stop the entire shortening batch immediately",
            "make no further call for the failed URL or any remaining batch URL",
            "never call a selector discovery or switch tool",
            "Apply no reusable or newly confirmed mapping to the displayed content",
            "Keep every earlier validated mapping in the conversation ledger",
            "do not display a current-batch mapping summary or mention earlier creation side effects",
            "以下為未套用本次短網址替換的原本文案：",
            "使用 `$lihi-switch-group`",
            "使用 `$lihi-switch-domain`",
            "使用 `$lihi-account`",
            "再使用 `$lihi-shorten`",
            "`site_create` is non-idempotent",
            "本次新建短網址",
            "Copy-only work ends after showing the result",
            "The inspected snapshot need not be final or stable",
            "After a successful batch, show the current updated human-visible content snapshot",
        )
        for host, root in self.roots.items():
            content = self.skill(host, "lihi-shorten")
            workflow = self.read(
                root / "skills/lihi-shorten/references/shortening-workflow.md"
            )
            for marker in skill_markers:
                self.assertIn(marker, content)
            for marker in workflow_markers:
                self.assertIn(marker, workflow)
            self.assertIn(GROUP_ACCOUNT_ERROR, workflow)
            self.assertIn(DOMAIN_ERROR, workflow)
            for error in WORK_GROUP_QUOTA_ERRORS:
                self.assertIn(error, workflow)
            self.assertNotIn("domain_options", workflow)
            self.assertNotIn("account_switch_domain", workflow)
            self.assertNotIn("account_switch_group", workflow)
            self.assertNotIn("hand off", workflow)
            self.assertNotIn("remediation", workflow)
            self.assertNotIn(GROUP_SWITCH_ERROR, workflow)
            self.assertNotIn("supports_custom_slug", workflow)
            self.assertNotIn("site_create.domain", workflow)
            self.assertNotIn("Finish the requested copy adjustment first", content)
            self.assertNotIn("exact complete final human-visible content", content)
            self.assertNotIn("show the complete content", content.lower())

    def test_shortening_error_guidance_matches_exact_classification(self):
        for host, root in self.roots.items():
            workflow = self.read(
                root / "skills/lihi-shorten/references/shortening-workflow.md"
            )
            group_error = workflow.index(GROUP_ACCOUNT_ERROR)
            domain_error = workflow.index(DOMAIN_ERROR)
            group_prompt = workflow.index("lihi 目前的工作群組或帳號無法使用")
            domain_prompt = workflow.index("lihi 目前的短網址網域已不在可用清單中")
            quota_prompt = workflow.index("lihi 目前的工作群組已達短網址建立上限")
            self.assertLess(group_error, group_prompt)
            self.assertLess(domain_error, domain_prompt)
            self.assertLess(domain_prompt, quota_prompt)
            self.assertIn("The user must start a later, independent switch or account workflow", workflow)
            self.assertIn("Retain validated mappings even when a later URL", workflow)

    def test_shortening_workflows_and_detectors_are_byte_identical(self):
        codex = self.roots["codex"] / "skills/lihi-shorten"
        claude = self.roots["claude"] / "skills/lihi-shorten"
        self.assertEqual(
            (codex / "references/shortening-workflow.md").read_bytes(),
            (claude / "references/shortening-workflow.md").read_bytes(),
        )
        self.assertEqual(
            (codex / "scripts/detect_urls.py").read_bytes(),
            (claude / "scripts/detect_urls.py").read_bytes(),
        )

    def test_skill_behavior_is_semantically_identical_across_hosts(self):
        explicit_host_differences = {
            "lihi-account": (
                ("the Codex OAuth recovery rules", "the host OAuth recovery rules"),
                ("the Claude Code OAuth recovery rules", "the host OAuth recovery rules"),
            ),
            "lihi-switch-group": (
                ("the Codex OAuth recovery rules", "the host OAuth recovery rules"),
                ("the Claude Code OAuth recovery rules", "the host OAuth recovery rules"),
            ),
            "lihi-switch-domain": (
                ("the Codex OAuth recovery rules", "the host OAuth recovery rules"),
                ("the Claude Code OAuth recovery rules", "the host OAuth recovery rules"),
            ),
            "lihi-shorten": (
                ("while Codex adjusts", "while the host adjusts"),
                ("while Claude Code adjusts", "while the host adjusts"),
                ("before Codex sends", "before the host sends"),
                ("before Claude Code sends", "before the host sends"),
                ("every URL introduced by Codex", "every URL introduced by the host"),
                ("every URL introduced by Claude Code", "every URL introduced by the host"),
                ("the Codex OAuth recovery rules", "the host OAuth recovery rules"),
                ("the Claude Code OAuth recovery rules", "the host OAuth recovery rules"),
            ),
        }
        for name, replacements in explicit_host_differences.items():
            codex = self.skill("codex", name)
            claude = self.skill("claude", name)
            for old, new in replacements:
                codex = codex.replace(old, new)
                claude = claude.replace(old, new)
            self.assertEqual(codex, claude, name)

    def test_oauth_recovery_has_shared_budgets_and_host_specific_action(self):
        for host in self.roots:
            for skill_name in SKILLS:
                with self.subTest(host=host, skill=skill_name):
                    content = self.recovery(host, skill_name)
                    self.assertIn("host-managed refresh", content)
                    self.assertIn("refresh token is invalid, expired, revoked, or unusable", content)
                    self.assertRegex(content, r"at most one (host )?refresh|allow one .*refresh")
                    self.assertIn("one resumed", content)
                    self.assertIn("second authentication failure", content.lower())
                    if host == "codex":
                        self.assertIn("codex mcp login lihi", content)
                    else:
                        self.assertIn("/mcp", content)
                        self.assertNotIn("codex mcp login", content)

    def test_switch_recovery_never_replays_success_or_uncertainty(self):
        for host in self.roots:
            group_oauth = self.recovery(host, "lihi-switch-group")
            domain_oauth = self.recovery(host, "lihi-switch-domain")
            group_error = self.error_recovery(host, "lihi-switch-group")
            domain_error = self.error_recovery(host, "lihi-switch-domain")
            for content in (group_oauth, domain_oauth):
                self.assertIn("Own only authentication recovery and its budget", content)
                self.assertIn("Do not call any lihi lookup or mutation tool", content)
                self.assertIn("return control to the calling error-recovery reference", content)
                self.assertIn("authentication_recovered", content)
                self.assertNotIn("`group_options`", content)
                self.assertNotIn("`domain_options`", content)
                self.assertNotIn("`account_status`", content)
                self.assertNotIn("`account_switch_group`", content)
                self.assertNotIn("`account_switch_domain`", content)
            self.assertIn("Never replay it blindly", group_error)
            self.assertIn("call `group_options` once and verify", group_error)
            self.assertIn("Never replay it blindly", domain_error)
            self.assertIn("call `account_status` once and compare its exact `domain`", domain_error)
            self.assertIn("this reference owns one resumed fresh `group_options` call", group_error)
            self.assertIn("this reference owns one resumed fresh `domain_options` call", domain_error)

    def test_codex_skill_metadata_declares_shared_dependency(self):
        for name in SKILLS:
            metadata = self.read(
                self.roots["codex"] / "skills" / name / "agents/openai.yaml"
            )
            self.assertIn('value: "lihi"', metadata)
            self.assertIn("$" + name, metadata)
            self.assertIn(PRODUCTION_ENDPOINT, metadata)
            match = re.search(r'short_description: "([^"]+)"', metadata)
            self.assertIsNotNone(match)
            self.assertGreaterEqual(len(match.group(1)), 25)
            self.assertLessEqual(len(match.group(1)), 64)

    def test_docs_freeze_current_contract_and_error_literals(self):
        contract = self.read(self.repo_root / "docs/mcp-contract.md")
        acceptance = self.read(self.repo_root / "docs/acceptance-scenarios.md")
        guide = self.read(self.repo_root / "AGENTS.md")
        for tool in TOOLS:
            self.assertIn("`" + tool + "`", contract)
        for text in (GROUP_ACCOUNT_ERROR, DOMAIN_ERROR, GROUP_SWITCH_ERROR):
            self.assertIn(text, contract)
            self.assertIn(text, guide)
        for text in WORK_GROUP_QUOTA_ERRORS:
            self.assertIn(text, contract)
            self.assertIn(text, guide)
        self.assertIn("minimum plugin version `0.3.1`", guide)
        self.assertIn("minimum plugin version is 0.3.1", acceptance)
        for content in (contract, acceptance, guide):
            self.assertNotIn("forbidden_origin", content)
            self.assertNotIn("Browser clients are unsupported", content)

    def test_runtime_files_have_no_superseded_contract(self):
        runtime_paths = list((self.repo_root / "plugins").rglob("*.md"))
        runtime_paths += list((self.repo_root / "plugins").rglob("*.yaml"))
        forbidden = (
            "lihi-switch-workgroup",
            "account_group",
            "supports_custom_slug",
            "site_create.domain",
            "consent-based URL shortening",
        )
        for path in runtime_paths:
            content = self.read(path)
            for token in forbidden:
                with self.subTest(path=path, token=token):
                    self.assertNotIn(token, content)
            self.assertIsNone(re.search(r"(?<!account_)\bswitch_group\b", content))

    def test_guides_are_language_separated_and_internal_guides_do_not_install(self):
        english = [self.repo_root / "README.md"] + [
            root / "README.md" for root in self.roots.values()
        ]
        chinese = [self.repo_root / "README.zh-TW.md"] + [
            root / "README.zh-TW.md" for root in self.roots.values()
        ]
        cjk = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
        for path in english:
            self.assertIsNone(cjk.search(self.read(path)), str(path))
        for path in chinese:
            self.assertIsNotNone(cjk.search(self.read(path)), str(path))
        for path in english[1:] + chinese[1:]:
            content = self.read(path)
            self.assertNotIn("plugin marketplace add", content)
            self.assertNotIn("## Install", content)
            self.assertNotIn("## 安裝", content)


if __name__ == "__main__":
    unittest.main()
