# Redirect Performance Benchmarks

This report compares redirect performance before and after introducing Redis caching to the URL Shortener. The goal is to establish a measurable PostgreSQL-only baseline and evaluate the impact of a warm Redis cache under the same nominal load-testing workload.

## 1. Test Environment

| Component | Configuration |
|---|---|
| Operating System | macOS (local development machine) |
| Backend | FastAPI + Uvicorn (1 worker) |
| Python | 3.11 |
| Database | PostgreSQL 17 (Docker) |
| Cache | Redis (Docker; Redis-backed tests only) |
| Load Testing Tool | Grafana k6 |
| Test Duration | 30 seconds per run |
| Virtual Users | 1, 10, 50, 100 |
| Workload | Repeated `GET /{code}` requests to one non-expiring short code |
| Redirect Handling | HTTP 302 responses; redirects not followed |

The load generator and application ran on the same local machine. This is a **single-hot-key, closed-loop** benchmark: each virtual user continuously sends the next request when its previous request completes, without an artificial sleep interval.

## 2. Benchmark Setup

The shared load-testing script is [`redirect.js`](redirect.js).

Install k6 (macOS):

```bash
brew install k6
```

Start the Docker services and API server:

```bash
docker compose up -d
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Create a non-expiring short URL using `POST /api/v1/urls` (omit `expires_in_seconds`) and save the returned code. For Redis-backed tests, issue one successful `GET /{code}` first and verify the Redis cache has been populated. This measures the **warm-cache-hit** path.

Run the benchmark from the repository root, changing `--vus` for each configuration:

```bash
k6 run --vus 10 --duration 30s -e SHORT_CODE=<YOUR_CODE> benchmarks/redirect.js
```

The PostgreSQL-only measurements were collected before Redis caching was implemented. Running the current application with a warm Redis cache measures the Redis-backed path, **not** the PostgreSQL-only baseline.

## 3. PostgreSQL-only Baseline

The initial baseline was measured once per concurrency level with the database-backed redirect endpoint.

| VUs | Requests | RPS | P50 | P95 | P99 | Error Rate |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 12,064 | 402.12 | 2.29ms | 3.02ms | 4.04ms | 0% |
| 10 | 20,360 | 678.18 | 12.53ms | 28.18ms | 48.14ms | 0% |
| 50 | 27,458 | 913.89 | 51.14ms | 101.34ms | 141.34ms | 0% |
| 100 | 25,664 | 851.83 | 109.62ms | 182.89ms | 277.13ms | 0% |

All requests returned the expected HTTP 302 status code. Throughput increased up to 50 VUs among the tested configurations, then decreased at 100 VUs while latency rose, suggesting possible resource saturation.

**Metrics:** RPS is completed requests per second; P50, P95, and P99 are the 50th, 95th, and 99th percentiles of HTTP request duration; error rate is the share of failed HTTP requests.

## 4. Redis Warm-cache Results

After introducing cache-aside Redis lookups, each concurrency level was tested **three times**. The table reports the **median of the three runs for each metric** (not the metrics of a single representative run).

| VUs | RPS (Median) | P50 | P95 | P99 | Error Rate |
|---:|---:|---:|---:|---:|---:|
| 1 | 640.35 | 1.34ms | 2.25ms | 4.90ms | 0% |
| 10 | 1,762.97 | 5.03ms | 8.02ms | 22.94ms | 0% |
| 50 | 2,009.37 | 22.55ms | 43.35ms | 69.30ms | 0% |
| 100 | 2,005.92 | 45.50ms | 75.77ms | 98.84ms | 0% |

All recorded Redis benchmark runs returned HTTP 302 with a 0% HTTP error rate.

## 5. Before / After Comparison

| VUs | PostgreSQL-only RPS | Redis RPS (Median) | Observed Speedup | PostgreSQL P95 | Redis P95 (Median) |
|---:|---:|---:|---:|---:|---:|
| 1 | 402.12 | 640.35 | 1.59x | 3.02ms | 2.25ms |
| 10 | 678.18 | 1,762.97 | 2.60x | 28.18ms | 8.02ms |
| 50 | 913.89 | 2,009.37 | 2.20x | 101.34ms | 43.35ms |
| 100 | 851.83 | 2,005.92 | 2.35x | 182.89ms | 75.77ms |

At **50 VUs**, the Redis-backed implementation showed approximately **2.20x the throughput** of the PostgreSQL-only baseline, and **57.2% lower P95 latency** (101.34ms down to 43.35ms). All runs in both configurations had a 0% HTTP error rate.

At 100 VUs, Redis throughput was similar to the 50-VU median while latency increased, suggesting additional performance constraints remain under higher concurrency. The current measurements do not identify the underlying bottleneck.

## 6. Limitations

These observations are **not** estimates of maximum production capacity:

- Both workloads were tested locally, with k6 and the application sharing the same machine's resources.
- A single short code was repeatedly requested, favoring warm caches and not representing real-world URL popularity distributions.
- The PostgreSQL baseline has only one run per VU setting; Redis measurements have three. The comparison is therefore indicative, not a controlled statistical estimate.
- The Redis test primarily measures cache hits; cache-miss performance and mixed hit rates were not evaluated.
- PostgreSQL may have cached frequently accessed data in memory during the baseline.
- CPU utilization, database query time, connection pool behavior, and Redis resource usage were not instrumented.
- Redis measurements varied across runs, particularly at 10 VUs.

## 7. Future Work

- Repeat PostgreSQL-only measurements under the same controlled conditions as Redis measurements.
- Benchmark many short codes with realistic access distributions and varying cache hit rates.
- Investigate CPU utilization, thread pool saturation, database connection pool usage, and Redis latency.
- Explore other concurrency levels and workload models to locate saturation points.

## 8. Conclusion

Introducing Redis caching correlated with substantial throughput and tail-latency improvements under this local, warm-cache, single-hot-key workload. At 50 VUs, the measured Redis median reached **2,009.37 RPS**, versus **913.89 RPS** for the single-run PostgreSQL baseline.

Further profiling and more representative load tests are needed before generalizing these results to production traffic.
