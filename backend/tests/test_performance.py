"""Decision latency: p95 under 500 ms over 500 payments (single client)."""

import random
from datetime import timedelta

import pytest

from portal.helpers.timing import percentile
from tests.conftest import NOON, make_account, pay


@pytest.mark.slow
def test_p95_latency_under_500ms_for_500_payments():
    rng = random.Random(3)
    accounts = [make_account(avg=rng.choice([800, 2000, 5000]), history=30) for _ in range(25)]
    latencies = []
    for i in range(500):
        acc = accounts[i % len(accounts)]
        amount = rng.choice([150, 900, 2500, 12000, 30000, 46000])
        result = pay(acc, amount, at=NOON + timedelta(minutes=i * 3), device_id=rng.choice(["DEV-T-1", "NEW-DEV"]))
        latencies.append(result["total_ms"])
    p95 = percentile(latencies, 95)
    print(f"\n500 payments: p50 {percentile(latencies, 50):.1f} ms, p95 {p95:.1f} ms, max {max(latencies):.1f} ms")
    assert p95 < 500
