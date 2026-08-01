# 旁路快取命名空間重評報告

**時間**: 2026-08-02 01:02:25
**快取命名空間**: `.cache/bypass_eval/`
**歷史快取未汙染**: True
**題庫**: questions/dev.jsonl (278 prompts)
**噪音死區閾值**: 3.0

## 1. 分組方差分析

| 分組 | 時期 | 樣本數 | 平均分 | 標準差 | 方差 |
|------|------|--------|--------|--------|------|
| 候選 | 舊 | 275 | 76.8873 / 0.4912 / 0.2413 |
| 候選 | 新 | 275 | 76.8518 / 0.5163 / 0.2666 |
| 冠軍 | 舊 | 3 | 77.5278 / 0.1819 / 0.0331 |
| 冠軍 | 新 | 3 | 76.6153 / 0.4877 / 0.2379 |
| 全部 | 舊 | 278 | 76.8943 / 0.4932 / 0.2433 |
| 全部 | 新 | 278 | 76.8492 / 0.5158 / 0.2660 |

## 2. 配對差異（新分 - 舊分）

**候選**: n=275, 平均差=-0.0356, std=0.7004, min差=-2.2583, max差=1.5791
**冠軍**: n=3, 平均差=-0.9125, std=0.3063, min差=-1.1625, max差=-0.5708

## 3. 獨立樣本 t 檢定

- t = 0.8347, df = 2.05, p ≈ 0.746249
- α=0.05 顯著: False

## 4. 新舊方差比較

- 舊全部方差: 0.2433
- 新全部方差: 0.266
- 舊候選方差: 0.2413
- 新候選方差: 0.2666
- **新方差 > 舊方差: True**

## 5. 同分/近分候選（死區內）

- **prompts/candidates/candidate_1779565104.md** 舊=76.19 新=77.17
  - vs prompts/candidates/candidate_1779565152.md: 舊差=0.41 → 新差=0.10
  - vs prompts/candidates/candidate_1779565195.md: 舊差=0.71 → 新差=0.34
  - vs prompts/candidates/candidate_1779565370.md: 舊差=1.34 → 新差=0.88
  - vs prompts/candidates/candidate_1779565398.md: 舊差=0.45 → 新差=0.56
  - vs prompts/candidates/candidate_1779565467.md: 舊差=1.30 → 新差=1.08
- **prompts/candidates/candidate_1779565152.md** 舊=76.60 新=77.07
  - vs prompts/candidates/candidate_1779565195.md: 舊差=0.30 → 新差=0.24
  - vs prompts/candidates/candidate_1779565370.md: 舊差=0.93 → 新差=0.78
  - vs prompts/candidates/candidate_1779565398.md: 舊差=0.05 → 新差=0.46
  - vs prompts/candidates/candidate_1779565467.md: 舊差=0.89 → 新差=0.98
  - vs prompts/candidates/candidate_1779565516.md: 舊差=0.34 → 新差=0.92
- **prompts/candidates/candidate_1779565195.md** 舊=76.90 新=76.83
  - vs prompts/candidates/candidate_1779565370.md: 舊差=0.63 → 新差=0.55
  - vs prompts/candidates/candidate_1779565398.md: 舊差=0.25 → 新差=0.23
  - vs prompts/candidates/candidate_1779565467.md: 舊差=0.59 → 新差=0.75
  - vs prompts/candidates/candidate_1779565516.md: 舊差=0.04 → 新差=0.68
  - vs prompts/candidates/candidate_1779566193.md: 舊差=0.35 → 新差=0.35
- **prompts/candidates/candidate_1779565370.md** 舊=77.53 新=76.28
  - vs prompts/candidates/candidate_1779565398.md: 舊差=0.89 → 新差=0.32
  - vs prompts/candidates/candidate_1779565467.md: 舊差=0.05 → 新差=0.20
  - vs prompts/candidates/candidate_1779565516.md: 舊差=0.59 → 新差=0.14
  - vs prompts/candidates/candidate_1779566193.md: 舊差=0.28 → 新差=0.19
  - vs prompts/candidates/candidate_1779611170.md: 舊差=1.15 → 新差=0.95
