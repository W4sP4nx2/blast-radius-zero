# Native Integration Design

This document describes the architectural decisions behind integrating Native with Blast Radius Zero.

## Design Principles

### Containment-First Security Model

Blast Radius Zero's security model emphasizes containment and isolation:

1. **No Risk to Host**: Native MCP client runs in the trusted backend, not in sandboxes
2. **No External Access**: Native database is stored locally with filesystem-level protection
3. **Authentication Required**: All API endpoints require session and CSRF validation
4. **Rate Limiting**: Each client has bounded API usage
5. **Audit Trail**: All operations are logged through the event system

### Architecture Decisions

#### 1. Python Client Wrapper

**Decision**: Create a Python MCP client instead of requiring Rust in the sandbox.

**Rationale**:
- Blast Radius Zero's backend is Python-based
- The sandbox environment is intentionally minimal and read-only
- Python client can communicate with both local (stdio) and remote (HTTP) Native servers
- Maintains separation between execution sandbox and trusted backend

**Implementation**:
- `native_client.py`: Low-level JSON-RPC over stdio client
- `native_api.py`: High-level service layer with task-native operations

#### 2. Stdio vs HTTP Modes

**Decision**: Support both stdio (local) and HTTP (remote) connection modes.

**Rationale**:
- Stdio mode: Best for local development and single-host deployments
- HTTP mode: Enables distributed deployments and remote Native instances
- Provides flexibility without changing the client code

**Connection**:
- Stdio: `subprocess.Popen` with pipes for stdin/stdout
- HTTP: `httpx.AsyncClient` with JSON-RPC over POST

#### 3. Service Pattern

**Decision**: Use an async context manager pattern for the Native service.

**Rationale**:
- Proper resource management (connection lifecycle)
- Clean separation between service initialization and usage
- Easy integration with FastAPI lifespan

**Usage**:
```python
async with NativeService(config) as service:
    # Service is connected
    result = await service.create_decision(...)
# Service is disconnected
```

#### 4. API Endpoints

**Decision**: Add Native-specific endpoints to the main API instead of a separate service.

**Rationale**:
- Shared authentication and CSRF protection
- Unified rate limiting
- Consistent error handling
- Single entry point for all backend operations

**Endpoints**:
- `/api/native/engine-info`: Engine status
- `/api/native/decisions`: Create decision records
- `/api/native/tasks`: Create task records
- `/api/native/decisions-and-tasks`: Create linked records
- `/api/native/records`: List and get records
- `/api/native/records/{id}`: Update/delete records
- `/api/native/relationships`: Create relationships

## JSON-RPC Protocol

Native uses the standard JSON-RPC 2.0 protocol over stdio:

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "record_create",
    "arguments": {"record": {...}}
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "id": "rec_abc123",
    "title": "Decision Title",
    ...
  }
}
```

## Security Considerations

### 1. Process Isolation

The Native MCP binary runs as a child process of the backend:

```python
self._proc = subprocess.Popen(
    [self.config.binary_path, self.config.database_path],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
```

**Mitigations**:
- No direct filesystem access from sandboxes
- No network access to Native database
- PID limits and resource constraints

### 2. Authentication

All API endpoints require:

1. Valid session cookie (`brz_session`)
2. CSRF token (`X-CSRF-Token` header)
3. Origin verification

### 3. Rate Limiting

Native operations are rate-limited:
- 30 operations per 60 seconds per client
- Configurable via `NATIVE_RATE_LIMIT_*` environment variables

### 4. Database Protection

The Native database:
- Stored in `/projects/sandbox/blast-radius-zero/backend/data/native.db`
- Protected by filesystem permissions
- No direct external access
- SQLite file locking prevents concurrent writes

## Testing Strategy

### Unit Tests

Test individual components in isolation:

```python
async def test_native_client_connect():
    config = NativeConfig(mode="stdio", binary_path="...", database_path="...")
    client = NativeMCPClient(config)
    await client.connect()
    assert client._connected
    await client.disconnect()
```

### Integration Tests

Test end-to-end workflow:

```python
async def test_decision_task_workflow():
    async with NativeService(config) as service:
        decision = await service.create_decision(...)
        task = await service.create_task(..., related_decision_id=decision["id"])
        records = await service.list_records()
        assert len(records) == 2
```

### Manual Testing

Use the example script:

```bash
python3 examples/native_integration_example.py
```

## Performance Considerations

### Connection Pooling

For HTTP mode:
- Use `httpx.AsyncClient` for connection pooling
- Set appropriate timeouts
- Handle connection failures gracefully

### Stdio Performance

For stdio mode:
- Use async I/O for non-blocking operation
- Buffer responses appropriately
- Handle process lifecycle efficiently

### Concurrency

- Use `asyncio.Lock` for connection management
- Limit concurrent operations via semaphore
- Queue requests when connection is busy

## Error Handling

### Connection Errors

```python
try:
    await client.connect()
except ValueError as e:
    # Configuration error
    logger.error(f"Configuration error: {e}")
except RuntimeError as e:
    # Connection error
    logger.error(f"Connection failed: {e}")
```

### Protocol Errors

```python
try:
    result = await client.engine_info()
except Exception as e:
    # Protocol error
    logger.error(f"Protocol error: {e}")
```

### Graceful Degradation

If Native is unavailable:
- Continue with other backend operations
- Return 503 Service Unavailable
- Provide clear error messages

## Future Enhancements

### 1. Caching

Add caching layer for:
- Frequently accessed records
- Query results
- Engine info

### 2. WebSockets

Support WebSocket transport for:
- Real-time updates
- Bidirectional communication
- Server-sent events

### 3. Federation

Enable multiple Native instances:
- Distributed record storage
- Cross-instance relationships
- Sync protocol

### 4. Monitoring

Add health checks:
- Connection status
- Query latency
- Error rates

## References

- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [Native GitHub Repository](https://github.com/W4sP4nx2/native)
- [Blast Radius Zero Security Model](README.md)
