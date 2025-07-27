import asyncio
import base64
import json
import logging
import os
import pathlib
import signal
import uuid
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from starlette.requests import Request

from backends.content_fetcher_factory import ContentFetcherFactory
from backends.content_fetcher_protocol import ContentFetcherProtocol
from backends.models import FormattedResult
from backends.search_factory import SearchClientFactory
from backends.search_protocol import SearchClientProtocol
from core import PromptManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class ServerConfig:
    def __init__(self) -> None:
        self.sse_port = int(os.getenv("MCP_SSE_PORT", "8000"))
        self.streamable_http_port = int(os.getenv("MCP_STREAMABLE_HTTP_PORT", "8080"))

        # Langfuse configuration
        self.langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"
        if self.langfuse_enabled:
            self.langfuse_public_key = self._get_required_env("LANGFUSE_PUBLIC_KEY")
            self.langfuse_secret_key = self._get_required_env("LANGFUSE_SECRET_KEY")
            self.langfuse_host = self._get_required_env("LANGFUSE_HOST")
        else:
            self.langfuse_public_key = ""
            self.langfuse_secret_key = ""
            self.langfuse_host = ""

        self.search_backend = self._get_required_env("SEARCH_BACKEND").lower()
        self.zoekt_api_url = ""
        self.sourcegraph_endpoint = ""
        self.sourcegraph_token = ""
        if self.search_backend == "zoekt":
            self.zoekt_api_url = self._get_required_env("ZOEKT_API_URL")
        elif self.search_backend == "sourcegraph":
            self.sourcegraph_endpoint = self._get_required_env("SRC_ENDPOINT")
            self.sourcegraph_token = os.getenv("SRC_ACCESS_TOKEN", "")  # it may not always be mandatory
        else:
            raise ValueError("Invalid option for SEARCH_BACKEND. Valid options are [zoekt|sourcegraph] ")

    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get required environment variable or raise descriptive error."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value


class TelemetryManager:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.enabled = config.langfuse_enabled
        if self.enabled:
            self._setup_telemetry()

    def _setup_telemetry(self) -> None:
        langfuse_auth = base64.b64encode(
            f"{self.config.langfuse_public_key}:{self.config.langfuse_secret_key}".encode()
        ).decode()

        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {langfuse_auth}"
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"{self.config.langfuse_host}/api/public/otel"

        trace_provider = TracerProvider()
        trace_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(trace_provider)

    def get_tracer(self, name: str) -> trace.Tracer:
        if self.enabled:
            return trace.get_tracer(name)
        else:
            # Return a no-op tracer when disabled
            return trace.get_tracer(name, tracer_provider=TracerProvider())


config = ServerConfig()
telemetry = TelemetryManager(config)
tracer = telemetry.get_tracer("codesearch-mcp")

server = FastMCP(sse_path="/codesearch/sse", message_path="/codesearch/messages/")

search_client_kwargs = {
    "base_url": config.zoekt_api_url,
    "endpoint": config.sourcegraph_endpoint,
    "token": config.sourcegraph_token,
}
search_client: SearchClientProtocol = SearchClientFactory.create_client(
    backend=config.search_backend, **search_client_kwargs
)
logger.info(f"Using {config.search_backend} search backend")

content_fetcher_kwargs = {
    "zoekt_url": config.zoekt_api_url,
    "endpoint": config.sourcegraph_endpoint,
    "token": config.sourcegraph_token,
}
content_fetcher: ContentFetcherProtocol = ContentFetcherFactory.create_fetcher(
    backend=config.search_backend, **content_fetcher_kwargs
)
logger.info(f"Using {config.search_backend} content fetcher backend")

prompt_manager = PromptManager(file_path=pathlib.Path(__file__).parent.parent.parent / "prompts" / "prompts.yaml")

# Load backend-specific prompts
CODESEARCH_GUIDE = prompt_manager._load_prompt(f"guides.codesearch_guide.{config.search_backend}")
SEARCH_TOOL_DESCRIPTION = prompt_manager._load_prompt(f"tools.search.{config.search_backend}")
SEARCH_PROMPT_GUIDE_DESCRIPTION = prompt_manager._load_prompt(f"tools.search_prompt_guide.{config.search_backend}")
FETCH_CONTENT_DESCRIPTION = prompt_manager._load_prompt("tools.fetch_content")

# Load organization-specific guide (may be empty/placeholder)
try:
    ORG_GUIDE = prompt_manager._load_prompt("guides.org_guide")
except Exception:
    ORG_GUIDE = ""  # Fallback if not found

_shutdown_requested = False


