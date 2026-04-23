from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import json
import subprocess


# Helper function to automatically discover the two Task-2 text files from a specified directory, ensuring that exactly two text files are found and returning their paths.
def discoverTextInputs(_outputDir: str = ".") -> Tuple[Path, Path]:
    base = Path(_outputDir)
    if not base.exists() or not base.is_dir():
        raise ValueError(f"Task-2 output directory is invalid: {_outputDir}")

    candidates = sorted(base.glob("*.txt"))
    if len(candidates) != 2:
        raise ValueError(
            "Expected exactly two Task-2 TEXT files, "
            f"but found {len(candidates)} in {base.resolve()}"
        )
    return candidates[0], candidates[1]


# Helper function to map the differences found in Task-2 to Kubescape controls, using keyword matching to associate differences with specific controls, and writing the resulting control list to a text file for Task-3 input.
def mapDifferencesToKubescapeControls(_textFileA: str, _textFileB: str, _outputTextPath: str, _controlMapper: Optional[Dict[str, str]] = None) -> List[str]:
    pathA = Path(_textFileA)
    pathB = Path(_textFileB)
    if not pathA.exists() or not pathB.exists():
        raise ValueError("Both Task-2 TEXT files must exist.")

    linesA = [line.strip() for line in pathA.read_text(encoding="utf-8").splitlines() if line.strip()]
    linesB = [line.strip() for line in pathB.read_text(encoding="utf-8").splitlines() if line.strip()]
    allLines = linesA + linesB

    hasDifferences = any(not line.upper().startswith("NO DIFFERENCES") for line in allLines)
    outputPath = Path(_outputTextPath)
    outputPath.parent.mkdir(parents=True, exist_ok=True)

    if not hasDifferences:
        outputPath.write_text("NO DIFFERENCES FOUND\n", encoding="utf-8")
        return []

    defaultMapper = {
        "audit": "C-0012",
        "logging": "C-0012",
        "secret": "C-0038",
        "encryption": "C-0038",
        "network": "C-0020",
        "image": "C-0044",
        "privilege": "C-0057",
        "resource": "C-0061",
        "rbac": "C-0016",
    }
    mapper = _controlMapper or defaultMapper

    controls: Set[str] = set()
    for line in allLines:
        lower = line.lower()
        for token, control in mapper.items():
            if token in lower:
                controls.add(control)

    if not controls:
        controls.add("C-0012")

    controlsList = sorted(controls)
    outputPath.write_text("\n".join(controlsList) + "\n", encoding="utf-8")
    return controlsList


# Helper function to create a pandas DataFrame from rows and columns for scan results.
def dataframeFromRows(_rows: List[Dict[str, object]], _columns: List[str]) -> Any:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pandas is required.") from exc

    return pd.DataFrame(_rows, columns=_columns)


# Helper function to execute a Kubescape scan using the provided project YAML ZIP file and controls text file, constructing the appropriate command-line arguments, running the scan, and parsing the JSON output to create a DataFrame with the relevant control results.
def executeKubescapeScan(_projectYAMLsZip: str, _controlsTextPath: str, _kubescapeBinary: str = "kubescape") -> Any:
    zipPath = Path(_projectYAMLsZip)
    if not zipPath.exists():
        raise ValueError(f"Project ZIP does not exist: {_projectYAMLsZip}")

    controlsFile = Path(_controlsTextPath)
    if not controlsFile.exists():
        raise ValueError(f"Controls TEXT file does not exist: {_controlsTextPath}")

    controlLines = [line.strip() for line in controlsFile.read_text(encoding="utf-8").splitlines() if line.strip()]
    runAllControls = len(controlLines) == 1 and controlLines[0].upper() == "NO DIFFERENCES FOUND"

    cmd = [_kubescapeBinary, "scan", str(zipPath), "--format", "json"]
    if not runAllControls:
        cmd.extend(["--controls", ",".join(controlLines)])

    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(proc.stdout or "{}")

    # Iterates over the frameworks and controls in the Kubescape JSON output, extracting relevant information such as severity, control name, failed resources, all resources, and compliance score, and building a list of rows for the DataFrame.
    rows: List[Dict[str, object]] = []
    frameworks = payload.get("frameworks", [])
    for fw in frameworks:
        for control in fw.get("controls", []):
            failed = control.get("failedResources", []) or []
            all_resources = control.get("allResources", []) or []
            rows.append(
                {
                    "FilePath": str(zipPath),
                    "Severity": control.get("severity", ""),
                    "Control name": control.get("name", ""),
                    "Failed resources": len(failed),
                    "All Resources": len(all_resources),
                    "Compliance score": control.get("score", ""),
                }
            )

    columns = [
        "FilePath",
        "Severity",
        "Control name",
        "Failed resources",
        "All Resources",
        "Compliance score",
    ]

    return dataframeFromRows(rows, columns)


# Helper function to generate a CSV file from the Kubescape scan results DataFrame, ensuring that the required columns are present and writing the specified columns to the output CSV file.
def generateScanCSV(_scanDF: Any, _outputCSVPath: str) -> Path:
    required_columns = [
        "FilePath",
        "Severity",
        "Control name",
        "Failed resources",
        "All Resources",
        "Compliance score",
    ]
    missing = [col for col in required_columns if col not in _scanDF.columns]
    if missing:
        raise ValueError(f"Scan dataframe is missing required columns: {missing}")

    output_path = Path(_outputCSVPath)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _scanDF[required_columns].to_csv(output_path, index=False)
    return output_path
