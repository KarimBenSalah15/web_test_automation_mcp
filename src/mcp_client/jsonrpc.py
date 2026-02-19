from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any


_jsonrpc_id = itertools.count(1)


@dataclass(slots=True)
class JsonRpcRequest:
    method: str
    params: dict[str, Any] | None = None
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": self.method,
        }
        if self.params is not None:
            payload["params"] = self.params
        if self.id is not None:
            payload["id"] = self.id
        return payload


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"JSON-RPC error {code}: {message}")


def next_id() -> int:
    return next(_jsonrpc_id)


def build_request(method: str, params: dict[str, Any] | None = None) -> JsonRpcRequest:
    return JsonRpcRequest(method=method, params=params, id=next_id())


def is_response(payload: dict[str, Any]) -> bool:
    return payload.get("jsonrpc") == "2.0" and "id" in payload and (
        "result" in payload or "error" in payload
    )


def is_notification(payload: dict[str, Any]) -> bool:
    return payload.get("jsonrpc") == "2.0" and "method" in payload and "id" not in payload


def extract_result(payload: dict[str, Any]) -> Any:
    if "error" in payload:
        err = payload["error"]
        raise JsonRpcError(
            code=err.get("code", -32000),
            message=err.get("message", "Unknown JSON-RPC error"),
            data=err.get("data"),
        )
    return payload.get("result")
