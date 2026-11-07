# Blast Radius Zero Examples

This directory contains example scripts and configurations for Blast Radius Zero.

## Examples

### Native MCP Integration

- [`native_integration_example.py`](native_integration_example.py) - Complete example of using Native MCP with Blast Radius Zero

## Configuration

Examples use environment variables for configuration. See [NATIVE_INTEGRATION.md](../NATIVE_INTEGRATION.md) for details.

## Running Examples

```bash
# Set up environment
cd /projects/sandbox/blast-radius-zero
cp .env.example .env
# Edit .env with your configuration

# Run the example
cd examples
python3 native_integration_example.py
```

## Requirements

- Python 3.13+
- Native MCP server (build from source or connect to remote)
- Access to Blast Radius Zero backend

## See Also

- [Blast Radius Zero Documentation](../README.md)
- [Native Integration Guide](../NATIVE_INTEGRATION.md)
