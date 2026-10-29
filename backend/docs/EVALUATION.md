# Evaluation report

*SQL-Based Real-Time Fraud Detection and Transaction Monitoring System* — generated 29 Oct 2026 15:28 by `flask evaluation-report` (metric run #2).

## Data set and method

* **5,114** synthetic payments (5,025 labelled), 3.0% fraud, spread over the last 7 days, sent through the HTTP ingestion API by parallel workers.
* Normal payments come from customer spending profiles; fraud is injected as labelled stories, one per rule R1–R9 plus rule combinations (R1+R4, R3+R6, R5+R8).
* The labelled payments are in [`evaluation_dataset.csv`](evaluation_dataset.csv).
* A payment counts as *flagged* when it is held (REVIEW) or blocked. Latency is measured from request receipt to the **committed** decision.
* Decision bands: hold from **40**, block from **70**; external model score weight 0% (0 = off).

## Results against Table 3.1

| Parameter | Target | Measured | Result |
|---|---|---|---|
| End-to-end decision latency (p95) | ≤ 500 ms | 76.8 ms (median 48.5 ms) | ✅ Pass |
| Sustained throughput | ≥ 100 TPS | 113 TPS | ✅ Pass |
| Detection rate (recall) | ≥ 90% | 91.3% (137 of 150) | ✅ Pass |
| False-positive rate | ≤ 5% | 0.27% (13 of 4875) | ✅ Pass |
| Explainability | 100% of flagged list their rules | 100.0% (158 of 158) | ✅ Pass |
| Dashboard freshness | new alerts visible within 3 s | worst case 2.11 s (p95 decision + queue read + 2 s refresh; not yet measured on screen) | ✅ Pass |

Precision **91.3%**, F1-score **91.3%**.

## Confusion matrix

| | Flagged | Approved |
|---|---|---|
| **Fraud** | 137 (TP) | 13 (FN) |
| **Genuine** | 13 (FP) | 4862 (TN) |

## Per fraud story

| Story | Rules it must fire | All fired | Caught (recall) |
|---|---|---|---|
| R1 | R1 | 13/13 | 0/13 (0%) |
| R2 | R2 | 13/13 | 13/13 (100%) |
| R3 | R3 | 13/13 | 13/13 (100%) |
| R4 | R4 | 13/13 | 13/13 (100%) |
| R5 | R5 | 13/13 | 13/13 (100%) |
| R6 | R6 | 13/13 | 13/13 (100%) |
| R7 | R7 | 12/12 | 12/12 (100%) |
| R8 | R8 | 12/12 | 12/12 (100%) |
| R9 | R9 | 12/12 | 12/12 (100%) |
| R1+R4 | R1 + R4 | 12/12 | 12/12 (100%) |
| R3+R6 | R3 + R6 | 12/12 | 12/12 (100%) |
| R5+R8 | R5 + R8 | 12/12 | 12/12 (100%) |

## Per rule

| Rule | Name | Weight (tuned) | Weight (spec) | Fired | Precision |
|---|---|---|---|---|---|
| R1 | Unusually large amount | 35 | 30 | 49 | 100% |
| R2 | Too many payments too fast | 40 | 25 | 26 | 54% |
| R3 | Impossible travel | 45 | 35 | 27 | 96% |
| R4 | New device, big amount | 40 | 20 | 33 | 100% |
| R5 | Late-night large payment | 40 | 10 | 25 | 100% |
| R6 | Known fraudster | 70 | 50 | 25 | 100% |
| R7 | Splitting money to dodge limits | 40 | 15 | 12 | 100% |
| R8 | Sleeping account wakes up | 40 | 20 | 24 | 100% |
| R9 | OTP / phishing-link fraud | 55 | 45 | 12 | 100% |

## Load test with and without the composite indexes

Same labelled payments, first with the composite `(account_id, txn_time)` and `(account_id, city, txn_time)` indexes, then with only a plain `(account_id)` index.

| | With indexes | Without | |
|---|---|---|---|
| Latency p50 | 47.7 ms | 48.1 ms | |
| Latency p95 | 76.3 ms | 76.2 ms | 1.0× faster with indexes |
| Throughput | 114 TPS | 114 TPS | 1.0× with indexes |
| Recall | 91.7% | 91.7% | same rules, same result |

## Notes

* Rule weights were tuned from the specification's starting values (Table 4.4); see [RULES.md](RULES.md#how-the-weights-were-tuned) for why. Thresholds are the specification's.
* Every number here comes from one run on synthetic data on a single machine; rerun `flask evaluation-report` to reproduce it.
