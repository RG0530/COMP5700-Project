from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from extractor import buildChainOfThoughtPrompt, buildFewShotPrompt, buildZeroShotPrompt


# Helper function to convert Python objects to a YAML-formatted string.
def toYAML(_obj: object, _indent: int = 0) -> str:
    space = "  " * _indent
    if isinstance(_obj, dict):
        lines: List[str] = []
        for k, v in _obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{space}{k}:")
                lines.append(toYAML(v, _indent + 1))
            else:
                lines.append(f"{space}{k}: {v}")
        return "\n".join(lines)
    if isinstance(_obj, list):
        lines = []
        for item in _obj:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.append(toYAML(item, _indent + 1))
            else:
                lines.append(f"{space}- {item}")
        return "\n".join(lines)
    return f"{space}{_obj}"


# Helper function to extract only the Table of Contents section from CIS benchmark PDFs.
def extractTableOfContentsPages(_docPath: str, _pages: List[str]) -> List[str]:
    docName = Path(_docPath).name.lower()
    cisDocs = {"cis-r1.pdf", "cis-r2.pdf", "cis-r3.pdf", "cis-r4.pdf"}
    if docName not in cisDocs:
        return _pages

    pageWindow = _pages[1:5]
    tocText = "\n".join(pageWindow).strip()
    if not tocText:
        return []

    tocHeader = "table of contents"
    nextPageText = "All CIS Benchmarks"
    tocLower = tocText.lower()
    tocStart = tocLower.find(tocHeader)
    if tocStart == -1:
        return []

    overviewStart = tocLower.find(nextPageText, tocStart + len(tocHeader))
    if overviewStart == -1:
        extracted = tocText[tocStart:].strip()
    else:
        extracted = tocText[tocStart:overviewStart].strip()
    return [extracted] if extracted else []
