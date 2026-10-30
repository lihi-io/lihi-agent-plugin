# lihi 用戶端套件

其他語言：[英文版](README.md)。

此外掛讓 Claude 連線至你的 lihi 帳號管理短網址，可在 Claude Code、claude.ai 與 Cowork 使用。外掛會註冊遠端 MCP 伺服器 `lihi`：

```text
https://app.lihi.io/mcp/v1/tools
```

四個技能共用這一個註冊：

- `lihi-account`：讀取帳號 email 與狀態、目前群組與網域，以及可用群組。
- `lihi-switch-group`：依最新 `group_options` 切換工作群組。
- `lihi-switch-domain`：依最新 `domain_options` 切換短網址網域。
- `lihi-shorten`：自動縮短已調整對外文案中的符合條件新網址。

## 驗證

外掛透過 OAuth 登入 lihi。登入流程與權杖更新由 Claude 應用程式管理，外掛不會儲存或要求密碼與權杖。

- **Claude Code**：需要驗證時，開啟 `/mcp`、選擇 lihi 外掛伺服器，然後選擇 **驗證**。
- **claude.ai 與 Cowork**：出現要求時，透過應用程式的連接器登入流程授權 lihi。

已有授權時，一般工具端點的 `401 invalid_token` 或宿主層級 `Auth required` 會先嘗試一次宿主管理的更新。只有初次登入，或已確認更新權杖無效、過期、遭撤銷或無法使用時，才會要求互動式驗證。沒有相符規則的錯誤只會回報並保留流程狀態，不會啟動互動式驗證。

## 傳送至 lihi 的資料

所有請求只會送往 lihi 正式環境 MCP 伺服器 `https://app.lihi.io/mcp/v1/tools`：

- `site_create`：傳送每個要縮短的長網址，並取得對應短網址。
- `account_status`、`group_options`、`domain_options`：讀取帳號 email、用量、方案、續訂日期、工作群組與短網址網域。
- `account_switch_group`、`account_switch_domain`：傳送選定的群組 ID 或網域 hostname。

外掛只傳送偵測到的網址，不會傳送周圍的文案。網址偵測由內附的 `skills/lihi-shorten/scripts/detect_urls.py` 在本機執行，只讀取目前內容快照，不會發出網路請求。在 claude.ai 與 Cowork 使用時，需要啟用程式碼執行。

請參閱 lihi [隱私權政策](https://knowledge.lihi.io/privacy-policy/) 與 [服務條款](https://knowledge.lihi.io/terms/)。如需協助，請透過 [lihistatus.com/contact](https://lihistatus.com/contact) 聯絡 lihi。

## 帳號與選擇器行為

`account_status` 提供帳號 email、用量、方案、續訂日期、目前工作群組與目前短網址網域；一般帳號狀態會先顯示帳號 email。只有查詢可用群組清單時才使用 `group_options`。兩個切換技能都會在異動前取得最新選項，成功後直接顯示 switch 回傳的完整 AccountStatus，不追加查詢。中文網域選項將 owned 標示為「專屬網域 (owned)」、public 標示為「公用網域 (public)」，並建議選擇專屬網域、提供 `https://lihidomain.com/`，但不會自動選擇。

選擇器異動可能撤銷目前 access token，但 refresh 授權仍有效；宿主只在下一個 lihi 請求需要時更新。可能已送出的切換請求不會被盲目重播。

## 短網址行為

處理對外文案時，`lihi-shorten` 會直接檢測目前內容快照，不必等待文案定稿或停止變動；告知目前建立批次後，會為每個唯一的新長網址自動呼叫一次 `site_create`。每次建立都會產生永久短網址並計入 lihi 額度。後續編修會保留已確認短網址並重用本對話的 exact mapping；lihi 不提供跨對話 long URL 重用。無法確定是否已送出的非冪等請求不會重試。

工作群組／帳號不可用、短網址網域不可用或工作群組額度上限會停止 shortening 批次與原先要求的發布。外掛會原樣顯示檢測時的文案，並等待使用者另外啟動建議的群組或網域切換後再重新縮短。

只有在使用者明確要求發布並確認完整最終內容後，外掛才會發布。建立提示與當批 mapping 摘要不會進入發布內容。

## 授權條款

依 [MIT License](LICENSE) 授權。
