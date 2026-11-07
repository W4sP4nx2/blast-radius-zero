"""Native MCP client wrapper for blast-radius-zero integration.

This module provides a Python client that communicates with a Native MCP server
over stdio using JSON-RPC protocol. It supports both local and remote MCP server
configurations while maintaining blast-radius-zero's containment-first security model.
"""
import asyncio
import json
import logging
import subprocess
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NativeConfig:
    """Configuration for connecting to a Native MCP server."""
    mode: str = "stdio"  # "stdio" or "http"
    binary_path: Optional[str] = None
    database_path: Optional[str] = None
    http_url: Optional[str] = None
    api_token: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "NativeConfig":
        """Create configuration from environment variables."""
        import os
        mode = os.getenv("NATIVE_MODE", "stdio")
        binary_path = os.getenv("NATIVE_BINARY_PATH")
        database_path = os.getenv("NATIVE_DATABASE_PATH")
        http_url = os.getenv("NATIVE_HTTP_URL")
        api_token = os.getenv("NATIVE_API_TOKEN")
        
        return cls(
            mode=mode,
            binary_path=binary_path,
            database_path=database_path,
            http_url=http_url,
            api_token=api_token,
        )


class NativeMCPClient:
    """Python client for Native MCP server communication.
    
    Implements JSON-RPC over stdio transport for Native engine integration.
    Follows blast-radius-zero's security model with proper isolation.
    """
    
    def __init__(self, config: NativeConfig):
        self.config = config
        self._proc: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._connected = False
        self._lock = asyncio.Lock()
        
    async def connect(self) -> None:
        """Establish connection to the Native MCP server."""
        async with self._lock:
            if self._connected:
                return
                
            if self.config.mode == "stdio":
                await self._connect_stdio()
            elif self.config.mode == "http":
                await self._connect_http()
            else:
                raise ValueError(f"Unsupported mode: {self.config.mode}")
            
            self._connected = True
            
    async def _connect_stdio(self) -> None:
        """Connect to Native MCP server via stdio."""
        if not self.config.binary_path:
            raise ValueError("NATIVE_BINARY_PATH required for stdio mode")
        if not self.config.database_path:
            raise ValueError("NATIVE_DATABASE_PATH required for stdio mode")
            
        # Start the MCP server as a subprocess
        self._proc = subprocess.Popen(
            [self.config.binary_path, self.config.database_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        
        # Initialize the server
        await self._send_request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {
                "name": "blast-radius-zero",
                "version": "0.1.0",
            },
        })
        
    async def _connect_http(self) -> None:
        """Connect to Native MCP server via HTTP."""
        import httpx
        
        self._http_client = httpx.AsyncClient(
            base_url=self.config.http_url,
            headers={"Authorization": f"Bearer {self.config.api_token}"} if self.config.api_token else {},
            timeout=30.0,
        )
        
    async def disconnect(self) -> None:
        """Close connection to the Native MCP server."""
        async with self._lock:
            if self._proc:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self._proc = None
                
            if hasattr(self, "_http_client"):
                await self._http_client.aclose()
                
            self._connected = False
            
    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request to the Native MCP server."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        
        if self.config.mode == "stdio":
            return await self._send_stdio_request(request)
        else:
            return await self._send_http_request(request)
            
    async def _send_stdio_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send request over stdio."""
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("Not connected to Native MCP server")
            
        # Send request as JSON-RPC line
        line = json.dumps(request) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()
        
        # Read response
        if self._proc.stdout:
            response_line = await asyncio.get_event_loop().run_in_executor(
                None, self._proc.stdout.readline
            )
            if response_line:
                return json.loads(response_line)
                
        raise RuntimeError("Failed to receive response from Native MCP server")
        
    async def _send_http_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send request over HTTP."""
        response = await self._http_client.post(
            "/mcp",
            json=request,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()
        
    async def engine_info(self) -> Dict[str, Any]:
        """Get information about the Native engine."""
        return await self._send_request("tools/call", {
            "name": "engine_info",
            "arguments": {},
        })
        
    async def create_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new record in the Native database."""
        return await self._send_request("tools/call", {
            "name": "record_create",
            "arguments": {"record": record},
        })
        
    async def read_record(self, record_id: str) -> Dict[str, Any]:
        """Read a record by its ID."""
        return await self._send_request("tools/call", {
            "name": "record_read",
            "arguments": {"id": record_id},
        })
        
    async def update_record(self, record_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing record."""
        return await self._send_request("tools/call", {
            "name": "record_update",
            "arguments": {"id": record_id, "record": record},
        })
        
    async def delete_record(self, record_id: str) -> Dict[str, Any]:
        """Delete a record."""
        return await self._send_request("tools/call", {
            "name": "record_delete",
            "arguments": {"id": record_id},
        })
        
    async def query_records(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query records with the provided query parameters."""
        return await self._send_request("tools/call", {
            "name": "record_query",
            "arguments": {"query": query},
        })
        
    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        relationship_type: str,
    ) -> Dict[str, Any]:
        """Create a relationship between two records."""
        return await self._send_request("tools/call", {
            "name": "relationship_create",
            "arguments": {
                "from_id": from_id,
                "to_id": to_id,
                "type": relationship_type,
            },
        })


class NativeService:
    """High-level service layer for Native integration with blast-radius-zero.
    
    Provides record management capabilities while maintaining the backend's
    containment-first security model. This service acts as an adapter between
    blast-radius-zero's task execution system and Native's MCP interface.
    """
    
    def __init__(self, config: Optional[NativeConfig] = None):
        self.config = config or NativeConfig.from_env()
        self._client: Optional[NativeMCPClient] = None
        
    async def __aenter__(self) -> "NativeService":
        """Async context manager entry."""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
        
    async def start(self) -> None:
        """Start the Native service connection."""
        if not self._client:
            self._client = NativeMCPClient(self.config)
            await self._client.connect()
            
    async def stop(self) -> None:
        """Stop the Native service connection."""
        if self._client:
            await self._client.disconnect()
            self._client = None
            
    async def initialize(self) -> Dict[str, Any]:
        """Initialize the Native service and get engine info."""
        await self.start()
        return await self._client.engine_info()
        
    async def create_decision(
        self,
        title: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a decision record."""
        record = {
            "title": title,
            "body": description,
            "kind": "decision",
            "metadata": metadata or {},
            "visibility": "team",
        }
        return await self._client.create_record(record)
        
    async def create_task(
        self,
        title: str,
        description: str,
        related_decision_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a task record, optionally linked to a decision."""
        record = {
            "title": title,
            "body": description,
            "kind": "task",
            "metadata": metadata or {},
            "visibility": "team",
        }
        result = await self._client.create_record(record)
        
        if related_decision_id:
            await self._client.create_relationship(
                result["id"], related_decision_id, "depends_on"
            )
            
        return result
        
    async def get_record(self, record_id: str) -> Dict[str, Any]:
        """Get a record by ID."""
        return await self._client.read_record(record_id)
        
    async def list_records(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """List records, optionally filtered by kind."""
        query = {"kind": kind} if kind else {}
        return await self._client.query_records(query)
        
    async def create_decision_and_task(
        self,
        decision_title: str,
        decision_description: str,
        task_title: str,
        task_description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a decision record and a task linked to it."""
        decision = await self.create_decision(
            decision_title, decision_description, metadata
        )
        task = await self.create_task(
            task_title, task_description, decision["id"], metadata
        )
        return {"decision": decision, "task": task}


def get_native_service() -> NativeService:
    """Get or create the Native service instance.
    
    This function provides a singleton pattern for the Native service,
    ensuring proper connection management across the blast-radius-zero backend.
    """
    from .config import Settings
    
    settings = Settings.from_env()
    config = NativeConfig.from_env()
    
    return NativeService(config)
