# URL Shortener

A URL shortening service built with FastAPI, PostgreSQL, and Redis.

This project explores RESTful API design, database persistence, caching strategies, fault tolerance, automated testing, and performance optimization.

## Features

### Implemented

- Generate random 8-character Base62 short codes
- Create short URLs through a REST API
- Redirect short URLs to their original destinations (HTTP 302)
- Validate input URLs
- Persist URL mappings in PostgreSQL
- Enforce short-code uniqueness with database constraints
- Retry short-code generation on uniqueness conflicts
- Integration tests with transaction-based isolation
- Database schema versioning with Alembic
- Automated testing with GitHub Actions CI
- URL expiration
- Redis caching using the cache-aside pattern
- Automatic fallback to PostgreSQL when Redis is unavailable
- Cache TTL aligned with URL expiration
- Redis cache tests using FakeRedis
- Load testing and performance analysis using Grafana k6
- Redis-based rate limiting for URL creation
- Per-IP request limits using a fixed-window counter
- HTTP 429 responses with Retry-After headers
- Fail-open behavior when Redis is unavailable
- Containerized FastAPI application using Docker
- Multi-service orchestration with Docker Compose
- Health checks for FastAPI, PostgreSQL, and Redis
- Database migrations executed within the API container

### Planned


## Tech Stack

- Language: Python 3.11
- Web Framework: FastAPI
- Database: PostgreSQL 17
- ORM: SQLAlchemy 2
- Database Driver: Psycopg 3
- Database Migrations: Alembic
- Cache: Redis
- Redis Client: redis-py
- Cache Testing: fakeredis
- Load Testing: Grafana k6
- Testing: pytest, FastAPI TestClient
- CI: GitHub Actions
- Containerization: Docker, Docker Compose
- Application Server: Uvicorn

## Architecture

```text
                         Client
                           |
                           v
                        FastAPI
                           |
                           v
                       Redis GET
                      /         \
                 Cache hit    Cache miss / failure
                     |                 |
                     |                 v
                     |             SQLAlchemy
                     |                 |
                     |                 v
                     |             PostgreSQL
                     |                 |
                     |         Optional cache fill
                     |                 |
                     +--------+--------+
                              |
                              v
                      HTTP 302 Redirect
```

The application is containerized using Docker Compose, with three services running on a shared Docker network:

- **api**: FastAPI application served by Uvicorn
- **db**: PostgreSQL for persistent URL storage
- **cache**: Redis for URL caching and rate limiting

Services communicate through Docker Compose service names. The API connects to PostgreSQL at `db:5432` and Redis at `cache:6379`.

Docker health checks monitor all three services. The API starts after PostgreSQL and Redis pass their health checks.

Database schema migrations are managed using Alembic and executed explicitly from the API container.

The application uses Redis as a cache layer for URL redirects. On a cache hit, the original URL is returned without querying PostgreSQL. On a cache miss or Redis failure, the application falls back to PostgreSQL.

PostgreSQL remains the source of truth. Cached URLs use a maximum TTL of one hour, capped by the URL's remaining lifetime.

## Getting Started

### Prerequisites

- Docker with Docker Compose

### Running with Docker Compose

1. Clone the repository.

```bash
git clone https://github.com/pistachiocc/url-shortener.git
cd url-shortener
```

2. Build the API image.

```bash
docker compose build api
```

3. Start PostgreSQL and Redis.

```bash
docker compose up -d db cache
```

4. Apply database migrations.

```bash
docker compose run --rm api alembic upgrade head
```

5. Start the FastAPI service.

```bash
docker compose up -d api
```

6. Verify service health.

```bash
docker compose ps
curl http://localhost:8000/health
```

All three services should report healthy status.

The API is available at http://localhost:8000.

Interactive API documentation is available at
http://localhost:8000/docs.

### Subsequent Starts

After the initial setup, start the services with:

```bash
docker compose up --build -d
```

Database migrations are not executed automatically.
Run `docker compose run --rm api alembic upgrade head`
whenever schema migrations need to be applied.

### Stopping the Application

```bash
docker compose down
```

The PostgreSQL data volume is preserved.

### Local Development (Optional)

The API can also run directly on the host machine
while PostgreSQL and Redis run in Docker.

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Copy the local environment configuration:

```bash
cp .env.example .env
```

Start the dependencies without the API container:

```bash
docker compose stop api
docker compose up -d db cache
```

Apply migrations and start the API:

```bash
alembic upgrade head
fastapi dev app/main.py
```

When running locally, the API connects to PostgreSQL
via `localhost:5433` and Redis via `localhost:6379`.

