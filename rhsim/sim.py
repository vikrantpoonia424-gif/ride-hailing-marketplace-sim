"""Minute-by-minute Monte Carlo simulation of a ride-hailing marketplace.

One city zone, one day. Riders request trips (Poisson arrivals that follow
an hourly demand curve), the platform dispatches the nearest idle driver,
riders cancel if the pickup ETA is too long, and drivers log in or out
depending on how much they expect to earn under the platform's policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Requests per hour for a ~10 x 10 km zone (morning and evening peaks).
DEMAND_PROFILE = np.array([
    40, 25, 15, 10, 10, 30, 90, 220, 320, 300, 200, 170,
    180, 170, 160, 170, 220, 300, 340, 310, 240, 170, 110, 70,
])
# Drivers who would be online at the reference policy (20% commission, no incentive).
SUPPLY_PROFILE = np.array([
    22, 15, 10, 8, 8, 18, 45, 95, 120, 110, 80, 72,
    72, 72, 70, 72, 90, 120, 128, 118, 90, 66, 45, 30,
])
PEAK_HOURS = np.array([h in (8, 9, 10, 17, 18, 19, 20) for h in range(24)])


@dataclass(frozen=True)
class Policy:
    commission: float = 0.20            # platform take rate on fare
    incentive_per_hour: float = 0.0     # Rs per online driver-hour, peak hours only


@dataclass(frozen=True)
class City:
    size_km: float = 10.0
    speed_kmph: float = 20.0
    detour: float = 1.3                 # road distance / straight-line distance
    base_fare: float = 40.0
    per_km: float = 12.0
    free_wait_min: float = 4.0          # riders accept any ETA up to this
    patience_min: float = 6.0           # beyond it, accept with prob exp(-extra/patience)
    max_dispatch_min: float = 15.0      # beyond this ETA the platform shows "no cabs"
    ops_cost_per_trip: float = 6.0      # payments, support, insurance per trip
    ref_driver_hourly: float = 200.0    # gross fare/hour a driver expects
    supply_elasticity: float = 0.8
    demand: np.ndarray = field(default_factory=lambda: DEMAND_PROFILE)
    supply: np.ndarray = field(default_factory=lambda: SUPPLY_PROFILE)
    peak: np.ndarray = field(default_factory=lambda: PEAK_HOURS)


def supply_multiplier(policy: Policy, city: City) -> np.ndarray:
    """Hourly multiplier on drivers online: drivers log in more when their
    expected take-home per hour rises (incentive is paid in peak hours only)."""
    ref = (1 - 0.20) * city.ref_driver_hourly
    take_home = ((1 - policy.commission) * city.ref_driver_hourly
                 + policy.incentive_per_hour * city.peak)
    return (take_home / ref) ** city.supply_elasticity


def simulate(policy: Policy, city: City = City(), seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    n_online = np.round(city.supply * supply_multiplier(policy, city)).astype(int)
    pool = int(n_online.max())
    pos = rng.uniform(0, city.size_km, size=(pool, 2))
    busy_until = np.zeros(pool)
    km_per_min = city.speed_kmph / 60

    requests = completed = no_driver = cancelled = 0
    eta_sum = fare_sum = busy_min = online_min = peak_online_min = 0.0

    for t in range(24 * 60):
        h = t // 60
        online = np.arange(pool) < n_online[h]
        online_min += online.sum()
        if city.peak[h]:
            peak_online_min += online.sum()
        busy_min += np.count_nonzero(online & (busy_until > t))

        for _ in range(rng.poisson(city.demand[h] / 60)):
            requests += 1
            idle = np.flatnonzero(online & (busy_until <= t))
            if idle.size == 0:
                no_driver += 1
                continue
            origin = rng.uniform(0, city.size_km, 2)
            dist = np.hypot(*(pos[idle] - origin).T) * city.detour
            j = int(np.argmin(dist))
            eta = dist[j] / km_per_min
            if eta > city.max_dispatch_min:
                no_driver += 1
                continue
            if rng.random() > np.exp(-max(0.0, eta - city.free_wait_min) / city.patience_min):
                cancelled += 1
                continue
            dest = rng.uniform(0, city.size_km, 2)
            trip_km = np.hypot(*(dest - origin)) * city.detour + 0.5
            d = idle[j]
            busy_until[d] = t + eta + trip_km / km_per_min
            pos[d] = dest
            completed += 1
            eta_sum += eta
            fare_sum += city.base_fare + city.per_km * trip_km

    online_hours = online_min / 60
    incentive_cost = policy.incentive_per_hour * peak_online_min / 60
    driver_pay = (1 - policy.commission) * fare_sum + incentive_cost
    contribution = (policy.commission * fare_sum - incentive_cost
                    - city.ops_cost_per_trip * completed)
    return {
        "requests": requests,
        "completed": completed,
        "completion_rate": completed / requests,
        "no_driver_rate": no_driver / requests,
        "cancel_rate": cancelled / requests,
        "avg_eta_min": eta_sum / max(completed, 1),
        "utilisation": busy_min / online_min,
        "driver_hourly": driver_pay / online_hours,
        "gmv": fare_sum,
        "contribution": contribution,
        "contribution_per_trip": contribution / max(completed, 1),
        "online_hours": online_hours,
    }


def monte_carlo(policy: Policy, city: City = City(), runs: int = 10) -> dict:
    """Mean and 95% half-width of each metric across `runs` random days."""
    res = [simulate(policy, city, seed=s) for s in range(runs)]
    out = {"commission": policy.commission, "incentive": policy.incentive_per_hour}
    for k in res[0]:
        vals = np.array([r[k] for r in res])
        out[k] = vals.mean()
        out[k + "_ci"] = 1.96 * vals.std(ddof=1) / np.sqrt(runs) if runs > 1 else 0.0
    return out
