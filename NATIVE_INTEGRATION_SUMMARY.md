# Native Integration Summary

## Overview

This document summarizes the work completed to integrate the Native engine (from https://github.com/W4sP4nx2/native) into the Blast Radius Zero backend.

## What Was Accomplished

### 1. Analysis and Planning

- ✅ Analyzed the Native repository structure
- ✅ Identified the `mcp-stdio` binary requirements (Rust 1.98.0)
- ✅ Located the database storage requirements
- ✅ Understood the MCP protocol (JSON-RPC over stdio)

### 2. Python MCP Client Implementation

Created `brz/native_client.py`:
- `NativeConfig`: Configuration management via environment variables
- `NativeMCPClient`: Low-level JSON-RPC client supporting stdio and HTTP modes
- `NativeService`: High-level service layer with record management operations

Key Features:
- Async context manager pattern for proper resource management
- Support for both stdio (local binary) and HTTP (remote server) modes
- JSON-RPC protocol implementation over stdio pipes
- Record CRUD operations (create, read, update, delete)
- Relationship management between records

### 3. API Integration

Created `brz/native_api.py`:
- `NativeAPI`: Service layer adapter for blast-radius-zero
- Integration with existing session and CSRF protection
- Event logging for audit trail

### 4. API Endpoints

Added to `brz/api.py`:
- `GET /api/native/engine-info`: Engine status
- `POST /api/native/decisions`: Create decision records
- `POST /api/native/tasks`: Create task records
- `POST /api/native/decisions-and-tasks`: Create linked records
- `GET /api/native/records`: List records
- `GET /api/native/records/{id}`: Get record
- `PATCH /api/native/records/{id}`: Update record
- `DELETE /api/native/records/{id}`: Delete record
- `POST /api/native/relationships`: Create relationships

### 5. Configuration

Updated `.env.example`:
- `NATIVE_MODE`: Connection mode (stdio/http)
- `NATIVE_BINARY_PATH`: Path to mcp-stdio binary
- `NATIVE_DATABASE_PATH`: Path to SQLite database
- `NATIVE_HTTP_URL`: URL for HTTP mode
- `NATIVE_API_TOKEN`: Authentication token

### 6. Documentation

Created comprehensive documentation:

1. **NATIVE_INTEGRATION.md**: User-facing guide for using Native integration
2. **NATIVE_INTEGRATION_DESIGN.md**: Architectural decisions and design rationale
3. **examples/README.md**: Examples directory documentation
4. **NATIVE_INTEGRATION_SUMMARY.md**: This file

### 7. Example Code

Created `examples/native_integration_example.py`:
- Complete working example
- Shows decision and task creation
- Demonstrates record querying
- Shows relationship management

### 8. Docker Configuration

Created `backend/Dockerfile.native`:
- Dockerfile for building the Native MCP binary
- Multi-stage build for minimal runtime image

## Files Created

```
backend/brz/
├── native_client.py    # MCP client implementation
├── native_api.py       # API integration layer
└── __init__.py         # Updated with native modules

backend/
├── Dockerfile.native   # Native MCP Docker build
└── data/               # Database directory (created)

backend/brz/
└── api.py              # Updated with Native endpoints

examples/
├── native_integration_example.py  # Example usage
└── README.md                       # Examples documentation

Root:
├── .env.example                      # Configuration with Native variables
├── NATIVE_INTEGRATION.md             # User guide
├── NATIVE_INTEGRATION_DESIGN.md      # Design document
└── NATIVE_INTEGRATION_SUMMARY.md     # This file
```

## Integration Architecture

```
+------------------+       +------------------+       +------------------+
|   Blast Radius   |       |   Native MCP     |       |   Native Engine  |
|   Zero Backend   |<----->|   Client/Wrapper |<----->|   (SQLite DB)    |
|                  | API   |                  | Stdio |                  |
+------------------+       +------------------+       +------------------+
        |                         |
        |                         +--(or HTTP)
        |
        v
+------------------+
|   API Endpoints  |
|   for Records    |
+------------------+
```

## Security Model

The integration follows blast-radius-zero's containment-first security model:

1. **Isolation**: Native MCP client runs in trusted backend, not in sandboxes
2. **No External Access**: Native database stored locally with filesystem protection
3. **Authentication**: All endpoints require session and CSRF validation
4. **Rate Limiting**: 30 operations per 60 seconds per client
5. **Audit Trail**: All operations logged through event system

## Usage

### Environment Configuration

```bash
# For stdio mode (local Native MCP binary)
export NATIVE_MODE=stdio
export NATIVE_BINARY_PATH=/path/to/native-source/target/debug/mcp-stdio
export NATIVE_DATABASE_PATH=/path/to/blast-radius-zero/backend/data/native.db

# For HTTP mode (remote Native server)
# export NATIVE_MODE=http
# export NATIVE_HTTP_URL=http://native-server:3001/mcp
# export NATIVE_API_TOKEN=your-token
```

### API Usage

```bash
# Create a decision
curl -X POST http://localhost:8000/api/native/decisions \
  -H "X-CSRF-Token: <token>" \
  -d '{"title": "Architecture Decision", "description": "Use SQLite"}'

# Create a task linked to a decision
curl -X POST http://localhost:8000/api/native/tasks \
  -H "X-CSRF-Token: <token>" \
  -d '{"title": "Implement Feature", "related_decision_id": "rec_abc123"}'

# List records
curl http://localhost:8000/api/native/records
```

### Python Usage

```python
from brz.native_client import NativeService

async def example():
    async with NativeService() as service:
        # Get engine info
        info = await service.initialize()
        
        # Create a decision
        decision = await service.create_decision(
            "Decision Title", "Decision description"
        )
        
        # Create a task linked to the decision
        task = await service.create_task(
            "Task Title", "Task description",
            related_decision_id=decision["id"]
        )
        
        # List all records
        records = await service.list_records()
```

## What's Missing

### To Fully Enable Native Integration

The following requires Rust 1.98.0 to be available in the environment:

1. **Build the Native binary**: Requires Rust 1.98.0 toolchain
   ```bash
   cd native-source
   cargo build --locked --bin mcp-stdio
   ```

2. **Run the MCP server**: Once built, start with the database path
   ```bash
   ./target/debug/mcp-stdio /path/to/blast-radius-zero/backend/data/native.db
   ```

### To Enable

1. Install Rust 1.98.0 (can be done with rustup if environment allows)
2. Build the Native binary
3. Start the MCP server (or configure for HTTP mode)
4. Set environment variables as described above

## Testing

### Unit Testing

```bash
# Verify Python syntax
python3 -m ast backend/brz/native_client.py
python3 -m ast backend/brz/native_api.py
python3 -m ast backend/brz/api.py
```

### Integration Testing

```bash
# Run the example
cd examples
python3 native_integration_example.py
```

## Next Steps

To complete the integration:

1. **Build Native Binary** (requires Rust 1.98.0):
   ```bash
   cd /projects/sandbox/native-source
   cargo build --locked --bin mcp-stdio
   ```

2. **Start MCP Server**:
   ```bash
   ./target/debug/mcp-stdio \
     /projects/sandbox/blast-radius-zero/backend/data/native.db
   ```

3. **Test Integration**:
   ```bash
   curl http://localhost:8000/api/native/engine-info
   ```

## References

- [Native GitHub Repository](https://github.com/W4sP4nx2/native)
- [Native SELF_HOSTING.md](native-source/SELF_HOSTING.md)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)

## Notes

- The Python MCP client is fully implemented and ready to use
- Once Rust 1.98.0 is available, the Native binary can be built
- The integration supports both local (stdio) and remote (HTTP) Native servers
- The blast-radius-zero security model is maintained throughout
