# presence-service

[![CI](https://github.com/khushal075/presence_service/actions/workflows/ci.yml/badge.svg)](https://github.com/khushal075/presence_service/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/khushal075/presence_service/branch/main/graph/badge.svg)](https://codecov.io/gh/khushal075/presence_service)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.128-green)
![Redis](https://img.shields.io/badge/Redis-7-red)

A distributed, real-time presence engine. Tracks user online/offline status across any number of horizontally scaled server nodes and pushes changes to all connected clients instantly — via WebSockets and Redis Pub/Sub.

---


## 🎯 Problem Statement

Tracking presence at scale is non-trivial due to:

* High-frequency updates (heartbeats every ~20s)
* Cross-node synchronization
* Real-time fan-out to connected clients
* Handling stale sessions and failures

This system solves:

* **Global presence consistency across nodes**
* **Low-latency propagation of state changes**
* **Efficient cleanup of inactive users**
* **Fault-tolerant presence tracking**

---

## 🏗️ High-Level Architecture

```
Client A ──WS──▶ Server 1 ──publish──▶ Redis Pub/Sub ──▶ Server 2 ──WS──▶ Client B
                     │                                          │
                     └───────── global_presence (Redis Hash) ───┘
```
---

### Core Idea:

* Redis acts as:

  * **Source of truth (Hash)**
  * **Event bus (Pub/Sub)**
* Servers remain **stateless and horizontally scalable**
---

## ⚙️ Core Components

| Component                         | Responsibility                           |
| --------------------------------- | ---------------------------------------- |
| Presence Service                  | Connection lifecycle, heartbeat, fan-out |
| Redis Hash (`global_presence`)    | Source of truth for active users         |
| Redis Pub/Sub (`presence_update`) | Cross-node event propagation             |
| WebSockets                        | Real-time client updates                 |

---

## Architecture

### Component Map

| File | Responsibility |
|---|---|
| `app/main.py` | FastAPI app, lifespan startup/shutdown, WebSocket + health endpoints |
| `app/manager.py` | Core orchestrator — connection lifecycle, heartbeat, cross-node fan-out |
| `app/broadcaster.py` | Thin Redis Pub/Sub wrapper (publish + get pubsub handle) |
| `app/repository.py` | Redis Hash CRUD — the persistent presence store |
| `app/schemas.py` | Pydantic models: `UserStatus` enum, `PresenceUpdate` |
| `app/config.py` | Environment-based settings via `pydantic-settings` |
| `app/dependencies.py` | FastAPI dependency injection for `PresenceManager` |
| `app/utils/redis_client.py` | Async Redis connection factory |

### Data Flows

**User connects:**
```
WS /ws/{user_id}
  → PresenceManager.handle_connection()
    → PresenceRepository.set_status(user_id, ONLINE)    # write to Redis Hash
    → PresenceBroadcaster.publish(PresenceUpdate)       # fan out to all nodes
    → local_connections[user_id].add(websocket)         # track in-process
```

**Cross-node sync (background task started at boot):**
```
PresenceManager.start_global_listener()
  → subscribes to Redis "presence_update" channel
  → on message received from any node:
      → _notify_local_subscribers()
          → asyncio.gather() — concurrent fan-out to every local WebSocket
```

**User disconnects:**
```
WebSocketDisconnect
  → PresenceManager.handle_disconnect()
    → remove from local_connections
    → if last connection for user:
        → PresenceRepository.remove_status(user_id)
        → PresenceBroadcaster.publish(PresenceUpdate OFFLINE)
```

**Heartbeat & stale session cleanup:**
```
Client sends {"type": "ping"} every ~20s
  → PresenceManager.refresh_heartbeat()
      → SET presence:heartbeat:{user_id} "alive" EX 60   # touch the TTL key
      → PresenceRepository.set_status(user_id, ONLINE)   # ensure marked online

PresenceManager.start_cleanup_monitor()  [background task, runs every 30s]
  → scan all users in Redis Hash
  → for each user, check if heartbeat key exists
  → if expired/missing → remove_status() + publish(OFFLINE)
```

### Startup & Shutdown

On startup (`lifespan`), two `asyncio` background tasks are created:

| Task | Purpose |
|---|---|
| `start_global_listener` | Subscribes to Redis channel, routes updates to local WebSocket clients |
| `start_cleanup_monitor` | Polls every 30s to evict users whose heartbeat has expired |

Both tasks are canceled cleanly on shutdown, followed by closing the Redis connection.

---

## 🔌 WebSocket Protocol

### 1. Connect
```
ws://localhost:8001/ws/{user_id}
```
Connecting marks the user `online` in Redis and broadcasts the change cluster-wide.

### 2. Heartbeat — Ping / Pong
The client must send a ping every ~20 seconds. If no ping arrives within 60 seconds, the cleanup monitor will mark the user offline.

```json
// Client → Server
{ "type": "ping" }

// Server → Client
{ "type": "pong" }
```

### 3. Presence Events — Server → Client
Pushed to all connected clients whenever any user's status changes:

```json
{
  "type": "presence_change",
  "user_id": "42",
  "status": "online"
}
```

### Status Values

| Value | When set |
|---|---|
| `online` | WebSocket connected |
| `offline` | WebSocket disconnected, or heartbeat expired |
| `away` | Defined in schema — not yet auto-assigned |
| `busy` | Defined in schema — not yet auto-assigned |

---

## 🚀 Getting Started

### Run with Docker Compose (Multi-Node demo)

```bash
docker-compose up --build
```

Starts three containers:

| Container | Port | Role |
|---|---|---|
| `presence_redis` | 6379 | Shared Redis instance |
| `presence_app_1` | 8001 | Server node 1 |
| `presence_app_2` | 8002 | Server node 2 |

Both app nodes connect to the same Redis, so cross-node presence sync works out of the box.

### Run Locally

Requirements: Python 3.12+, Poetry, a running Redis instance.

```bash
# Install dependencies (includes dev/test tools)
poetry install

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Environment Variables

Set in a `.env` file or via Docker `environment:`.

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `APP_NAME` | `app` | Application name |
| `HEARTBEAT_INTERVAL` | `20` | How often clients should ping (seconds) |
| `PRESENCE_TTL` | `30` | Heartbeat TTL before a user is considered stale (seconds) |

---


## CI / CD

The GitHub Actions pipeline (`.github/workflows/ci.yml`) runs on every push and pull request to `main`, `master`, and `develop`.

```
push / PR
  └─ test job
       ├─ spin up Redis 7 service container
       ├─ setup Python 3.12 + Poetry (cached virtualenv)
       ├─ poetry install
       ├─ pytest --cov --cov-fail-under=75
       ├─ upload coverage → Codecov (badge)
       └─ upload HTML report → GitHub Actions artifact
```

**One-time setup:**
1. Sign up at [codecov.io](https://codecov.io) and link this repo.
2. Add `CODECOV_TOKEN` to **Settings → Secrets → Actions**.

---

## Project Structure

```
.
├── .github/
│   └── workflows/
│       └── ci.yml                # CI pipeline
├── app/
│   ├── main.py                   # FastAPI app + endpoints
│   ├── manager.py                # Core orchestration
│   ├── broadcaster.py            # Redis Pub/Sub wrapper
│   ├── repository.py             # Redis Hash operations
│   ├── schemas.py                # Pydantic models
│   ├── config.py                 # Settings
│   ├── dependencies.py           # DI helpers
│   └── utils/
│       └── redis_client.py       # Async Redis factory
├── tests/
│   ├── conftest.py               # Shared fixtures
│   ├── test_unit.py              # Unit tests
│   ├── test_integration.py       # Integration tests
│   ├── test_socket.py            # WebSocket tests
│   └── load_test.py              # Manual load test
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```


## 🧪 Testing

CI enforces a minimum 75% coverage threshold via GitHub Actions.

```bash
# Run all tests with coverage
poetry run pytest tests/ --ignore=tests/load_test.py --cov=app --cov-report=term-missing

# Run only unit tests
poetry run pytest tests/test_unit.py -v

# Run only integration tests
poetry run pytest tests/test_integration.py -v

# Load test (manual, requires a running server)
python tests/load_test.py
```

### Test Structure

| File | What it covers |
|---|---|
| `tests/conftest.py` | Shared fixtures: mock Redis, repository, broadcaster, manager, async HTTP client |
| `tests/test_unit.py` | `PresenceRepository`, `PresenceBroadcaster`, `PresenceManager` (connect, disconnect, fan-out, global listener, heartbeat, cleanup monitor) |
| `tests/test_integration.py` | HTTP `/health` endpoint and WebSocket connect/ping-pong |
| `tests/test_socket.py` | WebSocket end-to-end tests |
| `tests/load_test.py` | Manual load testing (excluded from CI) |

CI enforces a **minimum 75% coverage threshold**. The full HTML report is uploaded as a build artifact on every run.

---

---

## ⚠️ Known Limitations

One known design limitation remains:

- **Broadcast Fan-out:** Currently, every presence update is pushed to every connected client on a node.
- **The Fix:** A subscription registry (dict[watched_user_id, set[WebSocket]]) is needed for targeted delivery to specific "friends" or "followers."

---

## 🛠️ Tech Stack

- **[FastAPI](https://fastapi.tiangolo.com/)** — async web framework
- **[Redis](https://redis.io/)** — presence state (Hash) + cross-node event bus (Pub/Sub)
- **[redis-py](https://github.com/redis/redis-py)** — async Redis client
- **[Pydantic](https://docs.pydantic.dev/)** — schema validation and settings management
- **[Uvicorn](https://www.uvicorn.org/)** — ASGI server
- **[Poetry](https://python-poetry.org/)** — dependency management
- **[pytest](https://pytest.org/)** + **[pytest-asyncio](https://pytest-asyncio.readthedocs.io/)** — async test framework
- **[Codecov](https://codecov.io/)** — coverage reporting