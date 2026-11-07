#!/usr/bin/env python3
"""
Example script demonstrating Native MCP integration with Blast Radius Zero.

This example shows how to:
1. Create a decision record in Native
2. Create a task record linked to the decision
3. Query existing records
4. Update and manage records
"""

import asyncio
import json
import os
import sys

# Add the backend to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from brz.native_client import NativeService, NativeConfig
from brz.config import Settings


async def main():
    """Example usage of Native integration."""
    print("=" * 60)
    print("Blast Radius Zero - Native MCP Integration Example")
    print("=" * 60)
    print()
    
    # Load configuration from environment
    native_config = NativeConfig.from_env()
    print(f"Native Configuration:")
    print(f"  Mode: {native_config.mode}")
    print(f"  Binary Path: {native_config.binary_path}")
    print(f"  Database Path: {native_config.database_path}")
    print()
    
    # Create the Native service
    async with NativeService(native_config) as service:
        # Initialize and get engine info
        print("Initializing Native service...")
        engine_info = await service.initialize()
        print(f"Engine: {engine_info.get('structuredContent', {}).get('engine', 'Unknown')}")
        print()
        
        # Create a decision record
        print("Creating decision record...")
        decision = await service.create_decision(
            title="MCP Integration Strategy",
            description="Integrate Native engine for context management",
            metadata={
                "author": "developer",
                "category": "infrastructure",
                "priority": "high",
            },
        )
        print(f"Decision created: {decision.get('id')}")
        print(f"  Title: {decision.get('title')}")
        print()
        
        # Create a task linked to the decision
        print("Creating task linked to decision...")
        task = await service.create_task(
            title="Implement Native MCP Client",
            description="Create Python wrapper for Native MCP server",
            related_decision_id=decision.get("id"),
            metadata={
                "assignee": "developer",
                "status": "in_progress",
            },
        )
        print(f"Task created: {task.get('id')}")
        print(f"  Title: {task.get('title')}")
        print(f"  Linked to decision: {decision.get('id')}")
        print()
        
        # Query records
        print("Querying records...")
        decisions = await service.list_records(kind="decision")
        print(f"Found {len(decisions)} decision(s):")
        for d in decisions:
            print(f"  - {d.get('title')} ({d.get('id')})")
        
        tasks = await service.list_records(kind="task")
        print(f"Found {len(tasks)} task(s):")
        for t in tasks:
            print(f"  - {t.get('title')} ({t.get('id')})")
        print()
        
        # Update a record
        print("Updating task status...")
        updated = await service._client.update_record(
            task.get("id"),
            {"metadata": {"status": "completed"}},
        )
        print(f"Task updated: {updated.get('id')}")
        print()
        
        # Create another decision and task
        print("Creating another decision and task...")
        result = await service.create_decision_and_task(
            decision_title="Database Schema Design",
            decision_description="Use SQLite for local development",
            task_title="Create Database Schema",
            task_description="Define SQLite tables and relationships",
            metadata={"project": "Native Integration"},
        )
        print(f"Decision: {result['decision'].get('id')}")
        print(f"Task: {result['task'].get('id')}")
        print()
        
        # List all records
        print("All records:")
        all_records = await service.list_records()
        for record in all_records:
            print(f"  [{record.get('kind', 'unknown').upper()}] {record.get('title')} ({record.get('id')})")
        print()
        
        # Create a relationship between records
        print("Creating relationship between records...")
        relationship = await service._client.create_relationship(
            from_id=task.get("id"),
            to_id=updated.get("id"),
            relationship_type="related",
        )
        print(f"Relationship created")
        print()
        
        print("=" * 60)
        print("Example completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
