"""Sourcegraph content fetcher implementation."""

import json
from typing import Any, List, Optional
from urllib.parse import urljoin

import requests

from backends.content_fetcher import MAX_FILE_SIZE, AbstractContentFetcher


class SourcegraphContentFetcher(AbstractContentFetcher):
    """Fetches content from Sourcegraph repositories."""

    def __init__(self, endpoint: str, token: str = ""):
        """Initialize Sourcegraph content fetcher.

        Args:
            endpoint: Sourcegraph API endpoint
            token: Authentication token (optional for public instances)

        Raises:
            ValueError: If endpoint is not provided
        """
        if not endpoint:
            raise ValueError("Sourcegraph endpoint is required")

        self.endpoint = endpoint
        self.token = token

        self.src_url = urljoin(self.endpoint, ".api/graphql")

    def get_content(self, repository: str, path: str = "", depth: int = 2, ref: str = "HEAD") -> str:
        """Get content from Sourcegraph repository.

        Args:
            repository: Repository path (e.g., "github.com/example/project" or "gitlab.com/org/repo")
            path: File or directory path (e.g., "src/main.py" or "src/api/handlers.go")
            depth: Tree depth for directory listings
            ref: Git reference (branch, tag, or commit SHA)

        Returns:
            File content if path is a file, directory tree if path is a directory

        Raises:
            ValueError: If repository or path does not exist
        """
        # Clean repository path for Sourcegraph
        repository = self._clean_repository_path(repository)

        if not path:
            try:
                tree = self._get_sourcegraph_tree(repository, ".", depth)
                return tree
            except ValueError:
                raise ValueError("invalid arguments the given path or repository does not exist")

        # Try file first, then directory
        try:
            file_content = self._get_sourcegraph_file_content(repository, path)
            if file_content:
                return file_content
        except ValueError:
            pass  # File not found, try as directory

        try:
            tree = self._get_sourcegraph_tree(repository, path, depth)
            return tree
        except ValueError:
            # Only raise "not found" if both file and directory lookups fail
            raise ValueError("invalid arguments the given path or repository does not exist")

    def _get_sourcegraph_file_content(self, repo_name: str, path: str) -> Optional[str]:
        """Get file content from Sourcegraph."""
        query = """
        query GetFileContent($name: String!, $path: String!) {
            repository(name: $name) {
                commit(rev: "HEAD") {
                    file(path: $path) {
                        path
                        name
                        content
                        totalLines
                        binary
                        contentType
                        richHTML
                        languages
                    }
                }
            }
        }
        """

        variables = {"name": repo_name, "path": path}
        headers = {
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        payload = {"query": query, "variables": variables}

        try:
            response = requests.post(self.src_url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()

            if "errors" in data:
                raise ValueError("invalid arguments the given path or repository does not exist")

            content = self._safe_get(data, ["data", "repository", "commit", "file", "content"], default=None)

            if content and len(content) > MAX_FILE_SIZE:
                total_lines = self._safe_get(
                    data, ["data", "repository", "commit", "file", "totalLines"], default="unknown"
                )
                truncated_content = content[:MAX_FILE_SIZE]
                # Find last complete line
                last_newline = truncated_content.rfind("\n")
                if last_newline > 0:
                    truncated_content = truncated_content[:last_newline]

                return (
                    f"{truncated_content}\n\n"
                    f"[FILE TRUNCATED: File too large ({len(content):,} chars, {total_lines} lines). "
                    f"Showing first {len(truncated_content):,} chars]"
                )

            return content

        except (requests.exceptions.RequestException, json.JSONDecodeError):
            raise ValueError("invalid arguments the given path or repository does not exist")

    def _get_sourcegraph_tree(self, repo_name: str, path: str, depth: int) -> str:
        """Get directory tree from Sourcegraph."""
        query = """
        query GetRepositoryTree($name: String!, $path: String = ".") {
            repository(name: $name) {
                name
                commit(rev: "HEAD") {
                    message
                    tree(path: $path) {
                        entries {
                            name
                            isDirectory
                            ... on GitTree {
                                entries {
                                    name
                                    isDirectory
                                }
                            }
                        }
                    }
                    languages
                }
            }
        }
        """

        variables = {"name": repo_name, "path": path}
        headers = {
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        payload = {"query": query, "variables": variables}

        try:
            response = requests.post(self.src_url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()

            if "errors" in data:
                raise ValueError("invalid arguments the given path or repository does not exist")

            # Check if repository exists
            repository = self._safe_get(data, ["data", "repository"], default=None)
            if repository is None:
                raise ValueError("invalid arguments the given path or repository does not exist")

            tree_data = self._safe_get(data, ["data", "repository", "commit", "tree"], default=None)
            if tree_data is None:
                raise ValueError("invalid arguments the given path or repository does not exist")

            entries = self._safe_get(tree_data, ["entries"], default=[])

            return self._format_sourcegraph_tree(entries, depth, 0)

        except (requests.exceptions.RequestException, json.JSONDecodeError):
            raise ValueError("invalid arguments the given path or repository does not exist")

    def _format_sourcegraph_tree(self, entries: list, max_depth: int, current_depth: int) -> str:
        """Format Sourcegraph tree entries into a string representation."""
        if current_depth >= max_depth:
            return ""

        output_lines = []
        for entry in sorted(entries, key=lambda x: x.get("name", "")):
            indent = "  " * current_depth
            name = entry.get("name", "")
            is_dir = entry.get("isDirectory", False)

            if is_dir:
                name += "/"

            output_lines.append(f"{indent}{name}")

            # If it's a directory and has nested entries, process them recursively
            if is_dir and "entries" in entry and entry["entries"] and current_depth < max_depth - 1:
                nested_output = self._format_sourcegraph_tree(entry["entries"], max_depth, current_depth + 1)
                if nested_output:
                    output_lines.append(nested_output)

        return "\n".join(output_lines)

    def _clean_repository_path(self, repository: str) -> str:
        """Clean repository path for Sourcegraph."""
        # Remove protocol prefixes
        repository = repository.replace("https://", "").replace("http://", "")
        return repository

    def _safe_get(self, data: dict, keys: List[str], default: Any = None) -> Any:
        result = data
        for key in keys:
            if not isinstance(result, dict):
                return default
            if key in result:
                result = result[key]
            else:
                return default
        return result
