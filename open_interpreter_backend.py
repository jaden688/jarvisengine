"""
Open Interpreter backend adapter for the JL Engine.

Uses the Open Interpreter Python API (non-interactive) instead of the CLI REPL.
"""

import json
from typing import Any, Dict, List, Optional

try:
    # Preferred import path for 0.4.x
    from open_interpreter import OpenInterpreter
except ImportError:
    try:
        # Package installs the module name `interpreter`
        from interpreter import OpenInterpreter
    except ImportError as exc:  # pragma: no cover - surfaced at runtime if missing
        raise ImportError(
            "open-interpreter package is required for the Open Interpreter backend."
        ) from exc


def _coerce_message(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Normalize a single message to include only role/content."""
    if not isinstance(item, dict):
        return None

    role = item.get("role")
    content = item.get("content")
    if not isinstance(role, str):
        return None

    return {
        "role": role,
        "content": "" if content is None else str(content),
    }


def _normalize_history(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Filter and normalize history items to role/content dicts."""
    safe: List[Dict[str, str]] = []
    for item in history or []:
        msg = _coerce_message(item)
        if msg:
            safe.append(msg)
    return safe


def _parse_tool_request(obj: Any) -> Optional[Dict[str, Any]]:
    """Detect a structured tool request sent through the bridge."""
    if isinstance(obj, dict) and obj.get("mode") == "tool":
        return obj
    if isinstance(obj, str):
        try:
            data = json.loads(obj)
        except (TypeError, ValueError):
            return None
        if isinstance(data, dict) and data.get("mode") == "tool":
            return data
    return None


def _format_tool_reply(tool: str, result: Any) -> str:
    status = "ok" if isinstance(result, dict) and result.get("ok") else "error"
    detail = ""
    if isinstance(result, dict):
        detail = (
            result.get("response")
            or result.get("status")
            or result.get("error")
            or ""
        )
    else:
        detail = str(result)
    detail_str = f": {detail}" if detail else ""
    return f"[{tool}] {status}{detail_str}"


def _handle_tool_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Route tool requests without invoking the LLM layer."""
    tool = request.get("tool")
    payload = request.get("payload") if isinstance(request, dict) else None
    payload = payload if isinstance(payload, dict) else {}

    if tool == "send_cnc_gcode":
        try:
            from tools import cnc_tool
            gcode_text = payload.get("gcode", "")
            dry_run = bool(payload.get("dry_run", False))
            result = cnc_tool.send_cnc_gcode(str(gcode_text), dry_run=dry_run)
            return {
                "assistant": _format_tool_reply("send_cnc_gcode", {"ok": True, **result}),
                "tokens": 0,
                "raw": {"tool": "send_cnc_gcode", "result": result},
            }
        except Exception as exc:
            return {
                "assistant": "[send_cnc_gcode] error: tool unavailable",
                "tokens": 0,
                "raw": {"tool": tool, "error": str(exc)},
            }

    if tool == "cnc":
        try:
            from tools import cnc_tool
        except Exception as exc:
            return {
                "assistant": "[cnc] error: cnc tool unavailable",
                "tokens": 0,
                "raw": {"tool": tool, "error": str(exc)},
            }

        result = cnc_tool.cnc(payload)
        return {
            "assistant": _format_tool_reply("cnc", result),
            "tokens": 0,
            "raw": {"tool": "cnc", "result": result},
        }

    return {
        "assistant": f"[tool error] Unknown tool: {tool}",
        "tokens": 0,
        "raw": {"tool": tool, "error": "unknown_tool"},
    }


def to_oi_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Convert JL Engine messages to the format Open Interpreter expects:
    role/content plus a required type="message". Open Interpreter already injects its
    own system message internally, so we downgrade all incoming 'system' roles to
    'assistant' to avoid multiple system messages.
    """
    oi_messages: List[Dict[str, str]] = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Prevent multiple system messages; the interpreter will prepend its own.
        if role == "system":
            role = "assistant"

        oi_messages.append(
            {
                "role": role,
                "content": content,
                "type": "message",
            }
        )

    return oi_messages


def _extract_assistant(raw: Any) -> str:
    """Best-effort extraction of assistant text from various OI response shapes."""
    if isinstance(raw, dict):
        if isinstance(raw.get("message"), dict):
            msg = raw["message"]
            if msg.get("role") == "assistant":
                return str(msg.get("content", ""))
        if isinstance(raw.get("messages"), list):
            for msg in reversed(raw["messages"]):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return str(msg.get("content", ""))
        if "response" in raw:
            return str(raw.get("response", ""))

    if isinstance(raw, list):
        for msg in reversed(raw):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                return str(msg.get("content", ""))

    if raw is None:
        return ""
    return str(raw)


def _extract_tokens(raw: Any) -> int:
    """Pull token usage if available."""
    if isinstance(raw, dict) and isinstance(raw.get("usage"), dict):
        usage = raw["usage"]
        for key in ("total_tokens", "tokens", "completion_tokens"):
            if isinstance(usage.get(key), (int, float)):
                try:
                    return int(usage[key])
                except (TypeError, ValueError):
                    continue
    return 0


class OpenInterpreterClient:
    """Stateful wrapper that keeps a single Open Interpreter instance alive."""

    def __init__(self, model: Optional[str] = None):
        self.interpreter = OpenInterpreter(
            auto_run=True,
            in_terminal_interface=False,
            conversation_history=False,
            disable_telemetry=True,
            plain_text_display=True,
        )
        # Reinforce non-interactive defaults in case the constructor signature changes.
        self.interpreter.auto_run = True
        self.interpreter.in_terminal_interface = False
        self.interpreter.conversation_history = False
        self.interpreter.plain_text_display = True
        try:
            # Attach tool metadata for function-calling aware models.
            existing_tools = getattr(self.interpreter, "tools", []) or []
            self.interpreter.tools = existing_tools + OI_TOOLS
        except Exception:
            pass

        if model:
            self.set_model(model)

    def set_model(self, model: str) -> None:
        """Set the underlying model if the adapter exposes one."""
        try:
            self.interpreter.llm.model = model
        except Exception:
            # Best-effort; not all builds expose llm.model
            pass

    def generate(
        self,
        query: Any,
        history: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        tool_request = _parse_tool_request(query)
        if tool_request:
            return _handle_tool_request(tool_request)

        if model:
            self.set_model(model)

        messages = _normalize_history(history)
        messages.append({"role": "user", "content": query or ""})
        oi_messages = to_oi_messages(messages)

        raw_response: Any = self.interpreter.chat(
            message=oi_messages,
            display=False,  # Crucial: avoid the terminal_interface/CLI REPL.
            stream=False,
        )

        assistant_text = _extract_assistant(raw_response)
        tokens_used = _extract_tokens(raw_response)

        return {
            "assistant": assistant_text,
            "tokens": tokens_used,
            "raw": raw_response,
        }


_CLIENT: Optional[OpenInterpreterClient] = None
OI_TOOLS = [
    {
        "name": "send_cnc_gcode",
        "description": "Send raw G-code lines to the CNC controller over the existing CNC bridge.",
        "parameters": {
            "type": "object",
            "properties": {
                "gcode": {
                    "type": "string",
                    "description": "Raw G-code text, may include multiple lines separated by newlines.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, only log/echo the commands without sending them.",
                    "default": False,
                },
            },
            "required": ["gcode"],
        },
    },
    {
        "name": "cnc",
        "description": "CNC control tool: status and raw G-code send.",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["status", "raw"],
                    "description": "\"status\" to query controller, \"raw\" to send G-code.",
                },
                "gcode": {
                    "type": "string",
                    "description": "Raw G-code when mode='raw'.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, log but do not actually send.",
                    "default": False,
                },
            },
            "required": ["mode"],
        },
    },
]


def _get_client(model: Optional[str] = None) -> OpenInterpreterClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenInterpreterClient(model=model)
    elif model:
        _CLIENT.set_model(model)
    return _CLIENT


def run(query: Any, history: List[Dict[str, Any]], model: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a single Open Interpreter turn in non-interactive mode.

    Args:
        query: Latest user message content.
        history: Prior messages (role/content dicts).
        model: Optional model override for this call.

    Returns:
        dict with:
            - assistant: extracted assistant reply text
            - tokens: int token count if available
            - raw: full raw response object from Open Interpreter
    """
    client = _get_client(model=model)
    return client.generate(query=query, history=history, model=model)
