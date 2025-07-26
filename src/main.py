import sys


def main():
    """Main entry point for the code-context-provider command."""
    if len(sys.argv) < 2:
        print("Usage: code-context-provider <search|context>")
        sys.exit(1)

    server_type = sys.argv[1]

    if server_type == "search":
        from code_context_provider.servers.search.server import main as search_main

        search_main()
    elif server_type == "context":
        from code_context_provider.servers.context.server import main as context_main

        context_main()
    else:
        print(f"Unknown server type: {server_type}")
        print("Usage: code-context-provider <search|context>")
        sys.exit(1)


if __name__ == "__main__":
    main()
