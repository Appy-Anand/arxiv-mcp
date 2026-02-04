# ArXiv MCP Server

A Model Context Protocol (MCP) server that enables AI assistants to search and discover academic papers from arXiv using semantic search capabilities powered by the ArXivXplorer API.

## How It Works

This MCP server acts as a bridge between AI assistants (like Claude Desktop) and the ArXivXplorer API:

- **ArXivXplorer API**: A third-party service that provides semantic search over arXiv papers (not the official arXiv.org API)
- **Your Server**: Makes direct HTTP requests to ArXivXplorer to search for papers
- **AI Assistant**: Invokes your server as a tool when you ask questions about research papers

**Important**: The AI assistant (Claude) does not perform the search itself. It simply calls this MCP server, which then queries the ArXivXplorer API and returns the results.

## Features

- **Semantic Search**: Find relevant papers using natural language queries
- **Similar Papers**: Discover papers related to a specific arXiv paper
- **Year Filtering**: Filter search results by publication year(s)
- **Rich Metadata**: Get paper titles, authors, abstracts, categories, and direct links

## Available Tools

1. **search_arxiv_papers**: Search for papers using natural language queries
   - Parameters: `query` (string), `limit` (1-100), `years` (optional)
   - Example: "neural networks for image classification"

2. **search_similar_papers**: Find papers similar to a given arXiv paper
   - Parameters: `arxiv_url` (paper URL or ID), `limit` (1-100), `years` (optional)
   - Example: "2301.12345" or "https://arxiv.org/abs/2301.12345"

## Prerequisites

- Python 3.13 or higher
- [uv](https://docs.astral.sh/uv/) package manager (recommended) or pip

## Installation

1. Clone the repository:
```bash
git clone git@github.com:Appy-Anand/arxiv-mcp.git
cd arxiv-mcp
```

2. Install dependencies:
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

## Configuration with Claude Desktop

To use this MCP server with Claude Desktop, add the following to your Claude configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "arxiv": {
      "command": "uv",
      "args": [
        "--directory",
        "/ABSOLUTE/PATH/TO/arxiv-mcp",
        "run",
        "arxiv_server_v2.py"
      ]
    }
  }
}
```

Replace `/ABSOLUTE/PATH/TO/arxiv-mcp` with the actual path to the cloned repository.

If you're using pip instead of uv:
```json
{
  "mcpServers": {
    "arxiv": {
      "command": "python",
      "args": [
        "/ABSOLUTE/PATH/TO/arxiv-mcp/arxiv_server_v2.py"
      ]
    }
  }
}
```

After updating the config, restart Claude Desktop.

## Testing/Development

To test the server using the MCP inspector:

```bash
mcp dev arxiv_server_v2.py
```

This will open a web interface where you can test the available tools.

## Usage Examples

Once configured with Claude Desktop, you can ask Claude:

- "Search for recent papers about transformer architectures"
- "Find papers similar to arXiv paper 2301.12345"
- "Search for machine learning papers from 2024"
- "Find papers about quantum computing published in 2023 or 2024"

## Project Structure

- `arxiv_server_v2.py` - Main MCP server implementation
- `pyproject.toml` - Project dependencies and configuration

- `README.md` - This file

## Credits

Built using:
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [ArXivXplorer API](https://gptstore.ai/gpts/vUPoYY1pm7-arxiv-xplorer/actions) - Semantic search API

Inspired by [arxiv-semantic-search-mcp](https://github.com/tan-yong-sheng/arxiv-semantic-search-mcp)

## License

MIT