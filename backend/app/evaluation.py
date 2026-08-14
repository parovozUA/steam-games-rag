import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path

import httpx
import yaml
from anyio import Path as AsyncPath


def ranking_metrics(expected: list[int], actual: list[int]) -> tuple[float, float, float]:
    relevant = set(expected)
    top = actual[:10]
    recall = len(relevant.intersection(top)) / len(relevant) if relevant else 1.0
    reciprocal_rank = next(
        (1 / rank for rank, app_id in enumerate(top, 1) if app_id in relevant), 0
    )
    dcg = sum(
        (1 if app_id in relevant else 0) / math.log2(rank + 1) for rank, app_id in enumerate(top, 1)
    )
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(relevant), 10) + 1))
    return recall, reciprocal_rank, dcg / ideal if ideal else 1.0


def field_f1(expected: dict, actual: dict) -> float:
    expected_pairs = {(key, json.dumps(value, sort_keys=True)) for key, value in expected.items()}
    actual_pairs = {
        (key, json.dumps(value, sort_keys=True))
        for key, value in actual.items()
        if value not in (None, [], {})
    }
    if not expected_pairs and not actual_pairs:
        return 1.0
    matches = len(expected_pairs & actual_pairs)
    precision = matches / len(actual_pairs) if actual_pairs else 0
    recall = matches / len(expected_pairs) if expected_pairs else 0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1)]


async def evaluate(dataset: Path, api_url: str, output: Path) -> dict:
    dataset_content = await AsyncPath(dataset).read_text(encoding="utf-8")
    cases = yaml.safe_load(dataset_content)["cases"]
    recalls, mrrs, ndcgs, filter_scores, latencies = [], [], [], [], []
    details = []
    async with httpx.AsyncClient(timeout=20) as client:
        for case in cases:
            started = time.monotonic()
            body = None
            lines = []
            async with client.stream("POST", f"{api_url.rstrip('/')}/api/v1/search", json={"query": case["query"], "debug": True}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    lines.append(line)
                    if line.startswith("data:") and '"results"' in line:
                        data_str = line.split(":", 1)[1].strip()
                        body = json.loads(data_str)
                        break
            if not body:
                print("Stream output:", lines)
                raise ValueError(f"No results found in stream for case {case['id']}")
            latency = (time.monotonic() - started) * 1000
            recall, mrr, ndcg = ranking_metrics(
                case["relevant_app_ids"], [item["app_id"] for item in body["results"]]
            )
            filter_score = field_f1(case.get("filters", {}), body["debug"]["filters"])
            recalls.append(recall)
            mrrs.append(mrr)
            ndcgs.append(ndcg)
            filter_scores.append(filter_score)
            latencies.append(latency)
            details.append(
                {
                    "id": case["id"],
                    "recall_at_10": recall,
                    "mrr_at_10": mrr,
                    "ndcg_at_10": ndcg,
                    "filter_f1": filter_score,
                    "latency_ms": latency,
                }
            )
    report = {
        "summary": {
            "cases": len(cases),
            "recall_at_10": statistics.fmean(recalls),
            "mrr_at_10": statistics.fmean(mrrs),
            "ndcg_at_10": statistics.fmean(ndcgs),
            "filter_field_f1": statistics.fmean(filter_scores),
            "latency_p50_ms": percentile(latencies, 0.5),
            "latency_p95_ms": percentile(latencies, 0.95),
        },
        "cases": details,
    }
    await AsyncPath(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("eval/dataset.yaml"))
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("eval-report.json"))
    args = parser.parse_args()
    asyncio.run(evaluate(args.dataset, args.api_url, args.output))


if __name__ == "__main__":
    main()
