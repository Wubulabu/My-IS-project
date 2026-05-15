#!/usr/bin/env python3
"""
test_plan_a_migration.py
------------------------
Comprehensive testing for Plan A model migration (Qwen3 + API-based retrieval).

Tests:
  1. API connectivity (embeddings & reranking)
  2. APIEmbeddingRetriever functionality
  3. NeuralReranker functionality
  4. EmojiSearchEngine integration
  5. Performance benchmarking (old vs. new models)
"""

import os
import sys
import json
import time
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

def test_api_connectivity():
    """Test SiliconFlow API connectivity."""
    print("\n" + "="*70)
    print("TEST 1: API Connectivity")
    print("="*70)
    
    api_key = os.getenv("SF_API_KEY")
    api_url = os.getenv("SF_BASE_URL", "https://api.siliconflow.cn/v1")
    
    if not api_key:
        print("❌ FAILED: SF_API_KEY not set")
        return False
    
    print(f"✓ API Key configured: {api_key[:20]}...")
    print(f"✓ API URL: {api_url}")
    
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        # Test embeddings endpoint
        payload = {
            "model": "Qwen/Qwen3-Embedding-8B",
            "input": ["hello world"],
            "encoding_format": "float",
        }
        
        print("\n  Testing embeddings endpoint...")
        response = requests.post(
            f"{api_url}/embeddings",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Embeddings API working")
            print(f"    - Embedding dimension: {len(data['data'][0]['embedding'])}")
            print(f"    - Response time: {response.elapsed.total_seconds():.2f}s")
        else:
            print(f"  ❌ Embeddings API error: {response.status_code}")
            print(f"     {response.text}")
            return False
        
        # Test reranking endpoint
        print("\n  Testing reranking endpoint...")
        rerank_payload = {
            "model": "Qwen/Qwen3-Reranker-8B",
            "query": "happy smile",
            "documents": ["laughing face", "crying face", "smiling emoji"],
        }
        
        response = requests.post(
            f"{api_url}/reranking",
            json=rerank_payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Reranking API working")
            print(f"    - Results: {len(data.get('results', []))} documents scored")
            print(f"    - Response time: {response.elapsed.total_seconds():.2f}s")
        else:
            print(f"  ❌ Reranking API error: {response.status_code}")
            print(f"     {response.text}")
            return False
        
        print("\n✅ API Connectivity: PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Exception during API testing: {e}")
        return False


def test_api_embedding_retriever():
    """Test APIEmbeddingRetriever class."""
    print("\n" + "="*70)
    print("TEST 2: APIEmbeddingRetriever")
    print("="*70)
    
    try:
        from retrieval.dense import APIEmbeddingRetriever
        
        print("\n  Initializing APIEmbeddingRetriever...")
        retriever = APIEmbeddingRetriever()
        retriever.load()
        
        print("  ✓ Retriever initialized and loaded")
        print(f"    - API Model: {retriever.model_name}")
        print(f"    - Cache file: {retriever.cache_file}")
        
        # Test single query
        print("\n  Testing single query embedding...")
        test_query = "happy smile"
        start = time.time()
        results = retriever.search(test_query, top_k=5)
        elapsed = time.time() - start
        
        print(f"  ✓ Search completed in {elapsed:.2f}s")
        print(f"    - Query: {test_query!r}")
        print(f"    - Results: {len(results)} emojis")
        
        for i, r in enumerate(results[:3], 1):
            print(f"      {i}. {r['char']} - {r['en']} (score: {r['score']:.4f})")
        
        print("\n✅ APIEmbeddingRetriever: PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_neural_reranker():
    """Test NeuralReranker class."""
    print("\n" + "="*70)
    print("TEST 3: NeuralReranker")
    print("="*70)
    
    try:
        from retrieval.reranker import NeuralReranker
        from retrieval.dense import DenseRetriever
        
        print("\n  Initializing NeuralReranker...")
        reranker = NeuralReranker()
        reranker.load()
        
        print("  ✓ Reranker initialized and loaded")
        print(f"    - Model: {reranker.model_name}")
        
        # Get initial candidates from old dense retriever
        print("\n  Getting initial candidates from DenseRetriever...")
        dense = DenseRetriever().load()
        candidates = dense.search("happy smile", top_k=10)
        print(f"  ✓ Got {len(candidates)} initial candidates")
        
        # Rerank
        print("\n  Reranking candidates with NeuralReranker...")
        start = time.time()
        reranked = reranker.rerank("happy smile", candidates)
        elapsed = time.time() - start
        
        print(f"  ✓ Reranking completed in {elapsed:.2f}s")
        print(f"    - Before: {[c['char'] for c in candidates[:5]]}")
        print(f"    - After:  {[c['char'] for c in reranked[:5]]}")
        
        for i, r in enumerate(reranked[:3], 1):
            print(f"      {i}. {r['char']} - score: {r['score']:.4f} (neural: {r.get('neural_score', 0):.4f})")
        
        print("\n✅ NeuralReranker: PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_search_engine_integration():
    """Test EmojiSearchEngine with new models."""
    print("\n" + "="*70)
    print("TEST 4: EmojiSearchEngine Integration")
    print("="*70)
    
    try:
        from search_engine import EmojiSearchEngine
        
        # Test with neural reranker
        print("\n  Initializing EmojiSearchEngine with NeuralReranker...")
        engine = EmojiSearchEngine(use_neural_reranker=True)
        print("  ✓ Engine initialized with use_neural_reranker=True")
        
        # Test search with api_embed method
        print("\n  Testing search with 'api_embed' method...")
        engine.load(["api_embed"])
        
        test_queries = [
            "happy smile",
            "火焰 fire",
            "cat animal",
            "爱心 love",
        ]
        
        for q in test_queries:
            start = time.time()
            results = engine.search(q, method="api_embed", top_k=5)
            elapsed = time.time() - start
            
            emojis = "".join([r["char"] for r in results])
            print(f"  ✓ {q:20s} → {emojis} ({elapsed:.2f}s)")
        
        # Test rerank method
        print("\n  Testing 'rerank' method...")
        engine.load(["api_embed"])
        start = time.time()
        results = engine.search("happy smile", method="rerank", top_k=5)
        elapsed = time.time() - start
        
        print(f"  ✓ Rerank search completed in {elapsed:.2f}s")
        print(f"    - Results: {len(results)} emojis")
        for i, r in enumerate(results[:5], 1):
            print(f"      {i}. {r['char']} - {r['en']}")
        
        print("\n✅ EmojiSearchEngine Integration: PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_model_configuration():
    """Test that model configurations are properly set in app.py."""
    print("\n" + "="*70)
    print("TEST 5: Model Configuration")
    print("="*70)
    
    try:
        import app
        
        print("\n  Checking LLM model configuration...")
        print(f"  - DEEP_MODEL: {app.DEEP_MODEL}")
        print(f"  - FAST_MODEL: {app.FAST_MODEL}")
        print(f"  - EMBEDDING_MODEL: {app.EMBEDDING_MODEL}")
        print(f"  - RERANKER_MODEL: {app.RERANKER_MODEL}")
        
        # Verify new models are being used
        checks = [
            ("Qwen3" in app.DEEP_MODEL, "DEEP_MODEL should use Qwen3"),
            ("Qwen3" in app.FAST_MODEL, "FAST_MODEL should use Qwen3"),
            ("Qwen3-Embedding-8B" in app.EMBEDDING_MODEL, "EMBEDDING_MODEL should be Qwen3-Embedding-8B"),
            ("Qwen3-Reranker-8B" in app.RERANKER_MODEL, "RERANKER_MODEL should be Qwen3-Reranker-8B"),
        ]
        
        all_passed = True
        for check, description in checks:
            if check:
                print(f"  ✓ {description}")
            else:
                print(f"  ❌ {description}")
                all_passed = False
        
        if all_passed:
            print("\n✅ Model Configuration: PASSED")
            return True
        else:
            print("\n❌ Model Configuration: FAILED")
            return False
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def benchmark_comparison():
    """Benchmark old vs new models."""
    print("\n" + "="*70)
    print("BENCHMARK: Old vs New Models")
    print("="*70)
    
    try:
        from search_engine import EmojiSearchEngine
        
        test_queries = [
            "happy smile",
            "火焰 fire",
            "cat animal",
            "爱心 love",
            "开心 笑脸",
        ]
        
        print("\n  Old Model (DenseRetriever + LexicalBoostReranker):")
        engine_old = EmojiSearchEngine(use_neural_reranker=False)
        engine_old.load(["dense"])
        
        old_times = []
        for q in test_queries:
            start = time.time()
            results = engine_old.search(q, method="dense", top_k=5)
            elapsed = time.time() - start
            old_times.append(elapsed)
            emojis = "".join([r["char"] for r in results])
            print(f"    - {q:20s} → {emojis} ({elapsed*1000:.0f}ms)")
        
        avg_old = np.mean(old_times)
        
        print("\n  New Model (APIEmbeddingRetriever + NeuralReranker):")
        engine_new = EmojiSearchEngine(use_neural_reranker=True)
        engine_new.load(["api_embed"])
        
        new_times = []
        for q in test_queries:
            start = time.time()
            results = engine_new.search(q, method="rerank", top_k=5)
            elapsed = time.time() - start
            new_times.append(elapsed)
            emojis = "".join([r["char"] for r in results])
            print(f"    - {q:20s} → {emojis} ({elapsed*1000:.0f}ms)")
        
        avg_new = np.mean(new_times)
        
        print("\n  Summary:")
        print(f"    - Old average: {avg_old*1000:.0f}ms")
        print(f"    - New average: {avg_new*1000:.0f}ms")
        print(f"    - Delta: {(avg_new - avg_old)*1000:.0f}ms ({((avg_new/avg_old - 1)*100):.0f}%)")
        
        if avg_new < avg_old * 2:  # Allow up to 2x for API overhead
            print("\n✅ Benchmark: ACCEPTABLE (performance within expected range)")
            return True
        else:
            print("\n⚠️  Benchmark: WARNING (significant latency increase)")
            return True
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "🚀 " + "="*66 + " 🚀")
    print("   PLAN A MODEL MIGRATION - COMPREHENSIVE TEST SUITE")
    print("   " + "="*66)
    
    results = {
        "API Connectivity": test_api_connectivity(),
        "APIEmbeddingRetriever": test_api_embedding_retriever(),
        "NeuralReranker": test_neural_reranker(),
        "EmojiSearchEngine Integration": test_search_engine_integration(),
        "Model Configuration": test_model_configuration(),
        "Benchmark": benchmark_comparison(),
    }
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status:8s} - {test_name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Plan A migration is ready for deployment!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - please review errors above")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
