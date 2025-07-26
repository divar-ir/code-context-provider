# Code Context Provider

A Model Context Protocol (MCP) server that provides AI-enhanced code search and context retrieval capabilities using [Sourcegraph](https://sourcegraph.com) or [Zoekt](https://github.com/sourcegraph/zoekt) search backends.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Using UV (recommended)](#using-uv-recommended)
  - [Using pip](#using-pip)
  - [Using Docker](#using-docker)
- [Configuration](#configuration)
  - [Backend Selection](#backend-selection)
  - [Required Environment Variables](#required-environment-variables)
  - [Optional Environment Variables](#optional-environment-variables)
  - [Observability with Langfuse](#observability-with-langfuse)
- [Server Modes](#server-modes)
  - [Search Server](#search-server)
  - [Context Server](#context-server)
- [Usage with AI Tools](#usage-with-ai-tools)
  - [Cursor](#cursor)
  - [Claude Desktop](#claude-desktop)
- [MCP Tools](#mcp-tools)
  - [Search Server Tools](#search-server-tools)
  - [Context Server Tools](#context-server-tools)
- [Development](#development)
  - [Linting and Formatting](#linting-and-formatting)
  - [Running Tests](#running-tests)
  - [Evaluation Framework](#evaluation-framework)

## Overview

Code Context Provider provides two specialized MCP servers for code search and AI-enhanced context retrieval:

1. **Search Server**: Direct code search with repository exploration
2. **Context Server**: AI-enhanced search with query reformulation and intelligent code snippet extraction

Both servers support multiple search backends (Sourcegraph and Zoekt) and include comprehensive observability through Langfuse.

## Features

- **Multiple Search Backends**: Choose between Sourcegraph (cloud/enterprise) or Zoekt (local) search engines
- **Two Operation Modes**: Direct search for speed or AI-enhanced context for intelligence
- **Advanced Query Language**: Support for regex patterns, file filters, language filters, and boolean operators
- **Repository Discovery**: Find repositories by name and explore their structure
- **Content Fetching**: Browse repository files and directories with GitLab integration
- **AI Enhancement**: Query reformulation and intelligent result ranking using LLMs
- **Observability**: Full tracing and monitoring via Langfuse (optional)
- **Rate Limiting**: Built-in rate limiting for API calls and token usage

## Architecture

The project consists of two main MCP servers:

- **Search Server** (`/codesearch`): Provides direct access to search backends
- **Context Server** (`/contextprovider`): Adds AI enhancement layer on top of search

**Important**: The Context Server depends on the Search Server. You must:
1. Start the Search Server first
2. Set `MCP_SERVER_URL` to point to the Search Server's streamable-http endpoint

Supported backends:
- **Sourcegraph**: Universal code search platform (cloud or self-hosted)
- **Zoekt**: Fast trigram-based code search engine (typically local)

## Prerequisites

- **Python 3.10+**: Required for running the MCP servers
- **Search Backend**: Either a Sourcegraph instance or Zoekt server
- **UV** (optional): Modern Python package manager for easier dependency management
- **Langfuse** (optional): For observability and tracing

## Installation

### Using UV (recommended)

```bash
# Install dependencies
uv sync

# Run search server (start this first)
uv run code-context-provider search

# In another terminal, run context server (on different ports)
# Make sure to set MCP_SERVER_URL to the search server's streamable-http endpoint
export MCP_SERVER_URL=http://localhost:8080/codesearch/mcp/
export MCP_SSE_PORT=8001
export MCP_STREAMABLE_HTTP_PORT=8081
uv run code-context-provider context
```

### Using pip

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package
pip install -e .

# Run search server (start this first)
code-context-provider search

# In another terminal, run context server
export MCP_SERVER_URL=http://localhost:8080/codesearch/mcp/
export MCP_SSE_PORT=8001
export MCP_STREAMABLE_HTTP_PORT=8081
code-context-provider context
```

### Using Docker

```bash
# Build the image
docker build -t code-context-provider .
```

To run both servers together, create a `docker-compose.yml` file:

```yaml
version: '3'
services:
  search:
    image: code-context-provider
    command: search
    ports:
      - "8000:8000"
      - "8080:8080"
    environment:
      - SEARCH_BACKEND=sourcegraph
      - SRC_ENDPOINT=https://sourcegraph.com
      - LANGFUSE_ENABLED=false

  context:
    image: code-context-provider
    command: context
    ports:
      - "8001:8000"
      - "8081:8080"
    environment:
      - MCP_SERVER_URL=http://search:8080/codesearch/mcp/
      - LANGFUSE_ENABLED=false
    depends_on:
      - search
```

Then run:
```bash
docker-compose up
```

## Configuration

### Backend Selection

Set `SEARCH_BACKEND` to choose your search backend:
- `sourcegraph`: For Sourcegraph instances
- `zoekt`: For Zoekt search servers

### Required Environment Variables

#### For Sourcegraph Backend:
- `SEARCH_BACKEND=sourcegraph`
- `SRC_ENDPOINT`: Sourcegraph instance URL (e.g., https://sourcegraph.com)

#### For Zoekt Backend:
- `SEARCH_BACKEND=zoekt`
- `ZOEKT_API_URL`: Zoekt server URL (e.g., http://localhost:6070)

#### For Context Server (additional):
- `MCP_SERVER_URL`: URL of the search server's streamable-http endpoint (e.g., http://localhost:8080/codesearch/mcp/)
  - **Important**: This must point to the running Search Server
  - Use `http://host.docker.internal:8080/codesearch/mcp/` when running Context Server in Docker and Search Server on host
  - Use container names when both servers are in the same Docker network

### Optional Environment Variables

- `SRC_ACCESS_TOKEN`: Authentication token for private Sourcegraph instances
- `MCP_SSE_PORT`: SSE server port (default: 8000)
- `MCP_STREAMABLE_HTTP_PORT`: HTTP server port (default: 8080)
  - **Important**: When running both servers on the same machine, use different ports for the Context Server (e.g., 8001 and 8081)
- `LANGFUSE_ENABLED`: Enable/disable Langfuse observability (default: false)

### Observability with Langfuse

Langfuse provides comprehensive tracing and monitoring for all AI operations. 

To enable Langfuse:
```bash
export LANGFUSE_ENABLED=true
export LANGFUSE_PUBLIC_KEY=your-public-key
export LANGFUSE_SECRET_KEY=your-secret-key
export LANGFUSE_HOST=your-langfuse-host
```

**Note**: The evaluation framework requires Langfuse to be enabled for tracking LLM calls and performance metrics.

### Evaluation Models Configuration

The evaluation framework uses configurable LLM models:

```bash
# Configure the code snippet finder model
export CODE_SNIPPET_FINDER_MODEL_NAME=gpt-4o-mini  # default

# Configure the LLM judge model
export LLM_JUDGE_V2_MODEL_NAME=gpt-4o-mini  # default

# Configure the code parser model
export CODE_AGENT_TYPE_PARSER_MODEL_NAME=gpt-4o-mini  # default

# Optional: Use custom LLM endpoints
export LLM_JUDGE_V2_BASE_URL=https://your-llm-endpoint
export LLM_JUDGE_V2_API_KEY=your-api-key
```

## Server Modes

### Search Server

Direct access to search backends with three main tools:

```bash
# Start search server
uv run code-context-provider search
```

Available at:
- SSE: `http://localhost:8000/codesearch/sse`
- HTTP: `http://localhost:8080/codesearch/mcp/`

### Context Server

AI-enhanced search with query understanding and intelligent extraction:

```bash
# Start search server first (in one terminal)
uv run code-context-provider search

# Then start context server (in another terminal)
export MCP_SERVER_URL=http://localhost:8080/codesearch/mcp/
export MCP_SSE_PORT=8001
export MCP_STREAMABLE_HTTP_PORT=8081
uv run code-context-provider context
```

**Note**: The Context Server connects to the Search Server via the MCP_SERVER_URL. Ensure:
1. The Search Server is running before starting the Context Server
2. MCP_SERVER_URL points to the Search Server's streamable-http endpoint (`/codesearch/mcp/`)

Available at (when using different ports):
- SSE: `http://localhost:8001/contextprovider/sse`
- HTTP: `http://localhost:8081/contextprovider/mcp/`

## Usage with AI Tools

### Cursor

Add to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "codesearch": {
      "url": "http://localhost:8080/codesearch/mcp/"
    },
    "contextprovider": {
      "url": "http://localhost:8081/contextprovider/mcp/"
    }
  }
}
```

## MCP Tools

### Search Server Tools

#### 🔍 search
Search across codebases using advanced query syntax.

Example queries:
- `error handler` - Find "error" and "handler" in code
- `func main lang:go` - Find main functions in Go files
- `class.*Service lang:python` - Find Python service classes
- `repo:github.com/example/project` - Search within specific repository

#### 📖 search_prompt_guide
Generate a query guide based on your search objective.

#### 📂 fetch_content
Retrieve file contents or explore directory structures.

### Context Server Tools

#### 🤖 agentic_search
AI-powered search that understands natural language queries and returns relevant code snippets with explanations.

#### 🔄 refactor_question
Reformulate queries into multiple optimized search patterns for better coverage.

## Development

### Linting and Formatting

```bash
# Check code style
uv run ruff check src/

# Format code
uv run ruff format src/
```

#### Manual Testing

For quick testing and dataset creation:

```bash
# First, ensure the search server is running:
uv run code-context-provider search

# In another terminal, set the MCP server URL and run the agent:
export MCP_SERVER_URL=http://localhost:8080/codesearch/mcp/

# Test a single question and save to question.json
uv run ccp-agent -q "How do I implement a Redis cache in Python?"

# Interactive mode
uv run ccp-agent
```

This creates a `question.json` file with the question and AI-generated answer that can be used as evaluation data.

**Note**: The `ccp-agent` command requires the search server to be running as it uses the Context Server's `CodeSnippetFinder` which connects to the search server via MCP.

#### Automated Evaluation

Run comprehensive evaluations against a Langfuse dataset:

```bash
# First, ensure the search server is running:
uv run code-context-provider search

# In another terminal, configure and run evaluation:
export MCP_SERVER_URL=http://localhost:8080/codesearch/mcp/
export LANGFUSE_DATASET_NAME=your-dataset-name  # default: code-search-mcp-agentic-v2

# Run evaluation
uv run ccp-evaluate
```

**Note**: The evaluation framework also requires the search server to be running.

### Evaluation Framework

The evaluation framework provides comprehensive testing capabilities:

#### Components

1. **CodeSnippetFinder**: The AI agent that searches and extracts code snippets
2. **CodeAgentTypeParser**: Parses natural language responses into structured code snippets
3. **LLMJudge**: AI-powered judge that evaluates search result quality

#### LLM Judge

The LLM Judge evaluates search results by comparing actual vs expected answers across multiple dimensions:
- **Issues**: Problems with the retrieved code
- **Strengths**: Positive aspects of the result
- **Suggestions**: Potential improvements
- **Pass/Fail**: Binary evaluation result

#### Dataset Format

Langfuse datasets should contain items with the following structure:

```json
{
  "input": {
    "question": "How do I implement a Redis cache in Python?"
  },
  "expected_output": {
    "snippet": "import redis\n\nclass RedisCache:\n    def __init__(self):\n        self.client = redis.Redis(host='localhost', port=6379)",
    "language": "python",
    "description": "Basic Redis cache implementation in Python"
  }
}
```

#### Features

- **Parallel Evaluation**: Processes multiple test cases concurrently (5 workers by default)
- **Comprehensive Logging**: Results saved to `logs/evaluation-{timestamp}.json`
- **Langfuse Integration**: Full tracing of all LLM calls and evaluations
- **Scoring**: Tracks pass/fail rates and generates aggregate metrics

#### Requirements

- **Langfuse must be enabled** for the evaluation framework to work
- A Langfuse dataset with the correct format must exist
- All Langfuse environment variables must be configured

#### Output

The evaluation generates:
- JSON logs in the `logs/` directory with detailed results
- Langfuse traces for each evaluation run
- Console output with aggregate metrics (pass rate, average score)

## Environment Variables Reference

| Variable                            | Description                        | Required          | Default                    |
|-------------------------------------|------------------------------------|-------------------|----------------------------|
| `SEARCH_BACKEND`                    | Search backend (sourcegraph/zoekt) | Yes               | -                          |
| `SRC_ENDPOINT`                      | Sourcegraph URL                    | Yes (Sourcegraph) | -                          |
| `SRC_ACCESS_TOKEN`                  | Sourcegraph token                  | No                | -                          |
| `ZOEKT_API_URL`                     | Zoekt server URL                   | Yes (Zoekt)       | -                          |
| `MCP_SERVER_URL`                    | Search server URL                  | Yes (Context)     | -                          |
| `MCP_SSE_PORT`                      | SSE server port                    | No                | 8000                       |
| `MCP_STREAMABLE_HTTP_PORT`          | HTTP server port                   | No                | 8080                       |
| `LANGFUSE_ENABLED`                  | Enable Langfuse                    | No                | false                      |
| `LANGFUSE_PUBLIC_KEY`               | Langfuse public key                | If enabled        | -                          |
| `LANGFUSE_SECRET_KEY`               | Langfuse secret key                | If enabled        | -                          |
| `LANGFUSE_HOST`                     | Langfuse host URL                  | If enabled        | -                          |
| `LANGFUSE_DATASET_NAME`             | Dataset name for evaluation        | For evaluation    | code-search-mcp-agentic-v2 |
| `CODE_SNIPPET_FINDER_MODEL_NAME`    | Model for code snippet extraction  | No                | gpt-4o-mini                |
| `LLM_JUDGE_V2_MODEL_NAME`           | Model for LLM judge                | No                | gpt-4o-mini                |
| `CODE_AGENT_TYPE_PARSER_MODEL_NAME` | Model for code parsing             | No                | gpt-4o-mini                |
| `LLM_JUDGE_V2_BASE_URL`             | Custom LLM endpoint for judge      | No                | -                          |
| `LLM_JUDGE_V2_API_KEY`              | API key for custom LLM judge       | No                | -                          |

## License

MIT License - see LICENSE file for details.
