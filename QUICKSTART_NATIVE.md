# Quick Start: Native Integration

This guide helps you quickly integrate Native with Blast Radius Zero.

## Prerequisites

- Python 3.13+
- Rust 1.98.0 (for building Native MCP binary)
- Docker (optional, for containerized deployment)

## Quick Start Steps

### 1. Clone Native Source

```bash
cd /projects/sandbox
git clone https://github.com/W4sP4nx2/native.git native-source
```

### 2. Build Native MCP Binary

```bash
cd native-source
cargo build --locked --bin mcp-stdio
```

### 3. Configure Environment

```bash
cd /projects/sandbox/blast-radius-zero
cp .env.example .env
# Edit .env with your configuration
```

Add to `.env`:

```bash
NATIVE_MODE=stdio
NATIVE_BINARY_PATH=/projects/sandbox/native-source/target/debug/mcp-stdio
NATIVE_DATABASE_PATH=/projects/sandbox/blast-radius-zero/backend/data/native.db
```

### 4. Start Backend

```bash
cd backend
# Start the FastAPI server
uvicorn main:app --host 127.0.0.1 --port 8000
```

### 5. Test Integration

```bash
# Check engine info
curl http://localhost:8000/api/native/engine-info

# Create a decision
curl -X POST http://localhost:8000/api/native/decisions \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Decision", "description": "Testing Native integration"}'

# Create a task
curl -X POST http://localhost:8000/api/native/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Task", "description": "Testing task creation"}'

# List records
curl http://localhost:8000/api/native/records
```

## Alternative: HTTP Mode

If you can't build the Native binary locally, you can use a remote Native server:

```bash
NATIVE_MODE=http
NATIVE_HTTP_URL=http://native-server:3001/mcp
NATIVE_API_TOKEN=your-auth-token
```

## Verification

Check that everything works:

```bash
# Verify Native binary exists
ls -la /projects/sandbox/native-source/target/debug/mcp-stdio

# Check database directory exists
ls -la /projects/sandbox/blast-radius-zero/backend/data/

# Test API endpoint
curl http://localhost:8000/api/native/engine-info
```

## Common Issues

### Rust 1.98.0 Not Available

If Rust 1.98.0 is not available, you can:

1. Install it with rustup: `rustup install 1.98.0`
2. Use Docker to build: `docker run --rm -v $(pwd):/work rust:1.98.0 cargo build`
3. Use HTTP mode with a remote Native server

### Database Permission Denied

```bash
# Ensure the data directory is writable
chmod 755 /projects/sandbox/blast-radius-zero/backend/data/
```

### Connection Refused

```bash
# Check that the MCP server is running
ps aux | grep mcp-stdio

# Check the database path in the binary arguments
```

## Next Steps

- Read [NATIVE_INTEGRATION.md](NATIVE_INTEGRATION.md) for detailed documentation
- See [NATIVE_INTEGRATION_DESIGN.md](NATIVE_INTEGRATION_DESIGN.md) for architecture details
- Run the example: `python3 examples/native_integration_example.py`

## Support

For issues:
- Check the logs: `backend/logs/`
- Review the event stream: `/api/tasks/{id}/events`
- Check Native repository: https://github.com/W4sP4nx2/native
