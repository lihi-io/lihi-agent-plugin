# lihi 代理外掛

其他語言：[英文版](README.md)。

透過一個 Codex 或 Claude Code 外掛使用 lihi 帳號狀態、工作群組與短網址網域切換，以及短網址功能。

## 外掛

### `lihi@lihi`

- 顯示短網址用量、額度、訂閱日期、目前工作群組與目前短網址網域。
- 先取得最新選項，再切換使用中的工作群組或短網址網域。
- 可在潤飾文案或準備對外內容時處理網址。
- 自動縮短該內容中所有符合條件的新長網址。
- 建立時使用目前 lihi 用戶端已設定的短網址網域。
- 只有在你明確要求發布並確認最終內容後，才會執行發布。
- 所有內含技能共用唯一的 `lihi` MCP 伺服器註冊。

正式環境 Streamable HTTP 端點為：

```text
https://app.lihi.com/mcp/v1/tools
```

## 安裝

正式環境市集來源為 [weedgood/lihi-agent-plugin.git](https://github.com/weedgood/lihi-agent-plugin.git)。外掛選擇器為 `lihi@lihi`，顯示名稱為 `lihi`。

### 直接從 GitHub 安裝

#### Codex

```bash
codex plugin marketplace add https://github.com/weedgood/lihi-agent-plugin.git
codex plugin add lihi@lihi
```

#### Claude Code

```bash
claude plugin marketplace add https://github.com/weedgood/lihi-agent-plugin.git
claude plugin install lihi@lihi
```

### 下載到本機後安裝

1. 從 GitHub 下載原始碼壓縮檔並解壓縮，也可以使用本機 Git 複本。
2. 找到同時包含 `.agents/plugins/marketplace.json` 與 `.claude-plugin/marketplace.json` 的解壓縮根目錄。
3. 將下方的 `/absolute/path/to/lihi-agent-plugin` 換成該根目錄的絕對路徑。

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

不要把下載的 ZIP 檔本身傳給市集指令。請先解壓縮，再使用解壓縮根目錄的絕對路徑。

## 驗證

### Codex

安裝外掛或第一次使用時，Codex 可能會要求完成 lihi 驗證。若目前工作仍偵測到需要初次驗證，或偵測到符合重新驗證條件的更新權杖失敗，Codex 會先協助執行一次 `codex mcp login lihi`。若無法代為啟動指令，或執行後仍未完成驗證，請自行在終端機執行 `codex mcp login lihi`；若無法使用該指令，再開啟 **MCP 設定 → lihi → 驗證**。已有 lihi 授權時，一般工具端點的 `401 invalid_token` 或 `Auth required` 會先由宿主嘗試更新權杖一次，不會僅因該訊號就啟動互動式登入。

安裝或更新後，請先開始新的 Codex 對話再使用外掛。若 Codex 應用程式仍顯示舊版外掛，再將應用程式完整結束後重新開啟，並另開新對話。

### Claude Code

需要驗證時，開啟 `/mcp`、選擇 lihi，然後選擇 **驗證**。

安裝或更新後，請開始新的 Claude Code 對話。

## 查看帳號資訊

依照需要詢問特定資訊：

```text
查看我的短網址額度與訂閱方案
```

```text
目前使用哪一個工作群組？
```

```text
查看我的 lihi 帳號資訊
```

最後一個一般帳號資訊請求會使用 `account_status`，依序顯示短網址用量、目前方案、續訂日期、目前工作群組與目前短網址網域。需要完整群組清單時再另外詢問可用群組。

如需切換使用中的工作群組：

```text
切換我的 lihi 工作群組
```

外掛會先呼叫 `group_options`。空白或不一致的清單會視為伺服器異常；只有一個項目時，會顯示目前僅有的工作群組後停止。外掛只會把最新清單回傳的 exact ID 傳給 `account_switch_group`，成功後直接顯示完整帳號狀態，不追加查詢。

如需切換短網址網域：

```text
切換我的 lihi 短網址網域
```

外掛一定會先取得 `domain_options`，再將選定的 exact hostname 傳給 `account_switch_domain`。中文選項清單將 owned 標示為「專屬網域 (owned)」、public 標示為「公用網域 (public)」，並建議選擇專屬網域、提供 `https://lihidomain.com/`；這段說明不會自動選擇網域。群組或網域變更後，下一個 lihi 請求可能會由宿主正常更新權杖。

## 縮短網址

請 Codex 或 Claude Code 潤飾含有連結的文案，或準備要對外發布的內容。例如：

```text
潤飾這篇貼文，並縮短其中的連結：
...
```

外掛會：

1. 直接檢測目前內容快照中的 HTTP(S) 網址，不必等待文案定稿或停止變動。
2. 告知本批次即將建立的新長網址並自動繼續。
3. 重用本對話已確認的對應，其餘每個唯一網址各呼叫一次 `site_create`。
4. 顯示目前更新後的內容，並在內容之外列出本批次新建的短網址。

同一對話後續修改內容時，會保留已確認的短網址並重用既有 mapping，只為新出現的長網址建立。lihi 目前沒有跨對話的 long URL 重用查詢；在另一個對話再次處理相同長網址，會建立新的永久短網址並消耗額度。只有在你明確要求發布並確認最終內容後，外掛才會執行發布。

若縮短流程遇到工作群組／帳號不可用、短網址網域不可用或工作群組額度上限，會停止本批次與原先要求的發布，不會自動切換選擇器，並原樣顯示檢測時的文案。請依提示另外切換工作群組或網域，再重新使用 shortening skill，或重新要求 agent 潤飾／改寫文案。

如需各宿主專用的驗證與行為說明，請參閱 [Codex 指引](plugins/codex/lihi/README.zh-TW.md) 或 [Claude Code 指引](plugins/claude/lihi/README.zh-TW.md)。
