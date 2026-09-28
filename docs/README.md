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

設定頁面的 Gemini 選項為 **Gemini 3.5 Flash-Lite** (`gemini-3.5-flash-lite`) 與 **Gemini 3.8 Flash** (`gemini-3.8-flash`)。Google 的[模型清單](https://ai.google.dev/gemini-api/docs/models)與[退場時程](https://ai.google.dev/gemini-api/docs/deprecations)在 2026-09-29 將兩者列為穩定模型，且未宣布停止日期。曾儲存舊 Gemini 型號的使用者需在設定頁重新選擇並儲存；舊型號不會送出 API 請求。正式 provider 可用性仍需經授權的 `generateContent` 呼叫驗證。

## 文件互連

- [architecture-overview.md](./architecture-overview.md) 會引導你到 `architecture.md` 進一步看實際模組與流程。
- `architecture.md` 會回指 `architecture-overview.md` 作為新進導向入口。
