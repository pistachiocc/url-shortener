# Redirect Performance Benchmark

This document presents the baseline performance measurements of the URL Shortener's redirect endpoint before introducing Redis caching.

The goal is to establish a reproducible baseline for evaluating future performance optimizations.

## 1. Test Environment

| Component | Configuration |
|---|---|
| Operating System | macOS |
| Backend | FastAPI + Uvicorn |
| Python | 3.11 |
| Database | PostgreSQL 17 (Docker) |
| Load Testing Tool | Grafana k6 |
| Test Duration | 30 seconds per run |
| Virtual Users | 1, 10, 50, 100 |
| Workload | Repeated GET requests to a single short code |

The benchmark was executed locally, with the load generator and application running on the same machine.

HTTP redirects were not followed, so external website latency was excluded from the measurements.

## 2. Benchmark Setup

The benchmark script is located at:

`benchmarks/redirect.js`

### Prerequisites

Install k6:

```bash
brew install k6
```

Start PostgreSQL:

```bash
docker compose up -d
```

Start the API using a single Uvicorn worker:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Create a short URL without expiration using `POST /api/v1/urls`, and save the returned short code.

### Running the Benchmark

From the repository root:

```bash
k6 run --vus 10 --duration 30s -e SHORT_CODE=<YOUR_CODE> benchmarks/redirect.js
```

Repeat with different concurrency levels:

- 1 VU
- 10 VUs
- 50 VUs
- 100 VUs

Each virtual user continuously sends requests without an artificial waiting period.

## 3. Baseline Results

**Configuration: PostgreSQL-only, single short code, 30 seconds per run.**

| VUs | Requests | RPS | P50 | P95 | P99 | Error Rate |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 12,064 | 402.12 | 2.29ms | 3.02ms | 4.04ms | 0% |
| 10 | 20,360 | 678.18 | 12.53ms | 28.18ms | 48.14ms | 0% |
| 50 | 27,458 | 913.89 | 51.14ms | 101.34ms | 141.34ms | 0% |
| 100 | 25,664 | 851.83 | 109.62ms | 182.89ms | 277.13ms | 0% |

All requests returned the expected HTTP 302 status code.

### Metrics

- **RPS:** Requests completed per second.
- **P50:** Median request latency.
- **P95:** 95th percentile request latency.
- **P99:** 99th percentile request latency.
- **Error Rate:** Percentage of failed HTTP requests.

## 4. Observations

### Throughput

Throughput increased from approximately 402 RPS at 1 VU to 914 RPS at 50 VUs.

However, increasing concurrency from 50 to 100 VUs reduced throughput by approximately 6.8%.

Among the tested concurrency levels, 50 VUs achieved the highest throughput.

### Latency

Latency increased significantly as concurrency increased.

At 50 VUs:

- P50: 51.14ms
- P95: 101.34ms
- P99: 141.34ms

At 100 VUs:

- P50: 109.62ms
- P95: 182.89ms
- P99: 277.13ms

The combination of reduced throughput and increased latency suggests possible resource saturation under higher concurrency.

### Reliability

All benchmark runs completed with a 0% HTTP error rate.

However, successful requests alone do not establish production readiness.

## 5. Limitations

These results should not be interpreted as the maximum production capacity of the system.

Several limitations apply:

- Tests were performed locally rather than in a production-like environment.
- Only one short code was repeatedly accessed, representing a hot-key workload.
- PostgreSQL may have served frequently accessed data from memory.
- The load generator and application shared the same machine's resources.
- Each configuration was measured once, so run-to-run variance has not yet been evaluated.
- Application CPU usage, database query latency, and connection pool utilization were not measured.

Therefore, the results do not establish whether PostgreSQL, FastAPI, or another component is the primary bottleneck.

## 6. Next Steps

Future benchmarks will evaluate:

1. **Redis caching:** Compare redirect performance before and after introducing a cache-aside layer.
2. **Multiple short codes:** Test workloads with different key distributions.
3. **Concurrency scaling:** Investigate throughput and latency under increasing load.
4. **Resource monitoring:** Measure CPU utilization, database performance, and connection pool behavior.
5. **Repeatability:** Run multiple iterations under identical conditions to evaluate measurement variance.

The objective is to quantify the impact of caching rather than assuming it will improve performance.

## 7. Conclusion

The PostgreSQL-only implementation achieved approximately **914 RPS at 50 VUs**, the highest throughput among the tested configurations.

Increasing concurrency to 100 VUs reduced throughput while increasing tail latency, suggesting possible saturation.

This baseline will be used to evaluate the performance impact of Redis caching in future iterations.