def signal_handler(sig: int, frame: Any) -> None:
    """Handle termination signals for graceful shutdown."""
    global _shutdown_requested
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    _shutdown_requested = True


def _set_span_attributes(
    span: trace.Span,
    input_data: Dict[str, Any],
    output_data: Dict[str, Any],
    session_id: str,
) -> None:
    if not telemetry.enabled:
        return
    try:
        span.set_attribute("langfuse.session.id", session_id)
        span.set_attribute("langfuse.tags", ["codesearch-mcp"])
        span.set_attribute("input", json.dumps(input_data))
        span.set_attribute("output", json.dumps(output_data))
    except Exception as exc:
        logger.error(f"Error setting span attributes: {exc}")


@tracer.start_as_current_span("CodeContextProvider:fetch_content")
def fetch_content(repo: str, path: str) -> str:
    if _shutdown_requested:
        logger.info("Shutdown in progress, declining new requests")
        return ""

    span = trace.get_current_span()
    request: Request = get_http_request()
    trace_id = str(request.headers.get("X-TRACE-ID", uuid.uuid4()))

    try:
        result = content_fetcher.get_content(repo, path)

        input_data = {"repo": repo, "path": path}
        output_data = {"output": result}
        _set_span_attributes(span, input_data, output_data, trace_id)

        return result
    except ValueError as e:
        logger.warning(f"Error fetching content from {repo}: {str(e)}")
        return "invalid arguments the given path or repository does not exist"
    except Exception as e:
        logger.error(f"Unexpected error fetching content: {e}")
        return "error fetching content"


@tracer.start_as_current_span("CodeContextProvider:search")
def search(query: str) -> List[FormattedResult]:
    if _shutdown_requested:
        logger.info("Shutdown in progress, declining new requests")
        return []

    num_results = 30

    request: Request = get_http_request()
    trace_id = str(request.headers.get("X-TRACE-ID", uuid.uuid4()))
    span = trace.get_current_span()

    try:
        results = search_client.search(query, num_results)
        formatted_results = search_client.format_results(results, num_results)

        simplified_results = [
            {
                "repository": result.repository,
                "file_name": result.filename,
                "matches": [{"line_number": match.line_number} for match in result.matches],
            }
            for result in formatted_results
        ]

        input_data = {"query": query}
        output_data = {"results": simplified_results}
        _set_span_attributes(span, input_data, output_data, trace_id)

        return formatted_results
    except requests.exceptions.HTTPError as exc:
        logger.error(f"Search HTTP error: {exc}")
        return []
    except Exception as exc:
        logger.error(f"Unexpected error during search: {exc}")
        return []


def search_prompt_guide(objective: str) -> str:
    if _shutdown_requested:
        logger.info("Shutdown in progress, declining new prompt guide requests")
        return "Server is shutting down"

    prompt_parts = []

    if ORG_GUIDE:
        prompt_parts.append(ORG_GUIDE)
        prompt_parts.append("\n\n")

    prompt_parts.append(CODESEARCH_GUIDE)
    prompt_parts.append(
        f"\nGiven this guide create a {config.search_backend} query for {objective} and call the search tool accordingly."
    )

    return "".join(prompt_parts)


def _register_tools() -> None:
    """Register MCP tools with the server."""
    tool_descriptions = {
        "search": SEARCH_TOOL_DESCRIPTION,
        "search_prompt_guide": SEARCH_PROMPT_GUIDE_DESCRIPTION,
        "fetch_content": FETCH_CONTENT_DESCRIPTION,
    }

    tools = [
        (search, "search"),
        (search_prompt_guide, "search_prompt_guide"),
        (fetch_content, "fetch_content"),
    ]

    for tool_func, tool_name in tools:
        description = tool_descriptions.get(tool_name, "")
        server.add_tool(tool_func, tool_name, description)
        logger.info(f"Registered tool: {tool_name}")


async def _run_server() -> None:
    """Run the FastMCP server with both HTTP and SSE transports."""
    tasks = [
        server.run_http_async(
            transport="streamable-http",
            host="0.0.0.0",
            path="/codesearch/mcp",
            port=config.streamable_http_port,
        ),
        server.run_http_async(transport="sse", host="0.0.0.0", port=config.sse_port),
    ]
    await asyncio.gather(*tasks)


def main() -> None:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    _register_tools()

    try:
        logger.info("Starting Code Search MCP server...")
        asyncio.run(_run_server())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt (CTRL+C)")
    except Exception as exc:
        logger.error(f"Server error: {exc}")
        raise
    finally:
        logger.info("Server has shut down.")
