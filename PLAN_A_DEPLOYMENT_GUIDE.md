# Plan A Migration - Quick Start Deployment Guide

## Overview

This guide walks through deploying **Plan A Model Migration** - upgrading from Qwen2.5 + local embeddings to **Qwen3 + API-based dense retrieval + neural reranking**.

**Status**: ✅ Code Complete | 🔄 Ready for Testing

---

## 1. Pre-Deployment Checklist

### Environment Setup

```bash
# 1. Verify SiliconFlow API credentials are set
echo "SF_API_KEY=$SF_API_KEY"
echo "SF_BASE_URL=$SF_BASE_URL"

# If not set, configure them:
export SF_API_KEY="your-api-key-here"
export SF_BASE_URL="https://api.siliconflow.cn/v1"

# 2. Verify Python environment
python --version  # Should be 3.9+
pip list | grep -E "flask|numpy|requests"  # Verify core dependencies
```

### Code Verification

```bash
# 1. Check syntax of modified files
python -m py_compile app.py
python -m py_compile search_engine.py
python -m py_compile retrieval/dense.py
python -m py_compile retrieval/reranker.py

# 2. Import check (quick validation)
python -c "from search_engine import EmojiSearchEngine; print('✓ Imports OK')"
```

---

## 2. Running Comprehensive Tests

```bash
# Full test suite (recommended first)
python test_plan_a_migration.py

# Expected output: All 6 tests should PASS
# - Test 1: API Connectivity
# - Test 2: APIEmbeddingRetriever  
# - Test 3: NeuralReranker
# - Test 4: EmojiSearchEngine Integration
# - Test 5: Model Configuration
# - Benchmark: Old vs New comparison
```

### Test Outputs to Look For

✅ **Success Indicators**:
```
✅ API Connectivity: PASSED
✅ APIEmbeddingRetriever: PASSED
✅ NeuralReranker: PASSED
✅ EmojiSearchEngine Integration: PASSED
✅ Model Configuration: PASSED
✅ Benchmark: ACCEPTABLE

🎉 ALL TESTS PASSED - Plan A migration is ready for deployment!
```

❌ **Failure Indicators** (with fixes):

| Error | Cause | Fix |
|-------|-------|-----|
| "SF_API_KEY not set" | Missing credentials | `export SF_API_KEY=...` |
| "Connection refused" | API endpoint down | Check VPN, firewall, API status |
| "Embedding dimension mismatch" | Cache conflict | `rm data/dense_embeddings_qwen3_8b.npy` |
| "ImportError: APIEmbeddingRetriever" | Code not updated | `git pull` and re-run tests |

---

## 3. Integration with Flask App

### Option A: Automatic Integration (Recommended)

The Flask app automatically uses the new models:

```python
# In app.py (lines 187-188) - already configured:
engine = EmojiSearchEngine(use_neural_reranker=True)
reranker = engine._reranker
```

**Behavior**:
- Uses `NeuralReranker` by default (Qwen3-Reranker-8B)
- Uses `APIEmbeddingRetriever` for dense retrieval
- Falls back to old models if API unavailable

### Option B: Manual Control (For Testing)

```python
# To temporarily switch back to old models for comparison:
from search_engine import EmojiSearchEngine

# New (neural reranker)
engine_new = EmojiSearchEngine(use_neural_reranker=True)
results_new = engine_new.search("happy smile", method="rerank", top_k=10)

# Old (lexical reranker)  
engine_old = EmojiSearchEngine(use_neural_reranker=False)
results_old = engine_old.search("happy smile", method="dense", top_k=10)
```

---

## 4. Starting the Flask Server

```bash
# Terminal 1: Start Flask development server
python app.py
# Expected: Listening on http://127.0.0.1:5000

# Terminal 2: Test endpoints
curl -X POST http://127.0.0.1:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "happy smile", "method": "rerank", "top_k": 5}'

# Expected response:
# {
#   "results": [
#     {"char": "😊", "en": "smiling face", "score": 0.92, ...},
#     ...
#   ]
# }
```

### Monitoring First Request

⏱️ **Timing expectations**:
- First search request: **2-10 seconds** (building embedding cache)
- Subsequent requests: **0.2-0.5 seconds** (cached embeddings)

