import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open("results/results.json") as f:
    data = json.load(f)

scenarios = ["baseline", "conn_timeout", "index_isolation"]
labels = ["Baseline\n(no mitigation)", "Connection budget\n+ statement timeout", "Index isolation\n(fix noisy query)"]

good_p50 = [data[s]["good_tenants_combined"]["p50_ms"] for s in scenarios]
good_p95 = [data[s]["good_tenants_combined"]["p95_ms"] for s in scenarios]

fig, ax = plt.subplots(figsize=(8, 5))
x = range(len(scenarios))
width = 0.35
ax.bar([i - width/2 for i in x], good_p50, width, label="Good tenants p50 (ms)", color="#4C72B0")
ax.bar([i + width/2 for i in x], good_p95, width, label="Good tenants p95 (ms)", color="#DD8452")
ax.set_xticks(list(x))
ax.set_xticklabels(labels)
ax.set_ylabel("Latency (ms)")
ax.set_title("Good-tenant latency while noisy tenant runs concurrently")
ax.legend()
fig.tight_layout()
fig.savefig("results/latency_comparison.png", dpi=150)
print("saved results/latency_comparison.png")
