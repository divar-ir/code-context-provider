import asyncio
import sys


def print_help():
    print("Usage: python main.py <command> [options]")
    print("\nAvailable commands:")
    print("  search     - Start the search server")
    print("  context    - Start the context server")
    print("  evaluate   - Run evaluation experiments")
    print("  agent      - Run the code agent interactively")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    command = sys.argv[1]

    match command:
        case "search":
            from servers.search.server import main as search_main

            search_main()
        case "context":
            from servers.context.server import main as context_main

            context_main()

        case "evaluate":
            from evaluator.evaluate import async_main as evaluate_main

            asyncio.run(evaluate_main())

        case "agent":
            from evaluator.agent import async_main as agent_main

            asyncio.run(agent_main())

        case _:
            print(f"Unknown command: {command}")
            print_help()
            sys.exit(1)
