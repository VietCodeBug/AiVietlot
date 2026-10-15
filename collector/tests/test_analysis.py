"""Synthetic test fixtures stay isolated from the live draw database."""
from dataclasses import replace
from datetime import date, timedelta

import pytest

from mega_collector import analysis


def records(count=18):
    result = []
    for index in range(count):
        values = sorted({(index * 3 + n * 5) % 45 + 1 for n in range(6)})
        result.append({"draw_id": index + 1, "draw_date": (date(2020, 1, 1) + timedelta(days=index * 3)).isoformat(),
            **{f"n{i}": n for i, n in enumerate(values, 1)}, "source_name": "synthetic-test-only",
            "source_url": "https://example.com/test-only", "fetched_at": "2020-06-01T00:00:00+00:00",
            "verification_status": "secondary"})
    return result


def config():
    return analysis.AnalysisConfig(windows=(4, 8), tickets_per_draw=3, seed_count=2,
        min_train=5, bootstrap_samples=100, block_length=3)


def test_walk_forward_uses_strictly_prior_weights(monkeypatch):
    rows = records()
    calls = []
    original = analysis.generate_tickets

    def spy(weights, count, seed, draw_id):
        calls.append((list(weights), draw_id))
        return original(weights, count, seed, draw_id)

    monkeypatch.setattr(analysis, "generate_tickets", spy)
    targets, _ = analysis.evaluate_walk_forward(rows, config())
    per_target = len(analysis.ALGORITHMS) * config().seed_count
    assert len(calls) == len(targets) * per_target
    for target_index, target in enumerate(targets):
        prior = rows[:target["draw_id"] - 1]
        for algorithm_index, algorithm in enumerate(analysis.ALGORITHMS):
            for seed_index in range(config().seed_count):
                weights, draw_id = calls[target_index * per_target + algorithm_index * config().seed_count + seed_index]
                assert draw_id == target["draw_id"]
                assert weights == pytest.approx(analysis.history_weights(prior, algorithm,
                    smoothing=config().smoothing, half_life=config().half_life))


def test_analysis_reproducible_and_baselines_comparable():
    result = analysis.run_analysis(records(), config())
    assert result == analysis.run_analysis(records(), config())
    for window in result["metrics"]["windows"]:
        for comparison in window["comparisons"]:
            expected = window["testDraws"] * config().tickets_per_draw * config().seed_count
            assert comparison["tickets"] == expected == sum(comparison["distribution"])
            assert 0 <= comparison["meanMatches"] <= 6
            assert 0 <= comparison["prizeRate"] <= 1
            assert comparison["ciLow"] <= comparison["ciHigh"]
        baseline = window["comparisons"][0]
        assert baseline["deltaMean"] == baseline["ciLow"] == baseline["ciHigh"] == 0


def test_invalid_or_gapped_history_is_rejected():
    rows = records()
    with pytest.raises(ValueError):
        analysis.run_analysis(rows[:8] + rows[9:], config())
    rows[0]["n1"] = rows[0]["n2"]
    with pytest.raises(ValueError):
        analysis.run_analysis(rows, config())


def test_distinct_seeded_tickets_and_invalid_configs():
    tickets = analysis.generate_tickets([1.0] * 45, 20, 123, 100)
    assert len(set(tickets)) == 20
    assert all(len(set(ticket)) == 6 and min(ticket) >= 1 and max(ticket) <= 45 for ticket in tickets)
    assert tickets == analysis.generate_tickets([1.0] * 45, 20, 123, 100)
    with pytest.raises(ValueError):
        replace(config(), half_life=0).validate()
    with pytest.raises(ValueError):
        replace(config(), seed_count=1).validate()
