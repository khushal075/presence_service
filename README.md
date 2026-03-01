# Presence Service

A distributed, real-time presence engine built with **FastAPI**, **WebSockets**, and **Redis Pub/Sub**. It tracks user online/offline status across multiple server instances and fans out presence changes to all connected clients in real time.

---

## How It Works

```
Client A ──WS──▶ Server 1 ──publishes──▶ Redis Pub/Sub ──▶ Server 2 ──WS──▶ Client B
                     │                                           │
                     └──────── global_presence (Redis Hash) ────┘
```

When a user connects to **any** server node:
1. Their status is written to a shared Redis Hash (`global_presence`).
2. A `presence_update` event is published to a Redis Pub/Sub channel.
3. Every server node is subscribed to that channel and forwards the update to its own locally connected WebSocket clients.

This means Client B on Server 2 instantly learns that Client A on Server 1 just came online — without the two servers ever talking directly.

---

## Architecture

### Components

| File | Role |
|---|---|
| `main.py` | FastAPI app, lifespan startup/shutdown, WebSocket endpoint |
| `manager.py` | Core orchestrator — handles connect, disconnect, heartbeat, fan-out |
| `broadcaster.py` | Thin wrapper around Redis Pub/Sub (publish + subscribe) |
| `repository.py` | Redis Hash CRUD for persistent presence state |
| `schemas.py` | Pydantic models — `UserStatus` enum, `PresenceUpdate` |
| `config.py` | Env-based settings via `pydantic-settings` |
| `dependencies.py` | FastAPI dependency injection for `PresenceManager` |
| `utils/redis_client.py` | Async Redis connection factory |

### Data Flow

**User connects:**
```
WebSocket /ws/{user_id}
  → PresenceManager.handle_connection()
    → PresenceRepository.set_status()       # writes to Redis Hash
    → PresenceBroadcaster.publish()         # publishes to Redis channel
```

**Cross-server sync (background task):**
```
PresenceManager.start_global_listener()    # runs forever on startup
  → subscribes to "presence_update" channel
  → on message: _notify_local_subscribers()
    → asyncio.gather() fan-out to all local WebSocket connections
```

**User disconnects:**
```
WebSocketDisconnect
  → PresenceManager.handle_disconnect()
    → PresenceRepository.remove_status()
    → PresenceBroadcaster.publish(OFFLINE)
```

**Heartbeat (stale connection cleanup):**
```
Client sends: {"type": "ping"}
  → PresenceManager.refresh_heartbeat()    # sets presence:heartbeat:{user_id} key (TTL: 60s)

PresenceManager.start_cleanup_monitor()    # background task, runs every 30s
  → scans all users in Redis Hash
  → removes any user whose heartbeat key has expired
  → publishes OFFLINE event for each
```

---

## WebSocket Protocol

### Connect
```
ws://localhost:8001/ws/{user_id}
```
On connection, the server marks the user `online` and broadcasts to all nodes.

### Ping / Pong (Heartbeat)
Send every ~20 seconds to keep the session alive:
```json
// Client → Server
{ "type": "ping" }

// Server → Client
{ "type": "pong" }
```

### Presence Updates (Server → Client)
All connected clients receive these when any user's status changes:
```json
{
  "type": "presence_change",
  "user_id": "42",
  "status": "online"
}
```

### User Status Values
| Value | Meaning |
|---|---|
| `online` | Connected and active |
| `offline` | Disconnected or heartbeat expired |
| `away` | Defined in schema, not yet auto-set |
| `busy` | Defined in schema, not yet auto-set |

---

## Getting Started

### Prerequisites
- Docker & Docker Compose

### Run with Docker Compose
```bash
docker-compose up --build
```

This starts:
- `presence_redis` — Redis 7 on port `6379`
- `presence_app_1` — Service node on port `8001`
- `presence_app_2` — Service node on port `8002`

Both app nodes share the same Redis instance, enabling cross-node presence sync automatically.

### Run Locally (without Docker)

**Requirements:** Python 3.12+, Poetry, a running Redis instance

```bash
# Install dependencies
poetry install

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `APP_NAME` | `app` | Application name |
| `HEARTBEAT_INTERVAL` | `20` | How often clients should ping (seconds) |
| `PRESENCE_TTL` | `30` | Presence heartbeat TTL (seconds) |

Set these in a `.env` file or pass via Docker environment.

---

## Testing

```bash
# WebSocket integration tests
python tests/test_integraation.py

# Load test
python tests/test_unit.py
```

---

## Known Issues / TODOs

- **`refresh_heartbeat` uses `self.redis`** — `PresenceManager` doesn't have a `self.redis` attribute directly; it should use `self.repository.redis` instead. This will raise an `AttributeError` when a ping is received.
- **`start_cleanup_monitor` uses `self.redis`** — same issue; needs `self.repository.redis`.
- **Typos in `repository.py` calls** inside `manager.py` — `get_all_stauts` / `remove_stauts` (should be `get_all_status` / `remove_status`). The repository itself uses the correct spelling.
- **`docker-compose.yml` has wrong Redis port** — `REDIS_URL: redis://redis:6789` should be `6379`.
- **`/presence/all` WebSocket route** — declared as `@app.websocket` but calls `manager.get_all_presences()` which doesn't exist on `PresenceManager`. Likely should be an HTTP GET route.
- **`PresenceUpdate.user_id` is typed `int`** — but `user_id` in the WebSocket path is a `str`. This causes a Pydantic validation error on connect.
- **`_notify_local_subscribers` broadcasts to all clients** — currently fans out to every connected user on the node, not just those subscribed to a specific user's presence. Needs a subscription registry to target only interested clients.

---

## Project Structure

```
.
├── app/
│   ├── main.py           # FastAPI app + WebSocket endpoint
│   ├── manager.py        # Orchestration logic
│   ├── broadcaster.py    # Redis Pub/Sub wrapper
│   ├── repository.py     # Redis Hash operations
│   ├── schemas.py        # Pydantic models
│   ├── config.py         # Settings
│   ├── dependencies.py   # DI helpers
│   └── utils/
│       └── redis_client.py
├── tests/
│   ├── test_socket.py
│   └── load_test.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## Tech Stack

- **[FastAPI](https://fastapi.tiangolo.com/)** — async web framework
- **[Redis](https://redis.io/)** — presence state (Hash) + cross-node messaging (Pub/Sub)
- **[redis-py](https://github.com/redis/redis-py)** — async Redis client
- **[Pydantic](https://docs.pydantic.dev/)** — schema validation
- **[Poetry](https://python-poetry.org/)** — dependency management
- **[Uvicorn](https://www.uvicorn.org/)** — ASGI server