# URL Shortener

A lightweight URL shortening service built with Python and FastAPI.

The project explores backend engineering concepts such as URL encoding, persistent storage, caching, API design, and horizontal scalability.

## Features

### Implemented

- Generate short URLs from long URLs
- Redirect short URLs to their original destinations (HTTP 302)
- Generate random 8-character Base62 short codes
- Validate input URLs

### Planned

- PostgreSQL for persistent storage
- Redis caching
- URL expiration
- Rate limiting
- Automated tests and CI
- Containerized deployment
- Load testing and performance analysis

## Tech Stack

- Python
- FastAPI
- Uvicorn

PostgreSQL, Redis, and Docker will be introduced in later development stages.

## Getting Started

1. Clone the repository and enter the project directory.

2. Create a virtual environment and install dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "fastapi[standard]"
```

3. Start the development server.

```bash
fastapi dev app/main.py
```

The API is available at http://localhost:8000.

Interactive API documentation: http://localhost:8000/docs

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
{"code": "aB3xY9q", "short_url": "http://localhost:8000/aB3xY9q"}
```

### Redirect to Original URL

```http
GET /{code}
```

Returns HTTP 302 with a Location header pointing to the original URL.

Returns HTTP 404 if the short code does not exist.

## Current Limitations

This initial version uses an in-memory Python dictionary for URL storage.

- Data is lost when the server restarts.
- URL mappings are not shared across multiple server processes.
- Short-code uniqueness is only guaranteed within the current in-memory store.

These limitations will be addressed in future iterations.

## Architecture

Current implementation:

```text
Client → FastAPI → In-memory Storage
```

Future iterations will introduce PostgreSQL and Redis.

## Development Roadmap

- Basic URL shortening API
- HTTP redirection
- PostgreSQL integration
- Redis caching
- Rate limiting
- Automated testing
- Docker deployment
- Performance benchmarking

## Design Decisions

Detailed discussions of short-code generation, caching, database design, and scalability will be added as the project evolves.

Use a BIGINT surrogate primary key to provide a stable internal identifier and simplify future relationships, while enforcing uniqueness on the externally exposed short code.
 