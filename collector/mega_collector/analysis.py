"""Reproducible prior-only historical comparisons; never a prediction claim.

Random ticket generation and bootstrap run on the collector/CI, not in a browser.
Only standard-library arithmetic is required, avoiding a separate numeric stack.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import math
import random
from typing import Any
import uuid
from zoneinfo import ZoneInfo

from .models import utc_now, validate_draw


ALGORITHM_VERSION = "mega-walk-forward-v1"
ALGORITHMS = ("uniform", "frequency", "recency")
LABELS = {"uniform": "Ngẫu nhiên đều", "frequency": "Tần suất lịch sử", "recency": "Tần suất gần đây"}


@dataclass(frozen=True)
class AnalysisConfig:
    windows: tuple[int, ...] = (100, 300)
    tickets_per_draw: int = 5
    seed_count: int = 10
    seed: int = 20261015
    min_train: int = 100
    smoothing: float = 1.0
    half_life: float = 50.0
    bootstrap_samples: int = 1000
    block_length: int = 10

    def validate(self) -> None:
        integer_limits = {"tickets_per_draw": (1, 100), "seed_count": (2, 100),
            "min_train": (1, 10000), "bootstrap_samples": (100, 10000), "block_length": (1, 1000)}
        for name, (low, high) in integer_limits.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in {low}..{high}")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        if not self.windows or any(type(window) is not int or not 1 <= window <= 5000 for window in self.windows):
            raise ValueError("windows must contain integers in 1..5000")
        for name in ("smoothing", "half_life"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")


def _random_seed(seed: int, draw_id: int, namespace: str = "tickets") -> int:
    # Do not use Python hash(), which varies across processes.
    value = f"{ALGORITHM_VERSION}:{namespace}:{seed}:{draw_id}".encode("ascii")
    return int.from_bytes(hashlib.sha256(value).digest()[:16], "big")


def sample_ticket(weights: list[float], rng: random.Random) -> tuple[int, ...]:
    """Sequential probability-proportional sampling without replacement."""
    if len(weights) != 45 or any(not math.isfinite(w) or w <= 0 for w in weights):
        raise ValueError("Exactly 45 finite positive weights are required")
    available = list(range(1, 46))
    remaining = list(weights)
    ticket = []
    for _ in range(6):
        total = math.fsum(remaining)
        threshold = rng.random() * total
        cumulative = 0.0
        selected = len(remaining) - 1
        for index, weight in enumerate(remaining):
            cumulative += weight
            if threshold < cumulative:
                selected = index
                break
        ticket.append(available.pop(selected))
        remaining.pop(selected)
    return tuple(sorted(ticket))


def generate_tickets(weights: list[float], count: int, seed: int, draw_id: int) -> list[tuple[int, ...]]:
    rng = random.Random(_random_seed(seed, draw_id))
    tickets: list[tuple[int, ...]] = []
    observed = set()
    for _ in range(count * 1000):
        ticket = sample_ticket(weights, rng)
        if ticket not in observed:
            tickets.append(ticket)
            observed.add(ticket)
            if len(tickets) == count:
                return tickets
    raise ValueError("Unable to generate the requested number of distinct tickets")


def history_weights(prior_records: list[dict], algorithm: str, *, smoothing: float = 1,
                    half_life: float = 50) -> list[float]:
    """Reference prior-only weights, also used to test the streaming state."""
    if algorithm not in ALGORITHMS or smoothing <= 0 or half_life <= 0:
        raise ValueError("Invalid algorithm or weight configuration")
    if algorithm == "uniform":
        return [1.0] * 45
    weights = [float(smoothing)] * 45
    for age, record in enumerate(reversed(prior_records)):
        contribution = 1.0 if algorithm == "frequency" else 2 ** (-age / half_life)
        for index in range(1, 7):
            weights[record[f"n{index}"] - 1] += contribution
    return weights


def _validated_records(records: list[dict]) -> list[dict]:
    today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    ordered = sorted(records, key=lambda row: row["draw_id"])
    previous = None
    for row in ordered:
        validate_draw(row, today=today)
        if previous is not None and (row["draw_id"] != previous["draw_id"] + 1
                                     or row["draw_date"] <= previous["draw_date"]):
            raise ValueError("Analysis requires contiguous draw ids and increasing dates")
        previous = row
    if ordered and ordered[0]["draw_id"] != 1:
        raise ValueError("Analysis history must start at draw 1")
    return ordered


def evaluate_walk_forward(records: list[dict], config: AnalysisConfig) -> tuple[list[dict], dict[str, list[list[list[int]]]]]:
    """Return target rows and [algorithm][seed][draw][ticket] match counts.

    State is scored BEFORE the target's six numbers are added. A fixed ticket
    stream per seed/draw is shared across algorithms for paired comparisons.
    """
    config.validate()
    ordered = _validated_records(records)
    if len(ordered) <= config.min_train:
        raise ValueError("Not enough completed draws after the minimum training period")
    start = max(config.min_train, len(ordered) - max(config.windows))
    target_rows = ordered[start:]
    results = {algorithm: [[] for _ in range(config.seed_count)] for algorithm in ALGORITHMS}
    frequency = [0.0] * 45
    recency = [0.0] * 45
    decay = 2 ** (-1 / config.half_life)
    for position, record in enumerate(ordered):
        if position >= start:
            weights = {"uniform": [1.0] * 45,
                "frequency": [config.smoothing + value for value in frequency],
                "recency": [config.smoothing + value for value in recency]}
            actual = {record[f"n{i}"] for i in range(1, 7)}
            for algorithm in ALGORITHMS:
                for seed_index in range(config.seed_count):
                    tickets = generate_tickets(weights[algorithm], config.tickets_per_draw,
                        config.seed + seed_index, record["draw_id"])
                    results[algorithm][seed_index].append([len(actual.intersection(ticket)) for ticket in tickets])
        # Updating after scoring is the boundary which prevents target leakage.
        recency = [value * decay for value in recency]
        for index in range(1, 7):
            number = record[f"n{index}"] - 1
            frequency[number] += 1
            recency[number] += 1
    return target_rows, results


def paired_bootstrap(differences: list[list[float]], *, samples: int, seed: int,
                     block_length: int) -> tuple[float, float]:
    """95% paired hierarchical circular-block interval over seeds and draws."""
    seed_count = len(differences)
    draw_count = len(differences[0])
    rng = random.Random(seed)
    estimates = []
    block = min(block_length, draw_count)
    for _ in range(samples):
        selected_seeds = [rng.randrange(seed_count) for _ in range(seed_count)]
        draw_means = [sum(differences[s][d] for s in selected_seeds) / seed_count for d in range(draw_count)]
        selected_draws = []
        while len(selected_draws) < draw_count:
            first = rng.randrange(draw_count)
            selected_draws.extend((first + offset) % draw_count for offset in range(block))
        estimates.append(sum(draw_means[d] for d in selected_draws[:draw_count]) / draw_count)
    estimates.sort()
    return estimates[int(0.025 * (samples - 1))], estimates[int(0.975 * (samples - 1))]


def _statistics(scores: list[list[list[int]]]) -> tuple[list[int], float, float]:
    distribution = [0] * 7
    for seed_scores in scores:
        for draw_scores in seed_scores:
            for count in draw_scores:
                distribution[count] += 1
    total = sum(distribution)
    return distribution, sum(k * value for k, value in enumerate(distribution)) / total, sum(distribution[3:]) / total


def _comparison(algorithm: str, scores: list[list[list[int]]], baseline: list[list[list[int]]],
                config: AnalysisConfig) -> dict:
    distribution, mean, prize = _statistics(scores)
    _, baseline_mean, _ = _statistics(baseline)
    differences = [[(sum(draw_scores) - sum(base_scores)) / config.tickets_per_draw
        for draw_scores, base_scores in zip(seed_scores, baseline_scores)]
        for seed_scores, baseline_scores in zip(scores, baseline)]
    interval = (0.0, 0.0) if algorithm == "uniform" else paired_bootstrap(differences,
        samples=config.bootstrap_samples, seed=_random_seed(config.seed, len(scores[0]), "bootstrap:" + algorithm),
        block_length=config.block_length)
    per_seed = []
    for seed_index, (seed_scores, baseline_scores) in enumerate(zip(scores, baseline)):
        _, seed_mean, seed_prize = _statistics([seed_scores])
        _, seed_baseline, _ = _statistics([baseline_scores])
        per_seed.append({"seed": config.seed + seed_index, "meanMatches": seed_mean,
            "prizeRate": seed_prize, "baselineMean": seed_baseline, "deltaMean": seed_mean - seed_baseline})
    return {"algorithm": algorithm, "label": LABELS[algorithm], "tickets": sum(distribution),
        "ticketsPerDraw": config.tickets_per_draw, "seedCount": config.seed_count,
        "testDraws": len(scores[0]), "meanMatches": mean, "prizeRate": prize,
        "distribution": distribution, "baselineMean": baseline_mean, "deltaMean": mean - baseline_mean,
        "ciLow": interval[0], "ciHigh": interval[1], "perSeed": per_seed}


def run_analysis(records: list[dict], config: AnalysisConfig | None = None) -> dict[str, Any]:
    config = config or AnalysisConfig()
    targets, all_scores = evaluate_walk_forward(records, config)
    windows = []
    for size in sorted({min(requested, len(targets)) for requested in config.windows}):
        target_range = targets[-size:]
        scores = {algorithm: [seed_scores[-size:] for seed_scores in all_scores[algorithm]] for algorithm in ALGORITHMS}
        windows.append({"testDraws": size,
            "range": {"first_draw_id": target_range[0]["draw_id"], "last_draw_id": target_range[-1]["draw_id"],
                "first_date": target_range[0]["draw_date"], "last_date": target_range[-1]["draw_date"]},
            "comparisons": [_comparison(algorithm, scores[algorithm], scores["uniform"], config) for algorithm in ALGORITHMS]})
    largest = windows[-1]
    denominator = math.comb(45, 6)
    probabilities = [math.comb(6, k) * math.comb(39, 6-k) / denominator for k in range(7)]
    configuration = asdict(config)
    configuration.update({"windows": list(config.windows), "effective_windows": [window["testDraws"] for window in windows],
        "seed_values": [config.seed + index for index in range(config.seed_count)],
        "training_rule": "all completed draws strictly before target; update only after scoring",
        "sampling": "sequential weighted without replacement; distinct tickets within seed/draw",
        "recency_unit": "draws", "bootstrap": "paired hierarchical circular blocks over draws and seeds", "confidence": 0.95})
    metrics = {"comparisons": largest["comparisons"], "range": largest["range"],
        "windows": windows, "seed": config.seed,
        "theoretical": {"meanMatches": 0.8, "prizeRate": sum(probabilities[3:]), "distribution": probabilities},
        "notes": [
            "Walk-forward: mỗi kỳ chỉ dùng dữ liệu trước kỳ đó; không dùng kết quả kỳ mục tiêu để tạo vé.",
            f"Mỗi phương pháp dùng cùng {config.tickets_per_draw} vé/kỳ và {config.seed_count} seed; tickets là tổng vé mô phỏng qua mọi seed.",
            "prizeRate là tỷ lệ vé mô phỏng trùng ít nhất 3 số, không phải lợi nhuận hay dự báo trúng thưởng.",
            "CI 95% của chênh lệch số trùng so với ngẫu nhiên đều dùng bootstrap ghép cặp theo seed và khối kỳ quay; chưa hiệu chỉnh nhiều phép so sánh.",
            "Kết quả lịch sử và khác biệt ngẫu nhiên không chứng minh khả năng dự đoán kỳ tiếp theo; các kỳ xổ số được xét độc lập.",
            "Dữ liệu giữ nguyên trạng thái xác minh của nguồn; dữ liệu secondary chưa được xác nhận trực tiếp bằng nguồn Vietlott.",
        ]}
    return {"algorithm_version": ALGORITHM_VERSION, "config": configuration,
        "first_draw_id": largest["range"]["first_draw_id"], "last_draw_id": largest["range"]["last_draw_id"],
        "metrics": metrics, "status": "succeeded"}


def publish_analysis(repository, result: dict) -> dict:
    """Publish one complete immutable report using a retry-stable client UUID."""
    record = {"id": str(uuid.uuid4()), "created_at": utc_now(), **result}
    repository._request("POST", "analysis_runs", params={"on_conflict": "id"},
        body=record, prefer="resolution=ignore-duplicates,return=minimal")
    return record
