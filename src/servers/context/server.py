import asyncio
import base64
import json
import logging
import os
import pathlib
import signal
import uuid
from typing import Any, List

from code_context_provider.core import PromptManager
from code_context_provider.servers.context.agent import (
    CodeSnippetFinder,
    QueryReformater,
    QueryReformaterResult,
)
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from starlette.requests import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class ServerConfig:
    def __init__(self) -> None:
        # Port configuration
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

    @staticmethod
    def _get_required_env(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value


# Initialize configuration
config = ServerConfig()


class TelemetryManager:
    def __init__(self, cfg: ServerConfig) -> None:
        self.cfg = cfg
        self.enabled = cfg.langfuse_enabled
        if self.enabled:
            self._setup()

    def _setup(self) -> None:
        langfuse_auth = base64.b64encode(
            f"{self.cfg.langfuse_public_key}:{self.cfg.langfuse_secret_key}".encode()
        ).decode()

        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {langfuse_auth}"
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"{self.cfg.langfuse_host}/api/public/otel"

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)

    def get_tracer(self, name: str) -> trace.Tracer:
        if self.enabled:
            return trace.get_tracer(name)
        else:
            # Return a no-op tracer when disabled
            return trace.get_tracer(name, tracer_provider=TracerProvider())


telemetry = TelemetryManager(config)
tracer = telemetry.get_tracer("context-provider-mcp")


def _set_span_attributes(
    span: trace.Span,
    input_data: dict,
    output_data: dict,
    session_id: str,
) -> None:
    """Attach common Langfuse attributes to the current span."""
    if not telemetry.enabled:
        return
    try:
        span.set_attribute("langfuse.session.id", session_id)
        span.set_attribute("langfuse.tags", ["context-provider-mcp"])
        span.set_attribute("input", json.dumps(input_data))
        span.set_attribute("output", json.dumps(output_data))
    except Exception as exc:
        logger.error(f"Error setting span attributes: {exc}")


server = FastMCP(sse_path="/contextprovider/sse", message_path="/contextprovider/messages/")

_shutdown_requested = False


def signal_handler(sig: int, frame: Any) -> None:
    """Handle termination signals for graceful shutdown."""
    global _shutdown_requested
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    _shutdown_requested = True


@tracer.start_as_current_span("ContextProviderMcp:agentic_search")
async def agentic_search(question: str) -> str:
    if _shutdown_requested:
        logger.info("Shutdown in progress, declining new requests")
        return ""
    try:
        request: Request = get_http_request()
        trace_id = str(request.headers.get("X-TRACE-ID", uuid.uuid4()))
    except Exception:
        trace_id = str(uuid.uuid4())

    span = trace.get_current_span()

    async with CodeSnippetFinder(trace_id=trace_id) as agent:
        result = await agent.run(question)

    _set_span_attributes(
        span,
        input_data={"question": question},
        output_data=result,
        session_id=trace_id,
    )
    return result


@tracer.start_as_current_span("ContextProviderMcp:refactor_question")
async def refactor_question(question: str) -> List[str]:
    if _shutdown_requested:
        logger.info("Shutdown in progress, declining new requests")
        return []

    try:
        request: Request = get_http_request()
        trace_id = str(request.headers.get("X-TRACE-ID", uuid.uuid4()))
    except Exception:
        trace_id = str(uuid.uuid4())

    span = trace.get_current_span()

    async with QueryReformater(trace_id=trace_id) as agent:
        result: QueryReformaterResult = await agent.run(question)

    _set_span_attributes(
        span,
        input_data={"question": question},
        output_data=result.model_dump(),
        session_id=trace_id,
    )

    return result.suggested_queries


def _register_tools() -> None:
    """Register MCP tools with the server."""
    # Load tool descriptions from prompts.yaml
    try:
        context_provider_prompts = PromptManager(
            file_path=pathlib.Path(__file__).parent.parent.parent / "prompts" / "prompts.yaml",
            section_path="context_provider",
        )
    except (FileNotFoundError, ValueError) as e:
        logger.warning(f"Could not load tool descriptions from prompts.yaml: {e}")

    tools = [
        agentic_search,
        refactor_question,
    ]

    for tool_func in tools:
        # Get description from prompts.yaml or use default
        description = context_provider_prompts.render_prompt(
            f"tools.{tool_func.__name__}.description",
        )

        server.add_tool(tool_func, tool_func.__name__, description)
        logger.info(f"Registered tool: {tool_func.__name__}")


async def _run_server() -> None:
    """Run the FastMCP server with both HTTP and SSE transports."""
    tasks = [
        server.run_http_async(
            transport="streamable-http",
            host="0.0.0.0",
            path="/contextprovider/mcp",
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
        logger.info("Starting Context Provider MCP server...")
        asyncio.run(_run_server())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt (CTRL+C)")
    except Exception as exc:
        logger.error(f"Server error: {exc}")
        raise
    finally:
        logger.info("Server has shut down.")
