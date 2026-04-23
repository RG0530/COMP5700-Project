import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extractor


def testDiscoverTask1YAMLInputs(tmp_path):
    y1 = tmp_path / "task1-a.yaml"
    y2 = tmp_path / "task1-b.yml"
    y1.write_text("element1:\n  name: logging\n  requirements:\n    - req1\n", encoding="utf-8")
    y2.write_text("element1:\n  name: encryption\n  requirements:\n    - req2\n", encoding="utf-8")

    foundA, foundB = extractor.discoverYamlInputs(str(tmp_path))

    assert foundA.name == "task1-a.yaml"
    assert foundB.name == "task1-b.yml"


def testCompareKDENamesOutputsText(tmp_path):
    y1 = tmp_path / "a.yaml"
    y2 = tmp_path / "b.yaml"
    out = tmp_path / "name-diff.txt"
    y1.write_text("k1:\n  name: logging\n  requirements:\n    - req1\n", encoding="utf-8")
    y2.write_text("k2:\n  name: encryption\n  requirements:\n    - req2\n", encoding="utf-8")

    diffs = extractor.compareKDENames(str(y1), str(y2), str(out))

    assert diffs == ["encryption", "logging"]
    assert out.read_text(encoding="utf-8").splitlines() == ["encryption", "logging"]


def testCompareKDENamesAndRequirementsOutputsTupleRows(tmp_path):
    y1 = tmp_path / "a.yaml"
    y2 = tmp_path / "b.yaml"
    out = tmp_path / "req-diff.txt"
    y1.write_text(
        "k1:\n  name: logging\n  requirements:\n    - req1\n    - req2\n",
        encoding="utf-8",
    )
    y2.write_text(
        "k1:\n  name: logging\n  requirements:\n    - req2\nk2:\n  name: backup\n  requirements:\n    - req9\n",
        encoding="utf-8",
    )

    rows = extractor.compareKDENamesAndRequirements(str(y1), str(y2), str(out))

    assert ("backup", "ABSENT-IN-a.yaml", "PRESENT-IN-b.yaml", "NA") in rows
    assert ("logging", "ABSENT-IN-b.yaml", "PRESENT-IN-a.yaml", "req1") in rows
    textRows = out.read_text(encoding="utf-8").splitlines()
    assert "backup,ABSENT-IN-a.yaml,PRESENT-IN-b.yaml,NA" in textRows
    assert "logging,ABSENT-IN-b.yaml,PRESENT-IN-a.yaml,req1" in textRows