## API Endpoints

### Health Check

```bash
GET \health
```

Returns HTTP 200 when the FastAPI application is responding.

Example response:

```json
{
    "status": "ok"
}
```

This endpoint serves as a liveness check. It does not verify the availability of PostgreSQL or Redis.


### Create Short URL

```http
POST /api/v1/urls
```

Request:

```json
{
    "long_url": "https://example.com/articles/12345",
    "expires_in_seconds": 3600
}
```

The expires_in_seconds parameter is optional.

- If omitted, the short URL never expires.
- Valid values range from 1 to 31,536,000 seconds (365 days).
- Invalid values return HTTP 422.

Example response (201 Created):

```json
{
   "code": "aB3xY9qK",
   "short_url": "http://localhost:8000/aB3xY9qK",
   "expires_at": "2026-10-21T13:38:21.933586+00:00"
}
```

The `expires_at` field is an absolute expiration timestamp in UTC, or null for URLs without expiration.

If a unique short code cannot be generated within 5 attempts, the API returns HTTP 503 Service Unavailable with `{"detail": "Could not generate unique short code"}`.

### Rate Limiting

The URL creation endpoint (`POST /api/v1/urls`) is rate-limited using Redis.

- **Limit**: 10 requests per IP address per 60-second fixed window
- **Exceeded Limit**: Returns HTTP 429 Too Many Requests
- **Retry-After**: Indicates the number of seconds until the next window
- **Failure Handling**: Allows requests when Redis is unavailable (fail-open)

The redirect endpoint (`GET /{code}`) is not rate-limited.

### Redirect to Original URL

```http
GET /{code}
```

- 302 Found: Redirects to the original URL.
- 404 Not Found: The short code does not exist.
- 410 Gone: URL has expired.

## Database Design

The `urls` table contains:

| Column       | Type         | Constraints      |
| ------------ | ------------ | ---------------- |
| id           | BIGINT       | Primary Key      |
| short_code   | VARCHAR(8)   | Unique, Not Null |
| original_url | TEXT         | Not Null         |
| created_at   | TIMESTAMPTZ  | Not Null         |
| expires_at   | TIMESTAMPTZ  | Nullable         |

A unique B-tree index on `short_code` supports efficient lookups and prevents duplicate short codes.

An index on `expires_at` supports efficient expiration-based queries for future cleanup jobs.

### Database Migrations

Database schema changes are managed with Alembic.

Migration history:

- Initial migration: Create the `urls` table.
- URL expiration migration: Add the nullable `expires_at` column.
- Expiration index migration: Add an index on `expires_at`.

Existing URL records remain valid after the migration,

with `expires_at` set to NULL.

Apply all pending migrations using Docker Compose:

```bash
docker compose run --rm api alembic upgrade head
```

For local development, migrations can also be applied
using the DATABASE_URL configured in `.env`:

```bash
alembic upgrade head
```

Check the current database revision:

```bash
alembic current
```

