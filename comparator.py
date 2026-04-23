from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set, Tuple


# Helper function to automatically discover the two Task-1 YAML files from a specified directory, ensuring that exactly two YAML files are found and returning their paths.
def discoverYamlInputs(_outputDir: str = ".") -> Tuple[Path, Path]:
    base = Path(_outputDir)
    if not base.exists() or not base.is_dir():
        raise ValueError(f"Task-1 output directory is invalid: {_outputDir}")

    candidates = sorted([*base.glob("*.yaml"), *base.glob("*.yml")])
    if len(candidates) != 2:
        raise ValueError(
            "Expected exactly two Task-1 YAML files, "
            f"but found {len(candidates)} in {base.resolve()}"
        )
    return candidates[0], candidates[1]


# Helper function to normalize nested YAML payloads into a flat dictionary mapping KDE names to their associated requirements, recursively walking through the YAML structure.
def flattenKDEs(_yamlPayload: object) -> Dict[str, Set[str]]:
    flattened: Dict[str, Set[str]] = {}

    def walk(_node: object) -> None:
        if isinstance(_node, dict):
            if "name" in _node and isinstance(_node["name"], str):
                name = _node["name"].strip()
                if not name:
                    return
                reqs = _node.get("requirements", [])
                req_set = {
                    str(req).strip()
                    for req in reqs
                    if isinstance(req, (str, int, float)) and str(req).strip()
                } if isinstance(reqs, list) else set()
                flattened.setdefault(name, set()).update(req_set)
            for value in _node.values():
                walk(value)
        elif isinstance(_node, list):
            for item in _node:
                walk(item)

    walk(_yamlPayload)
    return flattened


# Helper function to load KDEs from a YAML file, first attempting to parse it as YAML and flatten it, and if that fails, falling back to parsing it as JSON (since JSON is valid YAML) and flattening the result.
def loadKDEsFromYAML(_yamlPath: Path) -> Dict[str, Set[str]]:
    text = _yamlPath.read_text(encoding="utf-8")
    flattened: Dict[str, Set[str]] = {}
    lines = text.splitlines()

    # Iterates over the lines of the YAML file, looking for "name:" keys to identify KDE names and then scanning for associated "requirements:" lists, while keeping track of indentation levels to handle nested structures appropriately.
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            idx += 1
            continue

        if "name:" not in stripped:
            idx += 1
            continue

        name_indent = len(line) - len(line.lstrip(" "))
        _, raw_name = stripped.split("name:", 1)
        name = raw_name.strip().strip("'\"")
        if not name:
            idx += 1
            continue

        reqs: Set[str] = set()
        scan = idx + 1
        while scan < len(lines):
            current = lines[scan]
            current_stripped = current.strip()
            current_indent = len(current) - len(current.lstrip(" "))

            if current_stripped.startswith("name:") and current_indent <= name_indent:
                break

            if current_stripped.startswith("requirements:"):
                req_indent = current_indent
                scan += 1
                while scan < len(lines):
                    req_line = lines[scan]
                    req_stripped = req_line.strip()
                    req_line_indent = len(req_line) - len(req_line.lstrip(" "))
                    if req_line_indent <= req_indent:
                        scan -= 1
                        break
                    if req_stripped.startswith("- "):
                        reqs.add(req_stripped[2:].strip().strip("'\""))
                    scan += 1
            scan += 1

        flattened.setdefault(name, set()).update({req for req in reqs if req})
        idx += 1

    if flattened:
        return flattened

    try:
        payload = json.loads(text)
    except Exception as exc:
        raise ValueError(f"Unable to parse YAML file: {_yamlPath}") from exc
    return flattenKDEs(payload)


# Helper function to compare KDE names between two YAML files, using the flattenKDEs function to extract KDE names.
def compareKDENames(_yamlFileA: str, _yamlFileB: str, _outputTextPath: str) -> List[str]:
    pathA = Path(_yamlFileA)
    pathB = Path(_yamlFileB)
    kdesA = loadKDEsFromYAML(pathA)
    kdesB = loadKDEsFromYAML(pathB)

    namesA = set(kdesA.keys())
    namesB = set(kdesB.keys())
    diffs = sorted(namesA.symmetric_difference(namesB))

    out = Path(_outputTextPath)
    out.parent.mkdir(parents=True, exist_ok=True)
    if diffs:
        out.write_text("\n".join(diffs) + "\n", encoding="utf-8")
    else:
        out.write_text("NO DIFFERENCES IN REGARDS TO ELEMENT NAMES\n", encoding="utf-8")
    return diffs


# Helper function to compare KDE names and requirements.
def compareKDENamesAndRequirements(_yamlFileA: str, _yamlFileB: str, _outputTextPath: str) -> List[Tuple[str, str, str, str]]:
    pathA = Path(_yamlFileA)
    pathB = Path(_yamlFileB)
    kdesA = loadKDEsFromYAML(pathA)
    kdesB = loadKDEsFromYAML(pathB)

    labelAbsentA = f"ABSENT-IN-{pathA.name}"
    labelPresentA = f"PRESENT-IN-{pathA.name}"
    labelAbsentB = f"ABSENT-IN-{pathB.name}"
    labelPresentB = f"PRESENT-IN-{pathB.name}"

    # Iterates over the union of KDE names from both files, checking for presence in each file and comparing associated requirements, while building a list of differences with clear labels indicating presence or absence in each file.
    rows: List[Tuple[str, str, str, str]] = []
    allNames = sorted(set(kdesA.keys()).union(set(kdesB.keys())))
    for name in allNames:
        inA = name in kdesA
        inB = name in kdesB
        if inA and not inB:
            rows.append((name, labelAbsentB, labelPresentA, "NA"))
            continue
        if inB and not inA:
            rows.append((name, labelAbsentA, labelPresentB, "NA"))
            continue

        reqsA = kdesA[name]
        reqsB = kdesB[name]
        for req in sorted(reqsA - reqsB):
            rows.append((name, labelAbsentB, labelPresentA, req))
        for req in sorted(reqsB - reqsA):
            rows.append((name, labelAbsentA, labelPresentB, req))

    # Writes the differences to the specified output text path, with clear formatting and encoding, and returns the list of differences.
    out = Path(_outputTextPath)
    out.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        lines = [",".join(item) for item in rows]
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        out.write_text("NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS\n", encoding="utf-8")

    return rows