📊 **Monitor logs for**:
```
[APIEmbedding] Building embeddings using SiliconFlow API...
  Processing batch 1/30...
  Processing batch 2/30...
  ...
[APIEmbedding] Cached 3000+ embeddings to data/dense_embeddings_qwen3_8b.npy
```

---

## 5. Performance Monitoring

### Key Metrics to Track

```python
# Add to your monitoring dashboard:
import time

start = time.time()
results = engine.search("query", method="rerank", top_k=10)
latency = time.time() - start

metrics = {
    "latency_ms": latency * 1000,
    "results_count": len(results),
    "embedding_model": "Qwen3-Embedding-8B",  # NEW
    "reranker_model": "Qwen3-Reranker-8B",    # NEW
    "llm_deep_model": "Qwen3-32B-A3B",        # NEW
}
```

### Expected vs Actual Comparison

| Metric | Old | New | Target |
|--------|-----|-----|--------|
| Embedding latency | <50ms | 100-200ms | <500ms |
| Reranking latency | <10ms | 50-100ms | <500ms |
| E2E search latency | ~100ms | 200-300ms | <1000ms |
| Embedding quality | 384-dim | 768-dim | ✓ Better |
| Reranking accuracy | Lexical | Neural | ✓ Better |

---

## 6. Gradual Rollout Strategy

### Timeline: 7 Days

**Day 1-2: Internal Testing**
```bash
# 1. Run full test suite
python test_plan_a_migration.py

# 2. Manual testing on 20-30 representative queries
python -c """
from search_engine import EmojiSearchEngine
engine = EmojiSearchEngine(use_neural_reranker=True)
engine.load(['api_embed'])
queries = ['happy smile', '火焰 fire', 'cat animal', '爱心 love']
for q in queries:
    results = engine.search(q, method='rerank', top_k=5)
    print(f'{q}: {[r[\"char\"] for r in results]}')
"""

# 3. Compare with old model (A/B)
engine_old = EmojiSearchEngine(use_neural_reranker=False)
engine_old.load(['dense'])
```

**Day 3: Canary Deployment (5% traffic)**
```python
import random

def get_search_engine():
    if random.random() < 0.05:  # 5% use new model
        return EmojiSearchEngine(use_neural_reranker=True)
    else:
        return EmojiSearchEngine(use_neural_reranker=False)
```

**Day 4: Ramp Up (25% traffic)**
```python
# Change 0.05 to 0.25 above
```

**Day 5: Ramp Up (50% traffic)**
```python
# Change 0.25 to 0.50 above
```

**Day 6-7: Full Rollout (100%)**
```python
# Remove conditional logic, use new model exclusively
engine = EmojiSearchEngine(use_neural_reranker=True)
```

---

## 7. Fallback & Rollback Procedures

### Automatic Fallback (if API is down)

The system automatically falls back:

```python
# In search_engine.py _search_rerank():
embed_method = "api_embed" if "api_embed" in self.METHOD_MAP else "bi_encoder"
# Tries api_embed first, falls back to bi_encoder if unavailable
```

### Manual Rollback (if issues detected)

```bash
# Option 1: Temporary - Switch to old model
# Edit app.py line 187:
engine = EmojiSearchEngine(use_neural_reranker=False)

# Option 2: Revert old LLM models
# Edit app.py lines 35-37:
DEEP_MODEL = "Qwen/Qwen2.5-72B-Instruct"
FAST_MODEL = "Qwen/Qwen2.5-7B-Instruct"

# Option 3: Complete git revert
git revert HEAD
git push
```

---

## 8. Monitoring & Alerting

### Log Monitoring

```bash
# Watch for errors in real-time
tail -f app.log | grep -i "error\|exception\|api"

# Expected healthy logs:
# [APIEmbedding] Loaded 3000+ cached embeddings
# [NeuralReranker] Reranked 40 candidates in 0.08s
```

### Alert Conditions

Set up alerts for:
- ⚠️ API latency > 500ms
- ⚠️ API error rate > 1%
- ⚠️ Cache miss rate > 5%
- ❌ API connection failures

```python
# Add to Flask app for monitoring
@app.after_request
def log_metrics(response):
    if hasattr(request, '_latency'):
        if request._latency > 500:  # Alert if slow
            logger.warning(f"Slow search: {request._latency*1000:.0f}ms")
    return response
```

