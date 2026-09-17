import sys
from pathlib import Path
from ctxfw.core.topological import TopologicalResolver
from ctxfw.core.pruner import PolyglotASTPruner

PROJECT_ROOT = Path(r"C:\sermujer")
TARGET_MODULES = [
    "apps/api/main.py",
    "apps/api/app/routes/checkout.py",
    "apps/api/app/routes/webhooks.py",
    "apps/api/app/routes/checkin.py",
    "apps/api/app/routes/admin.py",
    "apps/api/app/core/config.py",
    "apps/api/app/core/database.py"
]

resolver = TopologicalResolver(root_dir=PROJECT_ROOT)
pruner = PolyglotASTPruner()

print("=" * 80)
print(f"{'MODULO OBJETIVO':<35} | {'ORIG TOK':<10} | {'PRUNED':<10} | {'SAVINGS %':<10}")
print("-" * 80)

total_orig, total_pruned = 0, 0

for rel_path in TARGET_MODULES:
    target_file = PROJECT_ROOT / rel_path
    if not target_file.exists():
        continue
    
    manifest = resolver.resolve(target_file)
    orig_tokens = manifest.total_tokens
    
    pruned_tokens = 0
    for dep in manifest.dependencies:
        if dep.depth_level == 0:
            pruned_tokens += dep.token_count
        else:
            try:
                code = dep.file_path.read_text(encoding="utf-8", errors="replace")
                res = pruner.prune_by_depth(code, dep.file_path.suffix, dep.depth_level)
                pruned_tokens += res.pruned_tokens
            except Exception:
                pruned_tokens += dep.token_count
                
    savings = ((orig_tokens - pruned_tokens) / orig_tokens * 100) if orig_tokens else 0.0
    total_orig += orig_tokens
    total_pruned += pruned_tokens
    
    print(f"{rel_path:<35} | {orig_tokens:<10} | {pruned_tokens:<10} | {savings:<9.1f}%")

print("-" * 80)
net_savings = ((total_orig - total_pruned) / total_orig * 100) if total_orig else 0.0
print(f"{'TOTAL PIPELINE TRANSACCIONAL':<35} | {total_orig:<10} | {total_pruned:<10} | {net_savings:<9.1f}%")
print("=" * 80)

saved_tokens = total_orig - total_pruned
simulated_calls = 500
total_saved_usd = (saved_tokens * simulated_calls / 1_000_000) * 3.00

print(f"\n[*] Tokens podados por ciclo transaccional: {saved_tokens:,}")
print(f"[*] Ahorro FinOps proyectado (500 llamadas de agentes): ${total_saved_usd:.2f} USD")