- **prompts/candidates/candidate_1779565398.md** 舊=76.64 新=76.60
  - vs prompts/candidates/candidate_1779565467.md: 舊差=0.84 → 新差=0.52
  - vs prompts/candidates/candidate_1779565516.md: 舊差=0.30 → 新差=0.46
  - vs prompts/candidates/candidate_1779566193.md: 舊差=0.61 → 新差=0.13
  - vs prompts/candidates/candidate_1779611170.md: 舊差=0.26 → 新差=0.63
  - vs prompts/candidates/candidate_1779612568.md: 舊差=0.28 → 新差=0.10
- **prompts/candidates/candidate_1779565467.md** 舊=77.48 新=76.08
  - vs prompts/candidates/candidate_1779565516.md: 舊差=0.55 → 新差=0.06
  - vs prompts/candidates/candidate_1779566193.md: 舊差=0.23 → 新差=0.39
  - vs prompts/candidates/candidate_1779611170.md: 舊差=1.10 → 新差=1.15
  - vs prompts/candidates/candidate_1779612568.md: 舊差=1.12 → 新差=0.62
  - vs prompts/candidates/candidate_1779613101.md: 舊差=0.65 → 新差=0.84
- **prompts/candidates/candidate_1779565516.md** 舊=76.94 新=76.15
  - vs prompts/candidates/candidate_1779566193.md: 舊差=0.31 → 新差=0.33
  - vs prompts/candidates/candidate_1779611170.md: 舊差=0.55 → 新差=1.09
  - vs prompts/candidates/candidate_1779612568.md: 舊差=0.57 → 新差=0.55
  - vs prompts/candidates/candidate_1779613101.md: 舊差=0.11 → 新差=0.78
  - vs prompts/candidates/candidate_1779613246.md: 舊差=0.36 → 新差=1.16
- **prompts/candidates/candidate_1779566193.md** 舊=77.25 新=76.47
  - vs prompts/candidates/candidate_1779611170.md: 舊差=0.87 → 新差=0.76
  - vs prompts/candidates/candidate_1779612568.md: 舊差=0.88 → 新差=0.23
  - vs prompts/candidates/candidate_1779613101.md: 舊差=0.42 → 新差=0.45
  - vs prompts/candidates/candidate_1779613246.md: 舊差=0.05 → 新差=0.83
  - vs prompts/candidates/candidate_1779643398.md: 舊差=0.52 → 新差=0.21
- **prompts/candidates/candidate_1779611170.md** 舊=76.38 新=77.23
  - vs prompts/candidates/candidate_1779612568.md: 舊差=0.02 → 新差=0.53
  - vs prompts/candidates/candidate_1779613101.md: 舊差=0.45 → 新差=0.31
  - vs prompts/candidates/candidate_1779613246.md: 舊差=0.92 → 新差=0.07
  - vs prompts/candidates/candidate_1779643398.md: 舊差=0.35 → 新差=0.97
  - vs prompts/candidates/candidate_1779643584.md: 舊差=0.15 → 新差=0.55
- **prompts/candidates/candidate_1779612568.md** 舊=76.37 新=76.70
  - vs prompts/candidates/candidate_1779613101.md: 舊差=0.46 → 新差=0.23
  - vs prompts/candidates/candidate_1779613246.md: 舊差=0.93 → 新差=0.61
  - vs prompts/candidates/candidate_1779643398.md: 舊差=0.36 → 新差=0.43
  - vs prompts/candidates/candidate_1779643584.md: 舊差=0.13 → 新差=0.02
  - vs prompts/candidates/candidate_1779643657.md: 舊差=0.05 → 新差=0.20
