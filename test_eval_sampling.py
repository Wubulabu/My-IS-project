from eval.sampling import load_evaluation_pools, pool_size, stratified_eval_sample


def test_stratified_eval_sample_balances_multimodal_and_core_queries():
    pools = load_evaluation_pools()

    assert len(pools["core"]) == 50
    assert len(pools["multimodal"]) >= 40
    assert len(pools["expanded"]) > len(pools["core"])

    sample, breakdown = stratified_eval_sample(pools, sample_size=100, seed="unit-test")

    assert len(sample) == 100
    assert sum(breakdown.values()) == 100
    assert breakdown["multimodal"] >= 40
    assert breakdown["core"] >= 35
    assert 5 <= breakdown["expanded"] <= 20
    assert pool_size(pools) > len(sample)
