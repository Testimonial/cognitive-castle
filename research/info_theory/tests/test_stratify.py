from pipeline.stratify import allocate_subsample


def test_proportional_allocation_when_no_floor_hit():
    strata = {"a": 800, "b": 200}  # 80/20 split, both > floor
    alloc = allocate_subsample(strata, n_total=100, floor=10)
    assert alloc["a"] + alloc["b"] == 100
    assert alloc["a"] == 80 and alloc["b"] == 20


def test_floor_raises_small_strata():
    strata = {"big": 950, "small": 50}  # proportional: 95/5
    alloc = allocate_subsample(strata, n_total=100, floor=20)
    assert alloc["small"] == 20  # raised from 5 to floor
    assert alloc["big"] == 80  # stolen 15 from big


def test_termination_when_total_floor_exceeds_n_total():
    # 10 strata × floor 20 = 200 minimum, but n_total=100
    strata = {f"s{i}": 50 for i in range(10)}
    alloc = allocate_subsample(strata, n_total=100, floor=20)
    # Floor must reduce so total fits
    total = sum(alloc.values())
    assert total <= 100
    # All strata get something
    assert all(v > 0 for v in alloc.values())


def test_deterministic_with_seed():
    strata = {"a": 400, "b": 300, "c": 300}
    a1 = allocate_subsample(strata, n_total=100, floor=20, seed=42)
    a2 = allocate_subsample(strata, n_total=100, floor=20, seed=42)
    assert a1 == a2


def test_seed_affects_distribution_only_via_rounding_tiebreaks():
    strata = {"a": 333, "b": 333, "c": 333}
    a1 = allocate_subsample(strata, n_total=100, floor=20, seed=1)
    a2 = allocate_subsample(strata, n_total=100, floor=20, seed=2)
    # Totals always match
    assert sum(a1.values()) == sum(a2.values()) == 100


def test_single_stratum_edge_case():
    # Single stratum: floor doesn't apply (only one bucket), gets everything
    strata = {"only": 500}
    alloc = allocate_subsample(strata, n_total=100, floor=20)
    assert alloc == {"only": 100}
