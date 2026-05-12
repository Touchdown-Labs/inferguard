#!/usr/bin/env python3
"""Check local HTML links in a built MkDocs/site directory."""

from __future__ import annotations

import argparse
import html.parser
import sys
from pathlib import Path
from urllib.parse import unquote, urldefrag, urlparse
from urllib.request import Request, urlopen


class LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "a" and attr_map.get("href"):
            self.links.append((tag, attr_map["href"]))
        elif tag == "link" and attr_map.get("href"):
            rel = set((attr_map.get("rel") or "").split())
            if rel & {"canonical", "icon", "stylesheet"}:
                self.links.append((tag, attr_map["href"]))
        elif tag in {"script", "img"} and attr_map.get("src"):
            self.links.append((tag, attr_map["src"]))


class AnchorParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value and name in {"id", "name"}:
                self.anchors.add(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site_dir", type=Path)
    parser.add_argument("--base-path", default="/inferguard/")
    parser.add_argument("--check-external", action="store_true")
    parser.add_argument("--ignore-host", action="append", default=[])
    args = parser.parse_args()

    site_dir = args.site_dir.resolve()
    if not site_dir.is_dir():
        raise SystemExit(f"site directory does not exist: {site_dir}")

    html_files = sorted(site_dir.rglob("*.html"))
    anchors = {path: parse_anchors(path) for path in html_files}
    failures: list[str] = []
    external_links: set[str] = set()

    for html_file in html_files:
        parser = LinkParser()
        parser.feed(html_file.read_text(encoding="utf-8", errors="replace"))
        for _tag, raw_url in parser.links:
            parsed = urlparse(raw_url)
            if parsed.scheme in {"http", "https", "mailto", "tel"}:
                if args.check_external and parsed.scheme in {"http", "https"}:
                    url_without_fragment, _fragment = urldefrag(raw_url)
                    if parsed.netloc not in set(args.ignore_host):
                        external_links.add(url_without_fragment)
                continue
            if raw_url.startswith(("javascript:", "data:")):
                continue

            url_without_fragment, fragment = urldefrag(raw_url)
            if not url_without_fragment and fragment:
                target = html_file
            else:
                target = resolve_target(site_dir, html_file, url_without_fragment, args.base_path)

            if target is None or not target.exists():
                failures.append(f"{html_file.relative_to(site_dir)} -> missing {raw_url}")
                continue
            if fragment and unquote(fragment) not in anchors.get(target, set()):
                failures.append(f"{html_file.relative_to(site_dir)} -> missing anchor {raw_url}")

    if args.check_external:
        failures.extend(check_external_links(external_links))

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"checked {len(html_files)} HTML files under {site_dir}")
    return 0


def parse_anchors(path: Path) -> set[str]:
    parser = AnchorParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.anchors


def resolve_target(site_dir: Path, page: Path, href: str, base_path: str) -> Path | None:
    parsed = urlparse(href)
    path = unquote(parsed.path)
    if path.startswith(base_path):
        rel = path.removeprefix(base_path)
        candidate = site_dir / rel
    elif path.startswith("/"):
        return None
    else:
        candidate = page.parent / path

    if candidate.is_dir():
        candidate = candidate / "index.html"
    elif candidate.suffix == "":
        candidate = candidate / "index.html"
    return candidate.resolve()


def check_external_links(urls: set[str]) -> list[str]:
    failures: list[str] = []
    for url in sorted(urls):
        status = fetch_status(url, method="HEAD")
        if status in {403, 405} or status >= 500:
            status = fetch_status(url, method="GET")
        if status == 429:
            print(f"external skipped rate-limited {status} {url}", file=sys.stderr)
            continue
        if status >= 400:
            failures.append(f"external {status} {url}")
    return failures


def fetch_status(url: str, *, method: str) -> int:
    request = Request(url, method=method, headers={"User-Agent": "InferGuard-docs-linkcheck/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            return int(response.status)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if isinstance(code, int):
            return code
        return 599


if __name__ == "__main__":
    raise SystemExit(main())
