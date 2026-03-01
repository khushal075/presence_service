"""
Unit tests for PresenceRepository, PresenceBroadcaster, and PresenceManager.
All external I/O is mocked — no real Redis required.
"""
import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.schemas import UserStatus, PresenceUpdate
from app.repository import PresenceRepository
from app.broadcaster import PresenceBroadcaster
from app.manager import PresenceManager


# ─────────────────────────────────────────────────────────────────────────────
# PresenceRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestPresenceRepository:

    @pytest.mark.asyncio
    async def test_set_status_writes_to_hash(self, repository, mock_redis):
        await repository.set_status("user_1", UserStatus.ONLINE)
        mock_redis.hset.assert_called_once_with("global_presence", "user_1", "online")

    @pytest.mark.asyncio
    async def test_remove_status_deletes_from_hash(self, repository, mock_redis):
        await repository.set_status("user_1", UserStatus.ONLINE)
        await repository.remove_status("user_1")
        mock_redis.hdel.assert_called_once_with("global_presence", "user_1")

    @pytest.mark.asyncio
    async def test_get_status_returns_value(self, repository):
        await repository.set_status("user_1", UserStatus.ONLINE)
        result = await repository.get_status("user_1")
        assert result == "online"

    @pytest.mark.asyncio
    async def test_get_status_missing_user_returns_none(self, repository):
        result = await repository.get_status("ghost")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_status_returns_all(self, repository):
        await repository.set_status("user_1", UserStatus.ONLINE)
        await repository.set_status("user_2", UserStatus.OFFLINE)
        result = await repository.get_all_status()
        assert result == {"user_1": "online", "user_2": "offline"}

    @pytest.mark.asyncio
    async def test_get_all_status_empty(self, repository):
        result = await repository.get_all_status()
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# PresenceBroadcaster
# ─────────────────────────────────────────────────────────────────────────────

class TestPresenceBroadcaster:

    @pytest.mark.asyncio
    async def test_publish_serializes_update(self, broadcaster, mock_redis):
        update = PresenceUpdate(user_id=1, status=UserStatus.ONLINE)
        await broadcaster.publish(update)

        mock_redis.publish.assert_called_once()
        channel, payload = mock_redis.publish.call_args[0]

        assert channel == "presence_update"
        data = json.loads(payload)
        assert data["user_id"] == 1
        assert data["status"] == "online"

    def test_get_pubsub_returns_pubsub_object(self, broadcaster, mock_redis):
        mock_redis.pubsub.return_value = MagicMock()
        pubsub = broadcaster.get_pubsub()
        mock_redis.pubsub.assert_called_once()
        assert pubsub is not None

    def test_channel_name(self, broadcaster):
        assert broadcaster.CHANNEL == "presence_update"


# ─────────────────────────────────────────────────────────────────────────────
# PresenceManager — connect / disconnect
# ─────────────────────────────────────────────────────────────────────────────