Generate a migration after modifying SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe schema change"
```

Autogenerated migrations should be reviewed before applying them.

## Testing

Integration tests run against a separate PostgreSQL database to avoid modifying development data.

1. Start PostgreSQL.

```bash
docker compose up -d db
```

2. Create the test database (first time only).

```bash
docker compose exec db psql -U shortener -d postgres -c "CREATE DATABASE shortener_test;"
```

3. Apply database migrations to the test database.

```bash
DATABASE_URL="postgresql+psycopg://shortener:dev_password@localhost:5433/shortener_test" alembic upgrade head
```

4. Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

5. Run the test suite:

```bash
python -m pytest -v
```

Current tests cover:

- Successful short URL creation (201)
- HTTP 302 redirection
- HTTP 404 for unknown short codes
- Database uniqueness constraint
- Redirecting URLs before expiration
- HTTP 410 for expired URLs
- Invalid expiration values (422)
- Backward compatibility for URLs without expiration
- Redis cache hits without additional database queries
- PostgreSQL fallback when Redis is unavailable
- Expiration validation for cached URLs
- Cache TTL bounded by URL expiration
- Health endpoint availability (HTTP 200)

### Test Isolation

Each test runs within an outer database transaction.

SQLAlchemy sessions use savepoints so that application-level commits do not commit the outer test transaction.

Redis cache tests use FakeRedis instances to isolate test state without depending on a running Redis server.

After each test, the outer transaction is rolled back, preventing test data from affecting subsequent tests.

### Continuous Integration

GitHub Actions automatically executes the test suite on pushes and pull requests.

The CI workflow:

1. Starts a PostgreSQL service container.

2. Sets up Python 3.11 and installs dependencies.

3. Applies Alembic migrations to the test database.

4. Runs the integration tests with pytest.

This verifies that the application and database schema can be initialized and tested in a clean environment. Redis caching behavior is tested with FakeRedis; a real Redis server is not required for these tests.

## Performance Benchmarks

Redirect performance was evaluated using Grafana k6, comparing PostgreSQL-only lookups with Redis-backed redirects.

Under a local, single-worker, single-hot-key workload at 50 concurrent virtual users:

| Metric | PostgreSQL-only | Redis Cached |

|---|---:|---:|
| Throughput | 913.89 RPS | 2,009.37 RPS |
| P95 Latency | 101.34ms | 43.35ms |
| P99 Latency | 141.34ms | 69.30ms |
| HTTP Error Rate | 0% | 0% |

Redis caching achieved approximately **2.20x higher throughput** and **57.2% lower P95 latency** under these test conditions.

Redis results represent the median of three runs, while the PostgreSQL-only baseline consists of a single run per concurrency level. These are local benchmark observations rather than production capacity estimates.

See [Detailed Benchmark Results](benchmarks/README.md) for methodology, measurements, and limitations.

## Design Decisions

### Why PostgreSQL?

PostgreSQL provides ACID transactions, unique constraints, and indexed lookups for reliable URL mapping storage.

### Why Separate `id` and `short_code`?

A BIGINT primary key provides a stable internal identifier for potential future relationships, while `short_code` serves as the public identifier.

### Why Random Base62 Codes?

Random Base62 codes are compact and do not directly expose sequential database IDs. Uniqueness is enforced by PostgreSQL, with retries on conflicts.

### Why Alembic?

Alembic provides version-controlled database schema migrations, allowing the schema to evolve without manually recreating database tables.

It also enables new environments to initialize their database schema consistently.

### Why Transaction-Based Test Isolation?

Database transactions and savepoints allow tests to execute real database operations while rolling back their changes afterward.

This improves test repeatability and reduces the risk of test data interfering with other tests.

### Why Store an Absolute Expiration Timestamp?

The API accepts a relative TTL (`expires_in_seconds`),

while PostgreSQL stores an absolute UTC timestamp (`expires_at`).

This allows expiration to be checked directly at request time

without recalculating the TTL from the creation timestamp.

Expired URLs return HTTP 410 without being immediately

deleted from the database.

### Why Redis?

URL shortening services typically have read-heavy workloads, where redirects occur more frequently than new URL creation.

Redis reduces repeated PostgreSQL lookups by caching frequently accessed URL mappings in memory.

The application uses the cache-aside pattern, keeping PostgreSQL as the source of truth. If Redis is unavailable, redirect requests fall back to PostgreSQL.

Cache entries have a maximum TTL of one hour, limited by the remaining lifetime of the URL to prevent serving expired redirects.

### Why Redis-Based Rate Limiting?

Redis provides shared, in-memory counters suitable for enforcing request limits across multiple application instances.

The initial implementation uses a fixed-window counter because it is simple, efficient, and requires minimal storage.

Redis transactions ensure that counter increments and TTL initialization execute atomically.

The rate limiter follows a fail-open policy to preserve API availability when Redis is unavailable.

**Trade-offs**:

- Fixed windows can allow bursts around window boundaries.
- Fail-open behavior temporarily disables rate limiting during Redis outages.
- Client IP identification requires trusted proxy configuration in production environments.

Sliding-window or token-bucket algorithms may be considered in future iterations.

### Why Docker Compose?

Docker Compose provides a reproducible local environment for the API, PostgreSQL, and Redis.

Each service runs in an isolated container and communicates through an internal Docker network, avoiding dependencies on host-specific service configurations.

Health checks help coordinate service startup, while explicit Alembic migration commands keep database schema changes separate from application startup.

This setup simplifies local development and integration testing, but it is not intended to represent a production deployment architecture.

## Current Limitations

- No authentication or user management
- No automatic cleanup of expired URLs
- The returned `short_url` uses a hardcoded base URL (`http://localhost:8000`)
- No distributed deployment
- No production deployment configuration

## Development Roadmap

- [x] Basic URL shortening
- [x] PostgreSQL persistence
- [x] Integration tests
- [x] Transaction-based test isolation
- [x] GitHub Actions CI
- [x] Alembic database migrations
- [x] URL expiration
- [x] Redis caching
- [x] Load testing
- [x] Rate limiting
- [x] Dockerized FastAPI application
- [x] Docker Compose service orchestration
- [x] Health checks for API, PostgreSQL, and Redis
- [ ] Production deployment
