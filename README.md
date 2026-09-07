# prompt-autoresearch

這個 repository 是一個受評量門檻約束的 prompt research 工具。它針對
prompts/current.md 產生候選提示詞，使用固定題庫和 rubric 做 smoke、dev、
holdout 評量，只有通過既有接受條件的候選才會更新 prompts/baseline.md。
它不是 production traffic，也不應接收真實個案或機密資料。

## 執行入口和邊界

| 入口 | 用途 | 成本界線 |
|---|---|---|
| scripts/preflight.py | 檢查題庫、baseline、run 證據和平行設定 | 只讀；可用 --offline 略過 provider key |
| infinite_evolve.py | 有 round、停止條件和成本估計的主要長跑入口 | max-rounds、平行數、timeout、budget 都先驗證 |
| auto_evolve.py | 舊版多世代相容入口 | 每個 generation 仍會進入 provider；沒有 offline 模式 |
| run_opt.py | 單次候選產生和 smoke/dev/holdout 閉環 | 會呼叫 MiniMax，不能作為離線測試入口 |
| route_evolve.py、route_loop.py | route subset 研究 | 會呼叫既有 evaluator/provider |
| scripts/evaluate.py、scripts/evaluate_routed.py | 依題庫評估答案 | 會呼叫 MiniMax；本機測試請用 fake/stub |

所有 model calls 都經過 lib/api.py。它要求 MINIMAX_API_KEY，讀取 runtime
config 的 API URL/model/timeout/retry 和 api.rate_limit.max_concurrent。
本 repository 的真實 provider endpoint 只作程式設定，不代表本次驗收會連線。

## 零成本檢查、開始和停止

不需要金鑰的 read-only preflight：

    python scripts/preflight.py --offline --json

主要長跑入口的離線 dry-run：

    python infinite_evolve.py --dry-run --max-rounds 1 --parallel 1 --route-every 0 --sleep-seconds 0

dry-run 仍會檢查題庫、baseline metadata、Git 和平行設定，然後在任何
run_opt round 前結束。--offline 只跳過 key 存在性檢查，不是假裝完成
model evaluation；帶 --require-git 的檢查可能更新被 .gitignore 排除的
output/research_git_preflight.json。

需要 provider 時，先用有限輪次和明確成本估計：

    python infinite_evolve.py --max-rounds 1 --parallel 1 --route-every 0 --budget-usd 1 --estimated-cost-per-call 0.002

max-rounds 和各 stage 平行數至少為 1；負數、非有限成本、或只給
budget-usd 而沒有正的 estimated-cost-per-call 會在 preflight 前拒絕。
API limiter 每個 process 的 max_concurrent 預設是 8；stage worker 數可以
高於它但呼叫會由 limiter 排隊，跨 process 的總量仍須由操作者自行控制。
成本 gate 依評估結果的 estimated API calls 計算，會在完整 round 後停止，
因此一次 round 可能略微超過估計預算；它不是 provider 帳單保證。

用 Ctrl+C 停止執行。不要刪除中斷留下的 runs/、候選、log 或 metadata。
這些檔案是恢復和稽核證據。

## Runtime config 和評估分割

config.json 是 runtime canonical config；lib/config.py 先載入它，再套用
environment overrides，最後驗證型別與範圍。config.yaml 由
scripts/best_version_report.py 讀取，作為報告/重現輸入；它不是 runtime
config 的自動同步鏡像，目前 config.json 和 config.yaml 的
thresholds.dev_min_improvement 已可不同。修改門檻時須明確決定兩個消費者，
不要把 YAML 數值 drift 說成 runtime 已套用。

固定題庫目前由 preflight 驗證為：

| Split | 數量 | 角色 |
|---|---:|---|
| questions/smoke.jsonl | 6 | 候選快速淘汰 |
| questions/dev.jsonl | 48 | 主要比較和治理門檻 |
| questions/holdout.jsonl | 18 | dev 通過後的防過擬合檢查 |
| questions/final.jsonl | 12 | 額外固定評估資料 |

questions/、rubrics/、scripts/ 和 program.md 是評估規則/資料，不得為了
讓候選通過而修改。holdout.jsonl 在此 clone 中是 tracked fixture，不是
外部秘密資料；協定上它只能在 dev 接受後作為結果 gate，不能拿來產生
候選或調整 prompt。若需要真正隱藏的 holdout，必須由外部 runner 提供並
另外驗證，本 repository 不宣稱已具備該隔離。

## 來源、證據和生成物

| 類別 | 路徑 | 處理方式 |
|---|---|---|
| 研究規則/程式 | *.py、lib/、api/、scripts/、program.md | source；人工 review 後修改 |
| prompt 和固定資料 | prompts/、questions/、rubrics/、schemas/ | source/fixture；保留 baseline 與 holdout |
| append-only 歷史證據 | evolution_log.jsonl、metrics.jsonl、route_*_log.jsonl、results.tsv | 由流程產生；不要手動改寫或覆蓋 |
| 每次 run 證據 | runs/、prompts/candidates/、prompts/archive/、output/ | 可再生或稽核資料；先保留，經 maintainer review 才歸檔 |
| 舊測試/覆蓋輸出 | test_output.txt、目前 tracked 的 htmlcov/ | 歷史產物；不當成最新 coverage 證據 |
| 未來本機生成物 | .cache/、新的 htmlcov/、*.lcov、.coverage*、output/ | .gitignore 排除；不刪既有 tracked evidence |

log 和 run 目錄沒有程式化自動 retention/rotation。建議每輪保留到
review 完成；之後由 maintainer 以日期和 baseline hash 歸檔，並保留
evolution_log.jsonl、metrics.jsonl 的原始副本。不要宣稱上述建議是
enforced retention。

## Holdout、最佳 baseline 和恢復

候選先寫入 prompts/candidates/，再依序通過 gatekeeper、smoke、dev，
最後才評估 holdout。只有完整接受條件通過才複製舊 baseline 到 archive 並
更新 prompts/baseline.md 和 prompts/baseline.meta.json；失敗流程會把
prompts/current.md 還原。baseline metadata 的 prompt_hash、dev/holdout
run 路徑是恢復時的交叉檢查，不是新的評估真相。

中斷後按以下順序處理：

1. 保留現有 log、run、candidate 和 output；先執行
   git status --short，確認是否有未完成的 current.md 變更。
2. 以 prompts/baseline.meta.json 的 prompt_hash 對照
   prompts/baseline.md；hash 不符時先停下，禁止 promote 或覆蓋證據。
3. 查看最後一筆 evolution_log.jsonl、候選 scorecard 和 run summary，
   判斷停在 candidate generation、smoke、dev 或 holdout。沒有完整 summary
   的 run 是未完成證據。
4. 若 current 只是未完成候選，保留候選檔後再將 current 恢復為 baseline；
   接著先跑離線 dry-run。不要把未完成的 run 當成可重用結果，也不要重跑
   外部 provider 來補未知狀態。
5. 重新研究時從新的有限 invocation 開始，明確給 max-rounds、stage
   平行數和 budget/單次成本估計。這個工具沒有自動 resume 或 spend
   de-duplication；是否重用既有 run 必須由 maintainer 依證據決定。

## 公開資料與發布限制

不要把真實個資、案件內容、憑證、provider response、內部 endpoint 或
使用者資料放進題庫、prompt、log、run 或 issue evidence。此 repository
沒有 production publish workflow；api/ 和 index.html 是本機工具/UI
表面，不能視為已部署。任何 provider call、真實 holdout、模型演化和
部署都不在本機 contract 驗收內。
