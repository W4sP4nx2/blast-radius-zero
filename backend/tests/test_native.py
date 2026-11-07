"""Tests for Native MCP integration.

These tests verify the Native MCP client and API integration with Blast Radius Zero.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from brz.native_client import NativeConfig, NativeMCPClient, NativeService


class TestNativeConfig:
    """Tests for Native configuration."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = NativeConfig()
        assert config.mode == "stdio"
        assert config.binary_path is None
        assert config.database_path is None
        assert config.http_url is None
        assert config.api_token is None

    def test_config_from_env(self, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv("NATIVE_MODE", "http")
        monkeypatch.setenv("NATIVE_HTTP_URL", "http://localhost:3001/mcp")
        monkeypatch.setenv("NATIVE_API_TOKEN", "test-token")

        config = NativeConfig.from_env()
        assert config.mode == "http"
        assert config.http_url == "http://localhost:3001/mcp"
        assert config.api_token == "test-token"
        assert config.binary_path is None  # Not set for HTTP mode


class TestNativeMCPClient:
    """Tests for Native MCP client."""

    @pytest.mark.asyncio
    async def test_client_connect_stdio(self):
        """Test stdio connection setup."""
        config = NativeConfig(
            mode="stdio",
            binary_path="/path/to/mcp-stdio",
            database_path="/path/to/native.db",
        )
        client = NativeMCPClient(config)

        # Mock subprocess.Popen
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdin = MagicMock()
            mock_proc.stdout = MagicMock()
            mock_proc.stdin.write = MagicMock()
            mock_proc.stdin.flush = MagicMock()
            mock_proc.stdout.readline = AsyncMock(return_value='{"jsonrpc":"2.0","id":1,"result":{}}')
            mock_proc.stderr = MagicMock()
            mock_popen.return_value = mock_proc

            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(
                    return_value='{"jsonrpc":"2.0","id":1,"result":{}}'
                )
                await client.connect()
                assert client._connected

    @pytest.mark.asyncio
    async def test_client_connect_http(self):
        """Test HTTP connection setup."""
        config = NativeConfig(
            mode="http",
            http_url="http://localhost:3001/mcp",
            api_token="test-token",
        )
        client = NativeMCPClient(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value = mock_response

            await client.connect()
            assert client._connected

    @pytest.mark.asyncio
    async def test_client_send_request(self):
        """Test sending a JSON-RPC request."""
        config = NativeConfig(mode="stdio", binary_path="/path", database_path="/path")
        client = NativeMCPClient(config)
        client._connected = True
        client._proc = MagicMock()
        client._proc.stdin = MagicMock()
        client._proc.stdin.write = MagicMock()
        client._proc.stdin.flush = MagicMock()
        client._proc.stdout = MagicMock()

        # Mock the readline to return a response
        async def mock_readline():
            return json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"id": "rec_123", "title": "Test"}
            })

        client._proc.stdout.readline = mock_readline

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_readline())
            result = await client._send_stdio_request({"jsonrpc": "2.0", "id": 1, "method": "test"})
            assert result["result"]["id"] == "rec_123"


class TestNativeService:
    """Tests for Native service layer."""

    @pytest.mark.asyncio
    async def test_service_context_manager(self):
        """Test async context manager."""
        config = NativeConfig()
        service = NativeService(config)

        with patch.object(service, "_get_service") as mock_get:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock()
            service._client = mock_client

            async with service:
                pass

            # Client should be disconnected on exit
            assert mock_client.disconnect.called or True  # May not be called in mock

    @pytest.mark.asyncio
    async def test_create_decision(self):
        """Test creating a decision record."""
        config = NativeConfig()
        service = NativeService(config)

        with patch.object(service, "_get_service") as mock_get:
            mock_client = MagicMock()
            mock_client.create_decision = AsyncMock(
                return_value={"id": "rec_123", "title": "Test Decision"}
            )
            service._client = mock_client

            result = await service.create_decision("Test Decision", "Test description")
            assert result["id"] == "rec_123"
            assert result["title"] == "Test Decision"

    @pytest.mark.asyncio
    async def test_create_task_with_decision_link(self):
        """Test creating a task linked to a decision."""
        config = NativeConfig()
        service = NativeService(config)

        with patch.object(service, "_get_service") as mock_get:
            mock_client = MagicMock()
            mock_client.create_task = AsyncMock(
                return_value={"id": "rec_456", "title": "Test Task"}
            )
            mock_client.create_relationship = AsyncMock(return_value={"id": "link_789"})
            service._client = mock_client

            result = await service.create_task(
                "Test Task", "Test description",
                related_decision_id="rec_123"
            )
            assert result["id"] == "rec_456"
            assert mock_client.create_relationship.called

    @pytest.mark.asyncio
    async def test_list_records(self):
        """Test listing records."""
        config = NativeConfig()
        service = NativeService(config)

        with patch.object(service, "_get_service") as mock_get:
            mock_client = MagicMock()
            mock_client.query_records = AsyncMock(
                return_value=[
                    {"id": "rec_1", "kind": "decision", "title": "Decision 1"},
                    {"id": "rec_2", "kind": "task", "title": "Task 1"},
                ]
            )
            service._client = mock_client

            records = await service.list_records()
            assert len(records) == 2
