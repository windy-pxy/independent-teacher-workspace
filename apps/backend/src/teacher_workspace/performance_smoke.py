from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from dataclasses import asdict, dataclass

import httpx


@dataclass(frozen=True)
class TargetResult:
    url: str
    requests: int
    failures: int
    p50_ms: float
    p95_ms: float
    requests_per_second: float


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile without values")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


async def measure_target(
    client: httpx.AsyncClient,
    url: str,
    *,
    requests: int,
    concurrency: int,
) -> TargetResult:
    semaphore = asyncio.Semaphore(concurrency)

    async def one_request() -> tuple[float, bool]:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.get(url)
                ok = response.status_code == 200
            except httpx.HTTPError:
                ok = False
            return (time.perf_counter() - started) * 1000, ok

    for _ in range(3):
        await one_request()
    started = time.perf_counter()
    samples = await asyncio.gather(*(one_request() for _ in range(requests)))
    elapsed = time.perf_counter() - started
    durations = [duration for duration, _ in samples]
    failures = sum(1 for _, ok in samples if not ok)
    return TargetResult(
        url=url,
        requests=requests,
        failures=failures,
        p50_ms=round(percentile(durations, 0.50), 2),
        p95_ms=round(percentile(durations, 0.95), 2),
        requests_per_second=round(requests / elapsed, 2),
    )


async def run_benchmark(arguments: argparse.Namespace) -> int:
    targets = [
        f"{arguments.api_url.rstrip('/')}/health/ready",
        f"{arguments.web_url.rstrip('/')}/login",
    ]
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        results = [
            await measure_target(
                client,
                target,
                requests=arguments.requests,
                concurrency=arguments.concurrency,
            )
            for target in targets
        ]
    print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2))
    return int(
        any(
            result.failures > 0 or result.p95_ms > arguments.max_p95_ms
            for result in results
        )
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="本地生产组合性能冒烟检查")
    result.add_argument("--api-url", default="http://localhost:8000")
    result.add_argument("--web-url", default="http://localhost:3000")
    result.add_argument("--requests", type=int, default=30)
    result.add_argument("--concurrency", type=int, default=5)
    result.add_argument("--max-p95-ms", type=float, default=1000)
    return result


def main() -> None:
    arguments = parser().parse_args()
    if arguments.requests < 1 or arguments.concurrency < 1:
        raise SystemExit("requests and concurrency must be positive")
    raise SystemExit(asyncio.run(run_benchmark(arguments)))


if __name__ == "__main__":
    main()
