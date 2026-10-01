# 文件索引

> 本目錄收斂 Prompt AutoResearch 文件入口，方便新成員快速找到需要的說明文件與導覽順序。

## 主要文件

- [架構總覽（新進版）](./architecture-overview.md)  
  - 給第一次接手專案的快速閱讀順序與核心術語導覽。
- [Prompt AutoResearch v3 架構總覽](./architecture.md)  
  - 收錄模組職責、資料流與 API 路徑的完整細節。
- [最佳版本證據契約](./best-version-evidence-contract.md)  
  - 證據報告的 canonical schema、最小完整證據夾具與 fail-closed 規則。

## 測試與輪次紀錄

- [第 1 輪測試筆記](./codex-round-1.md)
- [第 2 輪測試筆記](./codex-round-2.md)
- [第 3 輪測試筆記](./codex-round-3.md)
- [第 4 輪測試筆記](./codex-round-4.md)
- [第 5 輪測試筆記](./codex-round-5.md)

## 導覽建議

1. 先看 [架構總覽（新進版）](./architecture-overview.md)
2. 再看 [Prompt AutoResearch v3 架構總覽](./architecture.md) 補齊細節
3. 回頭追看 `output/` 的實驗報告與歷史 `runs/` 決策紀錄

## 瀏覽器 Gemini 模型

設定頁面的 Gemini 選項為 **Gemini 2.5 Flash** (`gemini-2.5-flash`) 與 **Gemini 2.5 Pro** (`gemini-2.5-pro`)，沿用原本「快速演化 / 深度邏輯」兩種角色。已於 2025-09-29 shutdown 的 `gemini-1.5-flash` / `gemini-1.5-pro` 已從可選清單移除（[Google 退場時程](https://ai.google.dev/gemini-api/docs/changelog)）。

行為契約：

- `callGeminiAPI()` 在送出前比對可選清單；已退場或未列出的 model ID 直接拒絕，不會送出請求。
- 曾儲存舊 Gemini 型號的使用者，設定頁會顯示「請重新選擇 Gemini 模型並儲存」，且在重新選擇前無法儲存，舊 ID 不會被沿用。
- 型號清單以 Google 官方[模型清單](https://ai.google.dev/gemini-api/docs/models)與[退場時程](https://ai.google.dev/gemini-api/docs/deprecations)為準；升級型號前需重新核對當時 lifecycle。
- 正式 provider 可用性仍為 `NEEDS_RUNTIME_VERIFICATION`：需在有明確測試授權的環境以選定替代型號做一次 bounded `generateContent` smoke 後才能宣告恢復，單元測試只驗證 selector 與請求組裝契約。

## 文件互連

- [architecture-overview.md](./architecture-overview.md) 會引導你到 `architecture.md` 進一步看實際模組與流程。
- `architecture.md` 會回指 `architecture-overview.md` 作為新進導向入口。
