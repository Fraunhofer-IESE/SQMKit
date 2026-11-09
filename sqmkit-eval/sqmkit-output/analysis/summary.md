# SQMKit evaluation analysis

Units: 110 criteria assessments (10 repositories x 11 criteria).

## Inter-group agreement (ordinal Krippendorff's alpha)

| Group | alpha |
|---|---:|
| Human (1, 2, 3) | 0.7678 |
| LLM (Qwen, DeepSeek, CLEF medians) | 0.8674 |

## Human consensus vs model consensus

Linearly weighted Cohen's kappa on the 1-5 scale.

| Comparison | kappa |
|---|---:|
| Human median vs Qwen median | 0.7450 |
| Human median vs DeepSeek median | 0.7245 |
| Human median vs CLEF median | 0.6164 |

## Run consistency

| Model | Identical across 3 runs | Within 1 point |
|---|---:|---:|
| Qwen | 81/110 = 73.6% | 110/110 = 100.0% |
| DeepSeek | 71/110 = 64.5% | 110/110 = 100.0% |
| CLEF | 105/110 = 95.5% | 108/110 = 98.2% |
