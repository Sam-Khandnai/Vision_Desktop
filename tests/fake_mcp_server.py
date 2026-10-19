from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("fake")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def echo(text: str) -> str:
    """Echo the text back."""
    return f"echo:{text}"


@mcp.tool()
def delete_note(name: str) -> str:
    """Delete a note."""
    return f"deleted:{name}"


if __name__ == "__main__":
    mcp.run("stdio")
