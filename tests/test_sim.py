import numpy as np

from rhsim import City, Policy, monte_carlo, simulate, supply_multiplier


def test_reference_policy_has_unit_supply():
    assert np.allclose(supply_multiplier(Policy(0.20, 0), City()), 1.0)


def test_incentive_only_raises_peak_supply():
    m = supply_multiplier(Policy(0.20, 40), City())
    assert (m[City().peak] > 1).all() and np.allclose(m[~City().peak], 1.0)


def test_simulation_is_reproducible_and_consistent():
    a, b = simulate(Policy(), seed=3), simulate(Policy(), seed=3)
    assert a == b
    assert 0 < a["completion_rate"] <= 1
    assert abs(a["completion_rate"] + a["no_driver_rate"] + a["cancel_rate"] - 1) < 1e-9


def test_more_drivers_means_shorter_eta():
    lean = monte_carlo(Policy(0.30, 0), runs=3)
    rich = monte_carlo(Policy(0.10, 40), runs=3)
    assert rich["avg_eta_min"] < lean["avg_eta_min"]