- **prompts/candidates/candidate_1779613101.md** 舊=76.83 新=76.92
  - vs prompts/candidates/candidate_1779613246.md: 舊差=0.47 → 新差=0.38
  - vs prompts/candidates/candidate_1779643398.md: 舊差=0.10 → 新差=0.66
  - vs prompts/candidates/candidate_1779643584.md: 舊差=0.60 → 新差=0.24
  - vs prompts/candidates/candidate_1779643657.md: 舊差=0.52 → 新差=0.42
  - vs prompts/candidates/candidate_1779646042.md: 舊差=0.62 → 新差=0.30
- **prompts/candidates/candidate_1779613246.md** 舊=77.30 新=77.31
  - vs prompts/candidates/candidate_1779643398.md: 舊差=0.57 → 新差=1.04
  - vs prompts/candidates/candidate_1779643584.md: 舊差=1.07 → 新差=0.62
  - vs prompts/candidates/candidate_1779643657.md: 舊差=0.99 → 新差=0.81
  - vs prompts/candidates/candidate_1779646042.md: 舊差=1.10 → 新差=0.08
  - vs prompts/candidates/candidate_1779646345.md: 舊差=0.25 → 新差=1.61
- **prompts/candidates/candidate_1779643398.md** 舊=76.73 新=76.27
  - vs prompts/candidates/candidate_1779643584.md: 舊差=0.50 → 新差=0.42
  - vs prompts/candidates/candidate_1779643657.md: 舊差=0.42 → 新差=0.23
  - vs prompts/candidates/candidate_1779646042.md: 舊差=0.53 → 新差=0.96
  - vs prompts/candidates/candidate_1779646345.md: 舊差=0.82 → 新差=0.57
  - vs prompts/candidates/candidate_1779646345_risk_repair.md: 舊差=0.03 → 新差=0.46
- **prompts/candidates/candidate_1779643584.md** 舊=76.23 新=76.68
  - vs prompts/candidates/candidate_1779643657.md: 舊差=0.08 → 新差=0.18
  - vs prompts/candidates/candidate_1779646042.md: 舊差=0.03 → 新差=0.55
  - vs prompts/candidates/candidate_1779646345.md: 舊差=1.32 → 新差=0.98
  - vs prompts/candidates/candidate_1779646345_risk_repair.md: 舊差=0.46 → 新差=0.05
  - vs prompts/candidates/candidate_1779646345_risk_repair_v2.md: 舊差=0.19 → 新差=0.47
- **prompts/candidates/candidate_1779643657.md** 舊=76.31 新=76.50
  - vs prompts/candidates/candidate_1779646042.md: 舊差=0.11 → 新差=0.73
  - vs prompts/candidates/candidate_1779646345.md: 舊差=1.24 → 新差=0.80
  - vs prompts/candidates/candidate_1779646345_risk_repair.md: 舊差=0.38 → 新差=0.23
  - vs prompts/candidates/candidate_1779646345_risk_repair_v2.md: 舊差=0.11 → 新差=0.66
  - vs prompts/candidates/candidate_1779646887.md: 舊差=1.40 → 新差=0.07
- **prompts/candidates/candidate_1779646042.md** 舊=76.20 新=77.23
  - vs prompts/candidates/candidate_1779646345.md: 舊差=1.35 → 新差=1.53
  - vs prompts/candidates/candidate_1779646345_risk_repair.md: 舊差=0.49 → 新差=0.50
  - vs prompts/candidates/candidate_1779646345_risk_repair_v2.md: 舊差=0.22 → 新差=0.07
  - vs prompts/candidates/candidate_1779646887.md: 舊差=1.51 → 新差=0.66
  - vs prompts/candidates/candidate_1779647180.md: 舊差=1.05 → 新差=0.07
