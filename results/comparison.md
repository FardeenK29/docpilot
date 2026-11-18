| Metric | v1 baseline | + fix ctx reload | + 1.5B router (rejected) | + rules & score gate | + k=4, cap, abstain | v1 baseline → + k=4, cap, abstain |
|---|---:|---:|---:|---:|---:|---:|
| Question pass rate | 71% | 71% | 68% | 71% | 68% | -3 pts |
| Retrieval hit rate | 97% | 97% | 95% | 97% | 95% | -3 pts |
| Citation accuracy | 76% | 76% | 74% | 76% | 82% | +5 pts |
| Key-fact recall | 86% | 86% | 83% | 86% | 82% | -4 pts |
| Abstains on unanswerable | 75% | 75% | 75% | 75% | 75% | same |
| Refuses off-topic | 100% | 100% | 25% | 100% | 100% | same |
| Ticket / escalation routing | 100% | 100% | 100% | 100% | 100% | same |
| PII leaks | 0 | 0 | 0 | 0 | 0 |  |
| Latency p50 | 29.0 s | 24.2 s | 22.5 s | 22.7 s | 16.9 s | -42% |
| Latency p95 | 44.5 s | 42.0 s | 41.2 s | 41.3 s | 29.3 s | -34% |
| LLM calls / query | 1.88 | 1.88 | 1.18 | 0.88 | 0.88 | -53% |
| Input tokens / query | 1,307 | 1,307 | 1,260 | 1,186 | 642 | -51% |
| Output tokens / query | 125 | 125 | 121 | 117 | 103 | -18% |
| Projected $ / 1k queries | $0.271 | $0.271 | $0.261 | $0.248 | $0.158 | -42% |

*Projected $ = measured tokens x $0.15/$0.6 per 1M in/out. All runs use local Qwen2.5 models, which cost $0 to run.*
