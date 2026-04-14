#!/usr/bin/env python3
"""Multi-Agent Research Assistant — CLI & API entry point.

Usage:
    # Run as CLI (single question)
    python main.py research "Your research question here"

    # Run both default example prompts
    python main.py research

    # Start the API server
    python main.py serve
    python main.py serve --port 8080
"""

from __future__ import annotations

import argparse
import logging
import sys


def cmd_research(args: argparse.Namespace) -> None:
    """Run the research pipeline from the command line."""
    from app.core.pipeline import run_pipeline

    EXAMPLE_PROMPTS = [
        "What are the main trade-offs between CNNs and Vision Transformers for medical imaging?",
        "What are the opportunities and risks of adopting AI in higher education institutions?",
    ]

    if args.question:
        question = " ".join(args.question)
        state = run_pipeline(question)
        print("\n" + "=" * 70)
        print(state.summary())
        print("=" * 70)
    else:
        print("No question provided. Running both example prompts.\n")
        for i, question in enumerate(EXAMPLE_PROMPTS, 1):
            print(f"\n{'#' * 70}")
            print(f"  PROMPT {i} of {len(EXAMPLE_PROMPTS)}")
            print(f"{'#' * 70}\n")
            run_pipeline(question, output_dir=f"output/prompt_{i}")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI server."""
    import uvicorn
    from app.core.config import API_HOST, API_PORT

    host = args.host or API_HOST
    port = args.port or API_PORT

    print(f"\n🚀 Starting Research Assistant API at http://{host}:{port}")
    print(f"   Docs:    http://{host}:{port}/docs")
    print(f"   Health:  http://{host}:{port}/api/health\n")

    uvicorn.run("app.api.app:app", host=host, port=port, reload=args.reload)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Multi-Agent Research Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # research sub-command
    research_parser = subparsers.add_parser("research", help="Run a research pipeline")
    research_parser.add_argument("question", nargs="*", help="Research question (omit for defaults)")

    # serve sub-command
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", type=str, default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()

    if args.command == "research":
        cmd_research(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
