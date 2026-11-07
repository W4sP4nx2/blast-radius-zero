# Native Integration with Blast Radius Zero

This document describes how Native is integrated into blast-radius-zero.

## Architecture Overview

Blast Radius Zero integrates with Native through a flexible, containment-first approach:

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

## Configuration

### Environment Variables

Set these in your `.env` file to configure Native integration:

| Variable | Description | Default |
|----------|-------------|---------|
| `NATIVE_MODE` | Connection mode: "stdio" or "http" | "stdio" |
| `NATIVE_BINARY_PATH` | Path to mcp-stdio binary (stdio mode) | - |
| `NATIVE_DATABASE_PATH` | Path to Native database file | - |
| `NATIVE_HTTP_URL` | URL to Native HTTP endpoint (http mode) | - |
| `NATIVE_API_TOKEN` | API token for HTTP authentication | - |

### Stdio Mode Configuration

For local Native MCP server (requires Rust 1.98.0 to build):

```bash
# Build the Native binary
cd native-source
cargo build --locked --bin mcp-stdio

# Set environment variables
export NATIVE_MODE=stdio
export NATIVE_BINARY_PATH=/path/to/native-source/target/debug/mcp-stdio
export NATIVE_DATABASE_PATH=/path/to/blast-radius-zero/backend/data/native.db
```

### HTTP Mode Configuration

For remote Native MCP server:

```bash
# Set environment variables for HTTP mode
export NATIVE_MODE=http
export NATIVE_HTTP_URL=http://native-server:3001/mcp
export NATIVE_API_TOKEN=your-auth-token
```

## API Endpoints

### Engine Information

**GET** `/api/native/engine-info`

Get information about the connected Native engine.

### Create Decision

**POST** `/api/native/decisions`

Create a decision record in Native.

```json
{
  "title": "Project Architecture Decision",
  "description": "Use SQLite for local storage",
  "metadata": {
    "author": "team",
    "category": "infrastructure"
  }
}
```

### Create Task

**POST** `/api/native/tasks`

Create a task record in Native.

```json
{
  "title": "Implement Feature X",
  "description": "Add support for Native integration",
  "related_decision_id": "record-id-here",
  "metadata": {
    "assignee": "developer",
    "priority": "high"
  }
}
```

### Create Decision and Task

**POST** `/api/native/decisions-and-tasks`

Create a decision and task, automatically linking them.

```json
{
  "decision_title": "Database Choice",
  "decision_description": "Use SQLite for simplicity",
  "task_title": "Setup SQLite Database",
  "task_description": "Configure SQLite for local development",
  "metadata": {
    "project": "Native Integration"
  }
}
```

### Get Record

**GET** `/api/native/records/{record_id}`

Retrieve a specific record by ID.

### List Records

**GET** `/api/native/records`

List all records, optionally filtered by kind.

```
GET /api/native/records?kind=decision
```

### Update Record

**PATCH** `/api/native/records/{record_id}`

Update an existing record.

```json
{
  "updates": {
    "title": "Updated Title",
    "metadata": {"status": "completed"}
  }
}
```

### Delete Record

**DELETE** `/api/native/records/{record_id}`

Delete a record.

### Create Relationship

**POST** `/api/native/relationships`

Create a relationship between two records.

```json
{
  "from_id": "record-id-1",
  "to_id": "record-id-2",
  "type": "depends_on"
}
```

## Security Model

Native integration follows blast-radius-zero's containment-first security model:

1. **Isolation**: Native MCP client runs as part of the trusted backend, not in sandboxes
2. **Authentication**: API endpoints require session and CSRF token validation
3. **Rate Limiting**: Native operations are subject to rate limits (30 per 60 seconds per client)
4. **No External Access**: Native database is stored locally, no direct external access
5. **Audit Trail**: All operations are logged through the event system

## Usage in Workflows

### Creating a Decision and Task

```python
from brz.native_api import create_native_api

async def create_workflow():
    api = await create_native_api()
    
    # Create a decision and task together
    result = await api.create_decision_and_task(
        decision_title="Security Review",
        decision_description="Complete security audit before release",
        task_title="Review Security Controls",
        task_description="Verify all containment controls are in place"
    )
    
    decision_id = result["decision"]["id"]
    task_id = result["task"]["id"]
    
    print(f"Created decision: {decision_id}")
    print(f"Created task: {task_id}")
```

### Querying Records

```python
async def list_tasks():
    api = await create_native_api()
    
    # List all tasks
    tasks = await api.list_records(kind="task")
    for task in tasks:
        print(f"Task: {task['title']}")
        
    # Get specific record
    record = await api.get_record(task_id)
    print(f"Record: {record}")
```

### Creating Relationships

```python
async def link_records():
    api = await create_native_api()
    
    # Link task to decision
    await api.create_relationship(
        from_id=task_id,
        to_id=decision_id,
        relationship_type="depends_on"
    )
    
    # Link related tasks
    await api.create_relationship(
        from_id=task_id,
        to_id=related_task_id,
        relationship_type="blocks"
    )
```

## Building the Native Binary

### Prerequisites

- Rust 1.98.0 or later
- Git

### Build Steps

```bash
# Clone the Native repository
cd /projects/sandbox
git clone https://github.com/W4sP4nx2/native.git native-source

# Build the mcp-stdio binary
cd native-source
cargo build --locked --bin mcp-stdio

# The binary will be at:
# target/debug/mcp-stdio
```

### Database Setup

The database is automatically created when the mcp-stdio binary is first launched:

```bash
# The database path is configured via NATIVE_DATABASE_PATH
# Example: /projects/sandbox/blast-radius-zero/backend/data/native.db
```

## Troubleshooting

### Connection Issues

**Error**: "Not connected to Native MCP server"
- Ensure `NATIVE_BINARY_PATH` is set correctly
- Verify the binary exists and is executable
- Check that `NATIVE_DATABASE_PATH` directory is writable

**Error**: "Failed to receive response"
- Ensure the Native MCP server is running
- Check that the database file is not locked by another process
- Verify stdio pipes are not blocked

### Build Issues

**Error**: "rustc 1.92.0 is not supported"
- Ensure Rust 1.98.0 or later is installed
- Check `rustc --version` matches requirements
- Update toolchain: `rustup update`

### Permission Issues

**Error**: "Database is locked" or "Read-only file system"
- Ensure the database directory is writable by the backend process
- Check that no other process is accessing the database
- Verify file system permissions

## References

- [Native GitHub Repository](https://github.com/W4sP4nx2/native)
- [Native MCP Server Documentation](SELF_HOSTING.md)
- [Blast Radius Zero Documentation](README.md)
- [Model Context Protocol](https://modelcontextprotocol.io)
