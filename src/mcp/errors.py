class McpClientError(RuntimeError):
    """Base MCP client error."""


class McpTimeoutError(McpClientError):
    """Raised when an MCP operation times out."""


class McpProtocolError(McpClientError):
    """Raised when MCP protocol responses are invalid."""
