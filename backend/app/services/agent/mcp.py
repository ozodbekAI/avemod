from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.agent import (
    AgentMCPRequest,
    AgentMCPResponse,
    AgentToolCallRequest,
    AgentToolsResponse,
)
from app.services.agent.orchestrator import AgentService

if TYPE_CHECKING:
    from app.models.auth import AuthUser


JSONRPC_INVALID_PARAMS = -32602
JSONRPC_METHOD_NOT_FOUND = -32601


class AgentMCPService:
    """JSON-RPC MCP adapter over the portal agent tool registry."""

    PROTOCOL_VERSION = "2025-11-25"

    def __init__(self, agent: AgentService | None = None) -> None:
        self.agent = agent or AgentService()

    async def handle(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        role: str,
        user: "AuthUser",
        payload: AgentMCPRequest,
    ) -> AgentMCPResponse:
        if payload.method == "initialize":
            return self._ok(payload.id, self._initialize_result())
        if payload.method == "tools/list":
            return self._ok(payload.id, self._tools_list_result(self.agent.list_tools()))
        if payload.method == "tools/call":
            return await self._tools_call(
                session,
                account_id=account_id,
                role=role,
                user=user,
                payload=payload,
            )
        return self._error(payload.id, JSONRPC_METHOD_NOT_FOUND, "MCP method not found")

    async def _tools_call(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        role: str,
        user: "AuthUser",
        payload: AgentMCPRequest,
    ) -> AgentMCPResponse:
        params = payload.params if isinstance(payload.params, dict) else {}
        tool_name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return self._error(
                payload.id,
                JSONRPC_INVALID_PARAMS,
                "tools/call params.name is required",
            )
        if arguments is not None and not isinstance(arguments, dict):
            return self._error(
                payload.id,
                JSONRPC_INVALID_PARAMS,
                "tools/call params.arguments must be an object",
            )
        response = await self.agent.execute_tool(
            session,
            account_id=account_id,
            role=role,
            user=user,
            payload=AgentToolCallRequest(
                account_id=account_id,
                tool_name=tool_name,
                arguments=arguments or {},
                context=params.get("context")
                if isinstance(params.get("context"), dict)
                else {},
            ),
        )
        structured = response.model_dump(mode="json")
        return self._ok(
            payload.id,
            {
                "content": [{"type": "text", "text": self._tool_result_text(structured)}],
                "structuredContent": structured,
                "isError": response.status in {"blocked", "error"},
            },
        )

    def _initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "finance-wb-agent",
                "title": "WB Seller Portal AI Operator",
                "version": "1.0.0",
            },
            "instructions": (
                "Use tools/list to discover allow-listed portal tools. "
                "State-changing actions return preview/confirmation UI actions; "
                "direct Wildberries writes are disabled."
            ),
        }

    @classmethod
    def _tools_list_result(cls, manifest: AgentToolsResponse) -> dict[str, Any]:
        tools = []
        for tool in manifest.tools:
            read_only = tool.write_policy in {"read", "none"}
            destructive = tool.write_policy not in {"read", "none", "download_only"}
            tools.append(
                {
                    "name": tool.name,
                    "title": tool.title,
                    "description": tool.description,
                    "inputSchema": tool.input_schema
                    or {"type": "object", "additionalProperties": False},
                    "annotations": {
                        "readOnlyHint": read_only,
                        "destructiveHint": destructive,
                        "openWorldHint": False,
                    },
                }
            )
        return {"tools": tools}

    @staticmethod
    def _tool_result_text(value: dict[str, Any]) -> str:
        message = value.get("message")
        if isinstance(message, str) and message.strip():
            return message
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _ok(id_: int | str | None, result: dict[str, Any]) -> AgentMCPResponse:
        return AgentMCPResponse(id=id_, result=result)

    @staticmethod
    def _error(
        id_: int | str | None, code: int, message: str
    ) -> AgentMCPResponse:
        return AgentMCPResponse(id=id_, error={"code": code, "message": message})
