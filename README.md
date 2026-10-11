# URL Shortener

A URL shortening service built with FastAPI and PostgreSQL.

The project explores backend engineering concepts including RESTful API design, database persistence, transaction management, and scalability.

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

### Planned

- Redis caching
- URL expiration
- Rate limiting
- Database migrations with Alembic
- GitHub Actions CI
- Containerized API deployment
- Load testing and performance analysis

## Tech Stack

- Language: Python
- Web Framework: FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy
- Database Driver: Psycopg
- Testing: pytest, FastAPI TestClient
- Development Environment: Docker Compose

## Architecture

Current architecture:

```text
Client
   |
   v
FastAPI
   |
   v
SQLAlchemy
   |
   v
PostgreSQL
```

FastAPI runs locally, while PostgreSQL runs in a Docker container.

## Getting Started

### Prerequisites

- Python 3.9+
- Docker with Docker Compose

### Installation

1. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Configure the database connection.

```bash
cp .env.example .env
```

4. Start PostgreSQL.

```bash
docker compose up -d
```

5. Start the API server.

```bash
fastapi dev app/main.py
```

The API is available at http://localhost:8000.

Interactive API documentation: http://localhost:8000/docs

The application automatically creates the database tables if they do not exist.

## API Endpoints

### Create Short URL

```http
POST /api/v1/urls
```

Request:

```json
{"long_url": "https://example.com/articles/12345"}
```

Example response (201 Created):

```json
{"code": "aB3xY9qK", "short_url": "http://localhost:8000/aB3xY9qK"}
```

### Redirect to Original URL

```http
GET /{code}
```

- 302 Found: Redirects to the original URL
- 404 Not Found: The short code does not exist

## Database Design

The `urls` table contains:

| Column       | Type         | Constraints      |
| ------------ | ------------ | ---------------- |
| id           | BIGINT       | Primary Key      |
| short_code   | VARCHAR(8)   | Unique, Not Null |
| original_url | TEXT         | Not Null         |
| created_at   | TIMESTAMPTZ  | Not Null         |

A unique B-tree index on `short_code` supports efficient lookups and prevents duplicate short codes.

## Testing

Create a separate test database:

```bash
docker compose exec db psql -U shortener -d postgres -c "CREATE DATABASE shortener_test;"
```

Install dependencies：

```bash
pip install -r requirements-dev.txt
````

Run the test suite:

```bash
python -m pytest -v
```

Current tests cover:

- Successful short URL creation
- HTTP 302 redirection
- HTTP 404 for unknown short codes
- Database uniqueness constraint

### Test Isolation

Each test runs within an outer database transaction.

SQLAlchemy sessions use savepoints so that application-level commits do not commit the outer test transaction.

After each test, the outer transaction is rolled back to prevent test data from affecting subsequent tests.

## Design Decisions

### Why PostgreSQL?

PostgreSQL provides ACID transactions, unique constraints, and indexed lookups for reliable URL mapping storage.

### Why Separate `id` and `short_code`?

A BIGINT primary key provides a stable internal identifier for potential future relationships, while `short_code` serves as the public identifier.

### Why Random Base62 Codes?

Random Base62 codes are compact and do not directly expose sequential database IDs. Uniqueness is enforced by PostgreSQL, with retries on conflicts.

## Current Limitations

- No caching layer
- No authentication or user management
- No URL expiration
- No distributed deployment
- No production deployment configuration

## Development Roadmap

- [x] ~~Basic URL shortening~~
- [x] ~~PostgreSQL persistence~~
- [x] ~~Integration tests~~
- [x] ~~Transaction-based test isolation~~
- [ ] GitHub Actions CI
- [ ] Alembic migrations
- [ ] Redis caching
- [ ] Rate limiting
- [ ] Load testing
