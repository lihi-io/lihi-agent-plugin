# lihi shortening workflow

Read this file completely after local detection identifies at least one fresh long URL and before the first lihi tool call.

## Revalidate the handoff

- Carry the exact inspected content snapshot, detector JSON, ordered creation batch, external-action intent, cumulative confirmed-generated ledger, uncertain creation states, and authentication-recovery budget.
- The inspected snapshot need not be final or stable. A later edit starts a new snapshot while retaining exact confirmed short URLs and reusable confirmed mappings from the conversation ledger.
- A confirmed ledger entry contains one exact validated `long_url` → `short_url` mapping. Exclude every recorded `short_url`, automatically reuse an exact `long_url` mapping, and never treat an uncertain result as confirmed.
- Recompute the batch from the detector's first-seen unique URLs. Remove confirmed short URLs and reusable long URLs. Duplicate occurrences receive one mapping and one creation call.
- If the content or batch membership changed, discard the pending disclosure and stale offsets, rerun detection, and rebuild the batch before any MCP call. Do not repeat a disclosure when resuming the unchanged batch.
- Detector offsets are zero-based Unicode code-point indexes with exclusive `end`. Apply replacements against the immutable snapshot from greatest `start` to smallest.
- If compaction or missing context removes the exact content, detector result, mapping, uncertain dispatch state, authentication-recovery budget, or external-action intent required for the next operation, fail closed. Re-establish safe state; never infer a mapping or retry a possibly dispatched call from a summary.
- Stop before all MCP calls if detection failed, detector output is malformed, or an `embedded_credentials` rejection remains.

## Disclose the current creation batch

Immediately before the first call, give one non-blocking disclosure in the user's language. For Chinese, use:

```text
lihi 將為本批次偵測到的 <N> 個新長網址建立短網址：
1. <url-1>
2. <url-2>
```

Append `已確認的既有對應會直接重用，不會再次建立。` only when this snapshot also reuses at least one mapping. This disclosure is not a question and does not pause automatic processing. It is workflow metadata, not outbound content: never scan, shorten, publish, or include it in the final-content confirmation snapshot.

## Create and validate short URLs

- Call `site_create` exactly once per fresh unique URL in detector order with exactly `{url:<long URL>}`. The server has no long-URL reuse lookup; another conversation or unrecorded call can create another permanent short URL and consume quota.
- Prefer `structuredContent`; otherwise parse JSON from the first text block. On success require absolute HTTP(S) `short_url` and `long_url` values without user information, and require returned `long_url` to exactly equal the submitted URL.
- Before generic business-error handling, trim surrounding whitespace from the first text message and exact-match these conclusive pre-creation failures:
  - Group or account unavailable: `目前的 access token 沒有可用的預設 domain。`
  - Domain unavailable: `access token 的預設 domain 已不在目前可用網域清單中。`
- Classify these short-URL quota errors as conclusive pre-creation rejections:
  - Account: `You have reach the maximum URLs you can create`, `網址已達上限`, `网址已达上限`.
  - Work group: `The URL has reached the maximum limit specified by the workgroup`, `網址已達工作群組限定的最大上限`, `网址已达工作群组限定的最大上限`.
- On the group/account-unavailable failure, stop the entire shortening batch immediately. In Chinese, show this guidance followed by the exact unmodified inspected content snapshot:

  ```text
  lihi 目前的工作群組或帳號無法使用，本次縮短已停止。
  若要繼續縮短，請先要求 agent「切換工作群組」（使用 `$lihi-switch-group`）；若沒有可切換的群組，請使用 `$lihi-account` 檢查帳號狀態。處理完成後，再使用 `$lihi-shorten`，或重新要求 agent 潤飾／改寫文案。

  以下為未套用本次短網址替換的原本文案：
  <original-inspected-content-snapshot>
  ```

