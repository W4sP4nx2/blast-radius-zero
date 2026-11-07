"""Native MCP API integration for blast-radius-zero.

This module provides API endpoints and handlers for Native record management,
integrating with the Native MCP server while maintaining blast-radius-zero's
security model.
"""
import logging
from typing import Any, Dict, List, Optional

from .config import Settings
from .native_client import NativeService, NativeConfig

logger = logging.getLogger(__name__)


class NativeAPI:
    """API handler for Native record management operations.
    
    This class provides methods to interact with Native through the NativeService,
    adapting the MCP protocol to REST-style operations suitable for the
    blast-radius-zero API.
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.from_env()
        self._service: Optional[NativeService] = None
        
    async def _get_service(self) -> NativeService:
        """Get or create the Native service instance."""
        if not self._service:
            self._service = NativeService(NativeConfig.from_env())
            await self._service.start()
        return self._service
        
    async def close(self) -> None:
        """Close the Native service connection."""
        if self._service:
            await self._service.stop()
            self._service = None
            
    async def get_engine_info(self) -> Dict[str, Any]:
        """Get information about the connected Native engine."""
        service = await self._get_service()
        return await service.initialize()
        
    async def create_decision(
        self,
        title: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a decision record in Native."""
        service = await self._get_service()
        return await service.create_decision(title, description, metadata)
        
    async def create_task(
        self,
        title: str,
        description: str,
        related_decision_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a task record in Native."""
        service = await self._get_service()
        return await service.create_task(title, description, related_decision_id, metadata)
        
    async def create_decision_and_task(
        self,
        decision_title: str,
        decision_description: str,
        task_title: str,
        task_description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a decision and task, linking them together."""
        service = await self._get_service()
        return await service.create_decision_and_task(
            decision_title, decision_description, task_title, task_description, metadata
        )
        
    async def get_record(self, record_id: str) -> Dict[str, Any]:
        """Get a record by its ID."""
        service = await self._get_service()
        return await service.get_record(record_id)
        
    async def list_records(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """List records, optionally filtered by kind."""
        service = await self._get_service()
        return await service.list_records(kind)
        
    async def update_record(
        self,
        record_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update a record."""
        service = await self._get_service()
        return await service._client.update_record(record_id, updates)
        
    async def delete_record(self, record_id: str) -> Dict[str, Any]:
        """Delete a record."""
        service = await self._get_service()
        return await service._client.delete_record(record_id)
        
    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        relationship_type: str,
    ) -> Dict[str, Any]:
        """Create a relationship between two records."""
        service = await self._get_service()
        return await service._client.create_relationship(from_id, to_id, relationship_type)


async def create_native_api() -> NativeAPI:
    """Factory function to create a NativeAPI instance."""
    return NativeAPI()
