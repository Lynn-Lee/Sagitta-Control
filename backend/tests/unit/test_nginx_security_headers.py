from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT.parent / "deploy" / "nginx.conf"


def _location_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for match in re.finditer(r"(?m)^\s*location\s+([^{]+)\{", text):
        start = match.end()
        depth = 1
        pos = start
        while pos < len(text) and depth:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
            pos += 1
        blocks.append((match.group(1).strip(), text[start : pos - 1]))
    return blocks


def test_nginx_csp_header_limits_script_and_frame_sources() -> None:
    conf = NGINX_CONF.read_text()

    csp_lines = re.findall(r'add_header\s+Content-Security-Policy\s+"([^"]+)"\s+always;', conf)
    assert csp_lines
    assert all("script-src 'self'" in line for line in csp_lines)
    assert all("frame-ancestors 'none'" in line for line in csp_lines)
    assert all("object-src 'none'" in line for line in csp_lines)


def test_nginx_csp_header_is_redeclared_in_locations_with_other_headers() -> None:
    conf = NGINX_CONF.read_text()

    locations_missing_csp = [
        name
        for name, block in _location_blocks(conf)
        if "add_header " in block and "add_header Content-Security-Policy" not in block
    ]

    assert locations_missing_csp == []