class TestPresenceManagerConnectDisconnect:

    def _make_websocket(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws.accept = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_handle_connection_sets_online(self, manager):
        ws = self._make_websocket()
        await manager.handle_connection("42", ws)

        status = await manager.repository.get_status("42")
        assert status == "online"

    @pytest.mark.asyncio
    async def test_handle_connection_accepts_websocket(self, manager):
        ws = self._make_websocket()
        await manager.handle_connection("42", ws)
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_connection_adds_to_local_connections(self, manager):
        ws = self._make_websocket()
        await manager.handle_connection("42", ws)
        assert "42" in manager.local_connections
        assert ws in manager.local_connections["42"]

    @pytest.mark.asyncio
    async def test_multiple_connections_same_user(self, manager):
        ws1, ws2 = self._make_websocket(), self._make_websocket()
        await manager.handle_connection("42", ws1)
        await manager.handle_connection("42", ws2)
        assert len(manager.local_connections["42"]) == 2

    @pytest.mark.asyncio
    async def test_handle_disconnect_removes_websocket(self, manager):
        ws = self._make_websocket()
        await manager.handle_connection("42", ws)
        await manager.handle_disconnect("42", ws)
        assert "42" not in manager.local_connections

    @pytest.mark.asyncio
    async def test_handle_disconnect_sets_offline(self, manager):
        ws = self._make_websocket()
        await manager.handle_connection("42", ws)
        await manager.handle_disconnect("42", ws)
        status = await manager.repository.get_status("42")
        assert status is None

    @pytest.mark.asyncio
    async def test_partial_disconnect_keeps_user_online(self, manager):
        """Disconnecting one of two tabs should keep user online."""
        ws1, ws2 = self._make_websocket(), self._make_websocket()
        await manager.handle_connection("42", ws1)
        await manager.handle_connection("42", ws2)
        await manager.handle_disconnect("42", ws1)

        assert "42" in manager.local_connections
        assert ws2 in manager.local_connections["42"]
        status = await manager.repository.get_status("42")
        assert status == "online"

    @pytest.mark.asyncio
    async def test_disconnect_unknown_user_is_safe(self, manager):
        ws = self._make_websocket()
        # Should not raise even if user was never connected
        await manager.handle_disconnect("ghost", ws)


# ─────────────────────────────────────────────────────────────────────────────
# PresenceManager — fan-out
# ─────────────────────────────────────────────────────────────────────────────

class TestPresenceManagerFanOut:

    def _make_websocket(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws.accept = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_notify_sends_to_all_local_connections(self, manager):
        ws1, ws2 = self._make_websocket(), self._make_websocket()
        await manager.handle_connection("1", ws1)
        await manager.handle_connection("2", ws2)

        await manager._notify_local_subscribers("99", "online")

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

        payload = json.loads(ws1.send_text.call_args[0][0])
        assert payload["user_id"] == "99"
        assert payload["status"] == "online"
        assert payload["type"] == "presence_change"

    @pytest.mark.asyncio
    async def test_notify_no_connections_is_safe(self, manager):
        # Should not raise when there are no connections
        await manager._notify_local_subscribers("99", "online")

    @pytest.mark.asyncio
    async def test_notify_failed_send_does_not_abort_others(self, manager):
        ws1, ws2 = self._make_websocket(), self._make_websocket()
        ws1.send_text.side_effect = Exception("dead socket")

        await manager.handle_connection("1", ws1)
        await manager.handle_connection("2", ws2)

        # Should not raise; ws2 should still receive the message
        await manager._notify_local_subscribers("99", "online")
        ws2.send_text.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# PresenceManager — global listener
# ─────────────────────────────────────────────────────────────────────────────

class TestPresenceManagerGlobalListener:

    def _make_websocket(self):
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        ws.accept = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_global_listener_routes_message_to_local_subscribers(self, manager):
        """A presence_update message from Redis should fan out to local connections."""
        import json
        import asyncio

        ws = self._make_websocket()
        await manager.handle_connection("99", ws)

        # Build a fake pubsub that yields one message then stops
        async def fake_listen():
            yield {"type": "message", "data": json.dumps({"user_id": "5", "status": "online"})}

        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        pubsub.unsubscribe = AsyncMock()
        pubsub.listen = fake_listen
        manager.broadcaster.get_pubsub = MagicMock(return_value=pubsub)

        await manager.start_global_listener()

        ws.send_text.assert_called_once()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["user_id"] == "5"
        assert payload["status"] == "online"
        assert payload["type"] == "presence_change"

    @pytest.mark.asyncio
    async def test_global_listener_skips_non_message_types(self, manager):
        """subscribe/psubscribe confirmation messages should be ignored."""
        import asyncio

        async def fake_listen():
            yield {"type": "subscribe", "data": 1}

        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        pubsub.unsubscribe = AsyncMock()
        pubsub.listen = fake_listen
        manager.broadcaster.get_pubsub = MagicMock(return_value=pubsub)

        # Should complete without error and without sending anything
        await manager.start_global_listener()

    @pytest.mark.asyncio
    async def test_global_listener_handles_exception_gracefully(self, manager):
        """An error mid-stream should not crash the process."""
        async def fake_listen():
            yield {"type": "message", "data": "not valid json {{{}"}

        pubsub = AsyncMock()
        pubsub.subscribe = AsyncMock()
        pubsub.unsubscribe = AsyncMock()
        pubsub.listen = fake_listen
        manager.broadcaster.get_pubsub = MagicMock(return_value=pubsub)

        # Should not raise
        await manager.start_global_listener()


# ─────────────────────────────────────────────────────────────────────────────
# PresenceManager — heartbeat & cleanup
# ─────────────────────────────────────────────────────────────────────────────

class TestPresenceManagerHeartbeat:

    @pytest.mark.asyncio
    async def test_refresh_heartbeat_sets_ttl_key(self, manager, mock_redis):
        """refresh_heartbeat should write a presence:heartbeat:{user_id} key with TTL."""
        # Fix the known bug: patch self.redis onto the manager
        manager.redis = mock_redis
        await manager.refresh_heartbeat("42")
        mock_redis.set.assert_called_once_with("presence:heartbeat:42", "alive", ex=60)

    @pytest.mark.asyncio
    async def test_refresh_heartbeat_ensures_user_online(self, manager, mock_redis):
        manager.redis = mock_redis
        await manager.refresh_heartbeat("42")
        status = await manager.repository.get_status("42")
        assert status == "online"

    @pytest.mark.asyncio
    async def test_cleanup_monitor_removes_expired_users(self, manager, mock_redis):
        """Users with no heartbeat key should be marked offline."""
        import asyncio

        # Pre-populate two users in the hash
        await manager.repository.set_status("alive_user", UserStatus.ONLINE)
        await manager.repository.set_status("dead_user", UserStatus.ONLINE)

        # alive_user has a heartbeat key, dead_user does not
        async def fake_exists(key):
            return 1 if "alive_user" in key else 0

        mock_redis.exists.side_effect = fake_exists
        manager.redis = mock_redis

        # Patch asyncio.sleep to run only one iteration then cancel
        call_count = 0

        async def fake_sleep(_):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch("app.manager.asyncio.sleep", fake_sleep):
            try:
                await manager.start_cleanup_monitor()
            except asyncio.CancelledError:
                pass

        # dead_user should have been removed
        dead_status = await manager.repository.get_status("dead_user")
        assert dead_status is None

        # alive_user should still be present
        alive_status = await manager.repository.get_status("alive_user")
        assert alive_status == "online"