- On the domain-unavailable failure, stop the entire shortening batch immediately. In Chinese, show this guidance followed by the exact unmodified inspected content snapshot:

  ```text
  lihi 目前的短網址網域已不在可用清單中，本次縮短已停止。
  若要繼續縮短，請先要求 agent「切換短網址網域」（使用 `$lihi-switch-domain`）。切換完成後，再使用 `$lihi-shorten`，或重新要求 agent 潤飾／改寫文案。

  以下為未套用本次短網址替換的原本文案：
  <original-inspected-content-snapshot>
  ```

- On a work-group quota failure, stop the entire shortening batch immediately. In Chinese, show this guidance followed by the exact unmodified inspected content snapshot:

  ```text
  lihi 目前的工作群組已達短網址建立上限，本次縮短已停止。
  若要繼續縮短，請先要求 agent「切換工作群組」（使用 `$lihi-switch-group`）。切換完成後，再使用 `$lihi-shorten`，或重新要求 agent 潤飾／改寫文案。

  以下為未套用本次短網址替換的原本文案：
  <original-inspected-content-snapshot>
  ```

- For each of those three termination branches, make no further call for the failed URL or any remaining batch URL, never call a selector discovery or switch tool, never retry automatically, and block any requested external release. Apply no reusable or newly confirmed mapping to the displayed content. Keep every earlier validated mapping in the conversation ledger, but do not display a current-batch mapping summary or mention earlier creation side effects. The user must start a later, independent switch or account workflow and then invoke shortening again.
- For an account quota failure, preserve the original URL, explain the account limit, provide `方案與額度說明：https://knowledge.lihi.io/pricing`, and ask whether to retry after resolution, keep this URL unchanged for the current snapshot, or cancel. Treat that guidance URL as metadata and never scan or shorten it.
- Treat every other `result.isError: true` as failure even with HTTP 200. Present the first message and ask whether to revise the input, keep this URL unchanged for the current snapshot, or cancel. An unchanged choice records an intentional snapshot-local exception so the automatic flow does not immediately reattempt it.
- Treat top-level JSON-RPC errors, HTTP 429, malformed or incomplete responses, timeout, and connection loss as protocol or transport failures. If dispatch may have occurred, record it separately as possibly created, warn that an unused link may exist, and never claim no link was created.
- `site_create` is non-idempotent. Retry only when non-dispatch is conclusive. Never replay a possibly dispatched call, and never release partially replaced content.

## Maintain the conversation ledger

- Add a mapping only after a successful result passes every validation. Deduplicate exact mappings and preserve first-confirmed order.
- Retain validated mappings even when a later URL in the same batch ends shortening through a documented group/account/domain termination branch. Reuse them only in a later shortening run; do not apply or disclose them in the terminated run.
- Keep the cumulative ledger private. Do not dump mappings from earlier batches. Report only the current batch's confirmed or uncertain state when needed.
- The ledger is conversation-scoped. In a new conversation, do not claim a previous long URL was already shortened. Preserve a short URL the user explicitly identifies, but do not invent its long-URL mapping.

## Replace, report, and release

- Complete every non-excepted creation before preparing replaced content. Replace all duplicate occurrences with the single validated mapping while preserving punctuation, Markdown labels, formatting, and surrounding text.
- Never silently fall back after failure. A URL explicitly kept unchanged for this exact snapshot is complete; an unresolved or uncertain URL is not.
- After a successful batch, show the current updated human-visible content snapshot. Outside that content, list only mappings newly created in this batch, in creation order:

  ```text
  本次新建短網址：
  <long-url-1> → <short-url-1>
  <long-url-2> → <short-url-2>
  ```

- The mapping summary is workflow metadata. Do not scan, shorten, publish, or include it in the exact content snapshot awaiting confirmation.
- Perform an external action only when explicitly requested and after the user confirms the exact complete content. Copy-only work ends after showing the result and never implies publication.
- Any content edit invalidates confirmation and returns to local detection while preserving only exact confirmed mappings and accurate uncertain states.
