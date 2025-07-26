import json
import logging
from typing import Any, Dict, Iterator, List
from urllib.parse import urlencode

import requests
from code_context_provider.backends.models import FormattedResult, Match
from code_context_provider.backends.search_protocol import SearchClientProtocol

logger = logging.getLogger(__name__)


class SSEParser:
    def __init__(self, response: requests.Response):
        self.response = response
        self.buffer = ""

    def __iter__(self) -> Iterator[Dict[str, str]]:
        try:
            for chunk in self.response.iter_content(chunk_size=8192, decode_unicode=False):
                if chunk:
                    try:
                        text = chunk.decode("utf-8", errors="replace")
                        self.buffer += text
                        yield from self._parse_buffer()
                    except Exception as e:
                        logger.warning(f"Error processing chunk: {e}")
        except Exception as e:
            logger.error(f"Error reading SSE stream: {e}")

        if self.buffer:
            yield from self._parse_buffer(final=True)

    def _parse_buffer(self, final: bool = False) -> Iterator[Dict[str, str]]:
        while True:
            event_end = self.buffer.find("\n\n")
            if event_end == -1:
                if final and self.buffer.strip():
                    event_data = self._parse_event(self.buffer)
                    if event_data:
                        yield event_data
                    self.buffer = ""
                break

            event_text = self.buffer[:event_end]
            self.buffer = self.buffer[event_end + 2 :]  # Skip the \n\n

            event_data = self._parse_event(event_text)
            if event_data:
                yield event_data

    def _parse_event(self, event_text: str) -> Dict[str, str]:
        event_type = None
        data_lines = []

        for line in event_text.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_lines.append(line[6:])

        if event_type and data_lines:
            # Join multi-line data fields
            data = "\n".join(data_lines)
            return {"event": event_type, "data": data}

        return {}


