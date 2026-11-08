"""Optional Native MCP startup measurement; this is not sandbox latency."""
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.native_integration]


def test_native_mcp_cold_start_engine_info(tmp_path, record_property):
    """Measure the published MCP context engine without claiming code execution."""
    if os.getenv("BRZ_NATIVE_INTEGRATION") != "1":
        pytest.skip("Set BRZ_NATIVE_INTEGRATION=1 with a built mcp-stdio binary")
    binary = Path(os.getenv("NATIVE_MCP_BINARY", "/usr/local/lib/brz/mcp-stdio"))
    if not binary.is_file():
        pytest.fail(f"Native MCP binary not found: {binary}")

    requests = "\n".join([
        json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "brz-benchmark", "version": "1.0.0"},
            },
        }),
        json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "engine_info", "arguments": {}},
        }),
    ]) + "\n"
    started = time.perf_counter()
    completed = subprocess.run(
        [str(binary), str(tmp_path / "native.db")],
        input=requests,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
        env={**os.environ, "NATIVE_CE_MCP_SURFACE": "legacy"},
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    engine = responses[-1]["result"]["structuredContent"]["engine"]
    assert engine == "native-ce"
    record_property("native_mcp_cold_start_ms", duration_ms)