- **prompts/candidates/candidate_1779646345.md** 舊=77.55 新=75.70
  - vs prompts/candidates/candidate_1779646345_risk_repair.md: 舊差=0.85 → 新差=1.03
  - vs prompts/candidates/candidate_1779646345_risk_repair_v2.md: 舊差=1.13 → 新差=1.46
  - vs prompts/candidates/candidate_1779646887.md: 舊差=0.16 → 新差=0.87
  - vs prompts/candidates/candidate_1779647180.md: 舊差=0.30 → 新差=1.60
  - vs prompts/candidates/candidate_1779647201_raw_overlength.md: 舊差=2.11 → 新差=0.85
- **prompts/candidates/candidate_1779646345_risk_repair.md** 舊=76.70 新=76.73
  - vs prompts/candidates/candidate_1779646345_risk_repair_v2.md: 舊差=0.28 → 新差=0.43
  - vs prompts/candidates/candidate_1779646887.md: 舊差=1.02 → 新差=0.16
  - vs prompts/candidates/candidate_1779647180.md: 舊差=0.56 → 新差=0.57
  - vs prompts/candidates/candidate_1779647201_raw_overlength.md: 舊差=1.25 → 新差=0.18
  - vs prompts/candidates/candidate_1779647213.md: 舊差=0.61 → 新差=0.27
- **prompts/candidates/candidate_1779646345_risk_repair_v2.md** 舊=76.42 新=77.16
  - vs prompts/candidates/candidate_1779646887.md: 舊差=1.29 → 新差=0.59
  - vs prompts/candidates/candidate_1779647180.md: 舊差=0.83 → 新差=0.14
  - vs prompts/candidates/candidate_1779647201_raw_overlength.md: 舊差=0.98 → 新差=0.61
  - vs prompts/candidates/candidate_1779647213.md: 舊差=0.89 → 新差=0.70
  - vs prompts/candidates/candidate_1779650804.md: 舊差=0.38 → 新差=0.30
- **prompts/candidates/candidate_1779646887.md** 舊=77.71 新=76.57
  - vs prompts/candidates/candidate_1779647180.md: 舊差=0.46 → 新差=0.73
  - vs prompts/candidates/candidate_1779647201_raw_overlength.md: 舊差=2.27 → 新差=0.02
  - vs prompts/candidates/candidate_1779647213.md: 舊差=0.40 → 新差=0.11
  - vs prompts/candidates/candidate_1779650804.md: 舊差=0.92 → 新差=0.30
  - vs prompts/candidates/candidate_1779650829_raw_overlength.md: 舊差=1.79 → 新差=0.76

## 6. 差距拉開證據

- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779565398.md: 舊差=0.45 → 新差=0.56 (×1.24)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779565516.md: 舊差=0.75 → 新差=1.02 (×1.36)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779612568.md: 舊差=0.18 → 新差=0.47 (×2.60)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779643398.md: 舊差=0.54 → 新差=0.90 (×1.66)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779643584.md: 舊差=0.05 → 新差=0.48 (×10.55)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779643657.md: 舊差=0.12 → 新差=0.67 (×5.33)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779646042.md: 舊差=0.02 → 新差=0.06 (×3.74)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779651433_raw_overle: 舊差=0.67 → 新差=0.89 (×1.34)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779652679.md: 舊差=0.12 → 新差=0.48 (×3.97)
- prompts/candidates/candidate_1779565104.md vs prompts/candidates/candidate_1779652958.md: 舊差=0.38 → 新差=1.40 (×3.66)

## 7. 結論

- 新計分方差 > 舊計分方差: **True**
- 至少一組可量測拉開差距: **True**
- **整體判定: PASS**

## 8. 個項明細（前 30 筆）