class SourcegraphClient(SearchClientProtocol):
    """Sourcegraph search client implementing the SearchClientProtocol interface."""

    def __init__(
        self,
        endpoint: str,
        token: str = "",
        max_line_length: int = 300,
        max_output_length: int = 100000,
    ):
        """Initialize Sourcegraph client.

        Args:
            endpoint: Sourcegraph API endpoint
            token: Authentication token (optional for public instances)
            max_line_length: Maximum length for a single line before truncation
            max_output_length: Maximum length for the entire output before truncation
        """
        if not endpoint:
            raise ValueError("Sourcegraph endpoint is required")

        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.max_line_length = max_line_length
        self.max_output_length = max_output_length

    def search(self, query: str, num: int) -> dict:
        """Execute a search query on Sourcegraph and return raw results.

        Args:
            query: The search query string
            num: Maximum number of results to return

        Returns:
            Raw search results as a dictionary
        """
        params = {
            "q": query,
            "t": "keyword",
            "v": "V3",
            "cm": "true",  # chunk matches
            "cl": "5",
            "display": str(num),  # Limit results on the server side
        }

        url = f"{self.endpoint}/.api/search/stream?{urlencode(params)}"
        headers = {
            "Accept": "text/event-stream",
        }

        # Only add Authorization header if token is provided
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        try:
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Sourcegraph search request failed: {e}")
            raise requests.exceptions.HTTPError(f"Search failed: {e}")

        matches = []
        filters = []
        progress = []
        alerts = []

        try:
            parser = SSEParser(response)
            for event in parser:
                event_type = event.get("event", "")
                data_str = event.get("data", "")

                if event_type == "done":
                    break

                if not data_str:
                    continue

                try:
                    data = json.loads(data_str)

                    if event_type == "matches" and isinstance(data, list):
                        matches.extend(data)
                    elif event_type == "filters" and isinstance(data, list):
                        filters = data  # Replace, don't extend
                    elif event_type == "progress":
                        progress.append(data)
                    elif event_type == "alert":
                        alerts.append(data)

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for event '{event_type}': {e}")
                    logger.debug(f"Problematic data: {data_str[:500]}...")

        finally:
            response.close()

        return {
            "matches": matches,
            "filters": filters,
            "progress": progress,
            "alerts": alerts,
        }

    def _truncate_line(self, line: str) -> str:
        """Truncate a line if it exceeds max_line_length."""
        if len(line) > self.max_line_length:
            return line[: self.max_line_length - 3] + "..."
        return line

    def _safe_get(self, obj: dict, *keys, default=None):
        """Safely get nested dictionary values."""
        current = obj
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return current

    def format_results(self, results: dict, num: int) -> List[FormattedResult]:
        """Format Sourcegraph search results into structured FormattedResult objects.

        Args:
            results: Raw search results from the search method
            num: Maximum number of results to format

        Returns:
            List of formatted results
        """
        formatted = []

        if not results or "matches" not in results:
            return formatted

        matches = results["matches"]
        if not matches:
            return formatted

        # Log any alerts
        for alert in results.get("alerts", []):
            severity = alert.get("severity", "info")
            message = alert.get("message", "")
            if severity == "error":
                logger.error(f"Search alert: {message}")
            elif severity == "warning":
                logger.warning(f"Search alert: {message}")
            else:
                logger.info(f"Search alert: {message}")

        # Group matches by file for content type, handle others individually
        file_matches: Dict[str, List[Dict[str, Any]]] = {}
        other_matches = []

        for match in matches[:num]:
            match_type = match.get("type", "")

            if match_type == "content":
                # Extract repository and file information
                repo = match.get("repository", "")
                file_path = match.get("path", "")
                key = f"{repo}:{file_path}"
                if key not in file_matches:
                    file_matches[key] = []
                file_matches[key].append(match)
            else:
                # Handle other types individually
                other_matches.append(match)

        # Process content matches
        for key, matches in file_matches.items():
            repo, file_path = key.split(":", 1)
            formatted_matches = []
            url = ""

            for match in matches:
                # Handle chunk matches if available
                chunk_matches = match.get("chunkMatches", [])
                if chunk_matches:
                    for chunk in chunk_matches:
                        content = chunk.get("content", "")
                        content_start = self._safe_get(chunk, "contentStart", default={})
                        line_number = content_start.get("line", 0) + 1  # 1-indexed
                        lines = content.split("\n")
                        truncated_lines = [self._truncate_line(line) for line in lines]
                        text = "\n".join(truncated_lines)
                        if not url:
                            url = f"https://{repo}/-/blob/HEAD/{file_path}"
                        formatted_matches.append(
                            Match(
                                line_number=line_number,
                                text=text,
                            )
                        )
                else:
                    # Fall back to line matches if no chunk matches
                    line_matches = match.get("lineMatches", [])
                    for line_match in line_matches:
                        line = line_match.get("line", "")
                        line_number = line_match.get("lineNumber", 0) + 1
                        text = self._truncate_line(line)
                        if not url:
                            url = f"https://{repo}/-/blob/HEAD/{file_path}"
                        formatted_matches.append(
                            Match(
                                line_number=line_number,
                                text=text,
                            )
                        )

            if formatted_matches:
                formatted.append(
                    FormattedResult(
                        filename=file_path,
                        repository=repo,
                        matches=formatted_matches,
                        url=url,
                    )
                )

        # Process other match types (keeping the same as before)
        for match in other_matches:
            match_type = match.get("type", "")
            repo = match.get("repository", "")

            if match_type == "symbol":
                # Handle symbol matches
                file_path = match.get("path", "")
                symbols = match.get("symbols", [])
                formatted_matches = []

                for symbol in symbols:
                    symbol_name = symbol.get("name", "")
                    container_name = symbol.get("containerName", "")
                    kind = symbol.get("kind", "")
                    line_number = symbol.get("line", 0)

                    # Create a text representation of the symbol
                    text_parts = []
                    if container_name:
                        text_parts.append(f"Container: {container_name}")
                    if symbol_name:
                        text_parts.append(f"Symbol: {symbol_name}")
                    if kind:
                        text_parts.append(f"Kind: {kind}")

                    text = " | ".join(text_parts) if text_parts else symbol_name

                    formatted_matches.append(
                        Match(
                            line_number=line_number,
                            text=text,
                        )
                    )

                if formatted_matches:
                    url = f"https://{repo}/-/blob/HEAD/{file_path}" if file_path else ""
                    formatted.append(
                        FormattedResult(
                            filename=file_path,
                            repository=repo,
                            matches=formatted_matches,
                            url=url,
                        )
                    )

            elif match_type == "repo":
                # Handle repository matches
                formatted_matches = []
                text = f"Repository: {repo}"
                formatted_matches.append(
                    Match(
                        line_number=0,
                        text=text,
                    )
                )

                formatted.append(
                    FormattedResult(
                        filename="",  # No specific file for repo matches
                        repository=repo,
                        matches=formatted_matches,
                        url=f"https://{repo}",
                    )
                )

            elif match_type in ["path", "commit", "diff"]:
                # Handle path, commit, and diff matches with basic information
                formatted_matches = []
                file_path = match.get("path", "")

                if match_type == "path":
                    text = f"Path: {file_path}"
                elif match_type == "commit":
                    commit_id = match.get("commit", "")
                    text = f"Commit: {commit_id}"
                    if file_path:
                        text += f" in {file_path}"
                elif match_type == "diff":
                    text = f"Diff in {file_path}" if file_path else "Diff"
                else:
                    text = f"Match type: {match_type}"

                formatted_matches.append(
                    Match(
                        line_number=0,  # No specific line for these types
                        text=text,
                    )
                )

                if formatted_matches:
                    url = f"https://{repo}/-/blob/HEAD/{file_path}" if file_path else f"https://{repo}"
                    formatted.append(
                        FormattedResult(
                            filename=file_path,
                            repository=repo,
                            matches=formatted_matches,
                            url=url,
                        )
                    )

        return formatted
