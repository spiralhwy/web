"""
Spiral HWY command line interface.

    spiral-hwy scrape [cinema] [music] [--workers N]
    spiral-hwy serve [--port N]
    spiral-hwy build
"""

import argparse
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent.parent

SCRAPERS = {
    "cinema": TOOLS_DIR / "cinema_scraper.py",
    "music": TOOLS_DIR / "music_scraper.py",
}


def run(cmd: list[str]) -> int:
    """
    Run a command from the project root, returning its exit code.
    """
    try:
        return subprocess.run(cmd, cwd=ROOT_DIR).returncode
    except KeyboardInterrupt:
        return 130


def scrape(args: argparse.Namespace) -> int:
    targets = args.targets or list(SCRAPERS)
    failed = []
    for target in dict.fromkeys(targets):
        print("=" * 10, f"{target} scraper", "=" * 10, flush=True)
        cmd = [sys.executable, str(SCRAPERS[target])]
        if target == "cinema" and args.workers is not None:
            cmd.append(f"workers={args.workers}")
        code = run(cmd)
        if code == 130:
            return code
        if code != 0:
            failed.append(target)

    if failed:
        print(f"Scraper(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def serve(args: argparse.Namespace) -> int:
    cmd = ["npx", "@11ty/eleventy", "--serve"]
    if args.port is not None:
        cmd.append(f"--port={args.port}")
    return run(cmd)


def build(args: argparse.Namespace) -> int:
    return run(["npx", "@11ty/eleventy"])


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="spiral-hwy", description="Spiral HWY scraping and site tools."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser(
        "scrape", help="Scrape listings into spiral_hwy/_data/ (default: all)"
    )
    p_scrape.add_argument(
        "targets",
        nargs="*",
        choices=list(SCRAPERS),
        help="Which scrapers to run (default: all)",
    )
    p_scrape.add_argument(
        "-w",
        "--workers",
        type=int,
        help="Parallel cinema scrapes (overrides configs/main.yaml)",
    )
    p_scrape.set_defaults(func=scrape)

    p_serve = sub.add_parser("serve", help="Serve the site locally with Eleventy")
    p_serve.add_argument("-p", "--port", type=int, help="Port (Eleventy default 8080)")
    p_serve.set_defaults(func=serve)

    p_build = sub.add_parser("build", help="Build the site into public/")
    p_build.set_defaults(func=build)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