---

## 9. Troubleshooting Common Issues

### Issue 1: "API Key Not Found"

```bash
# Check if key is set
echo $SF_API_KEY

# If not set, configure:
export SF_API_KEY="sk-xxxxxxxxxxxxxxxx"

# Verify in Python:
python -c "import os; print(f'Key: {os.getenv(\"SF_API_KEY\")[:20]}...')"
```

### Issue 2: "Embedding Cache Mismatch"

```bash
# The cache uses a different filename now:
# Old: data/dense_embeddings.npy (384-dim)
# New: data/dense_embeddings_qwen3_8b.npy (768-dim)

# No action needed - system will create new cache automatically
# To force rebuild:
rm data/dense_embeddings_qwen3_8b.npy
```

### Issue 3: "API Timeout"

```bash
# Increase timeout in dense.py (line ~80):
response = requests.post(
    f"{self.api_url}/embeddings",
    json=payload,
    headers=headers,
    timeout=60  # Increase from 30 to 60 seconds
)
```

### Issue 4: "Memory Error During Embedding Build"

```bash
# Reduce batch size in dense.py (line ~96):
batch_size = 50  # Change from 100 to 50
```

---

## 10. Performance Baseline

After deployment, establish these baselines:

```python
import time
from collections import defaultdict

metrics = defaultdict(list)

test_queries = [
    "happy smile", "火焰 fire", "cat animal", "爱心 love",
    "开心 笑脸", "王冠 crown", "🎉 party", "angry face"
]

for q in test_queries:
    start = time.time()
    results = engine.search(q, method="rerank", top_k=10)
    latency = (time.time() - start) * 1000
    
    metrics["latency_ms"].append(latency)
    metrics["results_count"].append(len(results))

print(f"Average latency: {sum(metrics['latency_ms'])/len(metrics['latency_ms']):.0f}ms")
print(f"P50: {sorted(metrics['latency_ms'])[len(metrics['latency_ms'])//2]:.0f}ms")
print(f"P95: {sorted(metrics['latency_ms'])[int(len(metrics['latency_ms'])*0.95)]:.0f}ms")
print(f"P99: {sorted(metrics['latency_ms'])[int(len(metrics['latency_ms'])*0.99)]:.0f}ms")
```

---

## 11. Post-Deployment Validation

### Day 1 (Go Live)
- [ ] All tests pass
- [ ] No console errors
- [ ] API latency < 500ms
- [ ] Cache building completed
- [ ] 100 representative queries validated

### Week 1 Monitoring
- [ ] Error rate < 0.1%
- [ ] Average latency trending stable
- [ ] Embedding quality confirmed (manual spot-check)
- [ ] No customer complaints
- [ ] Cost tracking aligned ($80-150/month estimate)

### Week 2 Sign-Off
- [ ] All success criteria met
- [ ] Documentation updated
- [ ] Team trained on monitoring
- [ ] Runbooks created for common issues

---

## 12. Documentation & Support

**Key Files**:
- [MODEL_MIGRATION_PLAN_A_IMPLEMENTED.md](MODEL_MIGRATION_PLAN_A_IMPLEMENTED.md) - Technical details
- [app.py](app.py) - Model configuration (lines 35-43)
- [retrieval/dense.py](retrieval/dense.py) - API embedding (lines 113-232)
- [retrieval/reranker.py](retrieval/reranker.py) - Neural reranking (lines 108-225)

**Support Contact**:
- For API issues: SiliconFlow support
- For code issues: GitHub issue tracker
- For deployment help: DevOps team

---

## Next Steps

1. **Now**: Run `python test_plan_a_migration.py` ✓
2. **Today**: Review test results and fix any failures
3. **Tomorrow**: Begin canary deployment (5% traffic)
4. **Week 1**: Ramp to 100%, monitor closely
5. **Week 2**: Full rollout + documentation updates

**Estimated Timeline**: 1 week to full production deployment

**Risk Level**: 🟡 Medium (Mitigated by fallback logic & gradual rollout)

---

**Good luck with the migration!** 🚀

For detailed technical specifications, see [MODEL_MIGRATION_PLAN_A_IMPLEMENTED.md](MODEL_MIGRATION_PLAN_A_IMPLEMENTED.md)