| 分組 | 路徑 | Hash | 舊分 | 新分 | 差 | 旁路快取 |
|------|------|------|------|------|-----|----------|
| candidate | prompts/candidates/candidate_1779565104.md | 7086c1fa6326 | 76.19 | 77.17 | +0.98 | False |
| candidate | prompts/candidates/candidate_1779565152.md | 94ef953a7648 | 76.60 | 77.07 | +0.47 | False |
| candidate | prompts/candidates/candidate_1779565195.md | 6968726f1127 | 76.90 | 76.83 | -0.07 | False |
| candidate | prompts/candidates/candidate_1779565370.md | 7e225ea04693 | 77.53 | 76.28 | -1.25 | False |
| candidate | prompts/candidates/candidate_1779565398.md | cc8e99eda097 | 76.64 | 76.60 | -0.04 | False |
| candidate | prompts/candidates/candidate_1779565467.md | 82ba02031f4f | 77.48 | 76.08 | -1.40 | False |
| candidate | prompts/candidates/candidate_1779565516.md | c447646f19d9 | 76.94 | 76.15 | -0.79 | False |
| candidate | prompts/candidates/candidate_1779566193.md | e8a1a886a737 | 77.25 | 76.47 | -0.78 | False |
| candidate | prompts/candidates/candidate_1779611170.md | b986b4bb985f | 76.38 | 77.23 | +0.85 | False |
| candidate | prompts/candidates/candidate_1779612568.md | fd8374122705 | 76.37 | 76.70 | +0.33 | False |
| candidate | prompts/candidates/candidate_1779613101.md | b29fd99381bc | 76.83 | 76.92 | +0.10 | False |
| candidate | prompts/candidates/candidate_1779613246.md | 0b0ed9835ec3 | 77.30 | 77.31 | +0.01 | False |
| candidate | prompts/candidates/candidate_1779643398.md | 8551982af9f5 | 76.73 | 76.27 | -0.46 | False |
| candidate | prompts/candidates/candidate_1779643584.md | 14cb6d6debf0 | 76.23 | 76.68 | +0.45 | False |
| candidate | prompts/candidates/candidate_1779643657.md | 326b8a95a360 | 76.31 | 76.50 | +0.19 | False |
| candidate | prompts/candidates/candidate_1779646042.md | 43646b60d007 | 76.20 | 77.23 | +1.03 | False |
| candidate | prompts/candidates/candidate_1779646345.md | 48cadb1819d2 | 77.55 | 75.70 | -1.85 | False |
| candidate | prompts/candidates/candidate_1779646345_risk_repai | 9cd2a619429b | 76.70 | 76.73 | +0.03 | False |
| candidate | prompts/candidates/candidate_1779646345_risk_repai | 14f896a91e46 | 76.42 | 77.16 | +0.74 | False |
| candidate | prompts/candidates/candidate_1779646887.md | d8ae6a69549a | 77.71 | 76.57 | -1.15 | False |
| candidate | prompts/candidates/candidate_1779647180.md | fb3909da93b2 | 77.25 | 77.30 | +0.05 | False |
| candidate | prompts/candidates/candidate_1779647201_raw_overle | 21db783a1a88 | 75.44 | 76.55 | +1.10 | False |
| candidate | prompts/candidates/candidate_1779647213.md | 1cd7c25b763a | 77.31 | 76.46 | -0.85 | False |
| candidate | prompts/candidates/candidate_1779650804.md | cd27606f2c05 | 76.80 | 76.86 | +0.07 | False |
| candidate | prompts/candidates/candidate_1779650829_raw_overle | ec2faa615546 | 75.92 | 77.33 | +1.40 | False |
| candidate | prompts/candidates/candidate_1779650843.md | d38299a2b87f | 76.89 | 76.92 | +0.03 | False |
| candidate | prompts/candidates/candidate_1779650863_raw_overle | 35ecc0b4747d | 77.47 | 77.42 | -0.05 | False |
| candidate | prompts/candidates/candidate_1779650877.md | 1c4d42275fbe | 77.14 | 76.55 | -0.59 | False |
| candidate | prompts/candidates/candidate_1779651433_raw_overle | 081a76eba377 | 76.85 | 76.28 | -0.58 | False |
| candidate | prompts/candidates/candidate_1779651447.md | b6b582e4c9a5 | 77.42 | 76.36 | -1.06 | False |

（共 278 筆，僅顯示前 30 筆）
