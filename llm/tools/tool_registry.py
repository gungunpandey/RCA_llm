"""
Tool Registry for RCA Analysis Tools

Manages registration and execution of RCA analysis tools.
"""

from typing import Dict, List, Type, Any, Optional
import logging

from tools.base_tool import BaseTool
from models.tool_results import ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing RCA analysis tools.
    
    Provides centralized tool registration, discovery, and execution.
    """
    
    def __init__(self):
        """Initialize empty tool registry."""
        self._tools: Dict[str, BaseTool] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_tool(self, name: str, tool_instance: BaseTool) -> None:
        """
        Register a tool instance.
        
        Args:
            name: Unique name for the tool
            tool_instance: Initialized tool instance
        """
        if name in self._tools:
            self.logger.warning(f"Tool '{name}' already registered, overwriting")
        
        self._tools[name] = tool_instance
        self.logger.info(f"Registered tool: {name}")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Get a registered tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """
        List all registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    async def execute_tool(
        self,
        name: str,
        failure_description: str,
        equipment_name: str,
        symptoms: List[str],
        **kwargs
    ) -> ToolResult:
        """
        Execute a registered tool.
        
        Args:
            name: Tool name
            failure_description: Failure description
            equipment_name: Equipment name
            symptoms: List of symptoms
            **kwargs: Additional tool-specific parameters
            
        Returns:
            ToolResult from tool execution
            
        Raises:
            ValueError: If tool not found
        """
        tool = self.get_tool(name)
        if tool is None:
            raise ValueError(f"Tool '{name}' not found in registry")
        
        self.logger.info(f"Executing tool: {name}")
        
        result = await tool.analyze(
            failure_description=failure_description,
            equipment_name=equipment_name,
            symptoms=symptoms,
            **kwargs
        )
        
        return result
    
    def unregister_tool(self, name: str) -> bool:
        """
        Unregister a tool.
        
        Args:
            name: Tool name
            
        Returns:
            True if tool was removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            self.logger.info(f"Unregistered tool: {name}")
            return True
        return False
    
    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()
        self.logger.info("Cleared all tools from registry")
