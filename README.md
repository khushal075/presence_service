# Distributed Presence Service

A high-performance, real-time presence service built with **FastAPI**, **WebSockets**, and **Redis**. This service tracks user online/offline status across multiple server nodes using Redis Pub/Sub.

## 🚀 Features
* **Real-time Tracking:** WebSocket-based heartbeat system.
* **Distributed Architecture:** Horizontal scaling support via Redis.
* **Global Sync:** Automatic status synchronization across all cluster nodes.
* **Automatic Cleanup:** TTL-based session management in Redis.

## 🛠️ Tech Stack
* **Language:** Python 3.14+
* **Framework:** FastAPI
* **Messaging:** Redis (Pub/Sub & Key-Value Store)
* **Concurrency:** Asyncio / ASGI

## 🚦 Getting Started

### 1. Prerequisites
* Python 3.12+ (or 3.14 for experimental features)
* Docker (for Redis)
* `websocat` (for testing)

### 2. Setup
```bash
# Clone the repository
git clone <your-repo-url>
cd presence_service

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install fastapi uvicorn redis pydantic pydantic-settings    