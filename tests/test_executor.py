import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extractor


def testDiscoverTask2TextInputs(tmp_path):
    t1 = tmp_path / "names.txt"
    t2 = tmp_path / "requirements.txt"
    t1.write_text("NO DIFFERENCES IN REGARDS TO ELEMENT NAMES\n", encoding="utf-8")
    t2.write_text("NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS\n", encoding="utf-8")

    foundA, foundB = extractor.discoverTextInputs(str(tmp_path))

    assert foundA.name == "names.txt"
    assert foundB.name == "requirements.txt"


def testMapDifferencesToKubescapeControls(tmp_path):
    inA = tmp_path / "names.txt"
    inB = tmp_path / "requirements.txt"
    out = tmp_path / "controls.txt"
    inA.write_text("network policy\n", encoding="utf-8")
    inB.write_text("audit logging requirement mismatch\n", encoding="utf-8")

    controls = extractor.mapDifferencesToKubescapeControls(str(inA), str(inB), str(out))

    assert controls == ["C-0012", "C-0020"]
    assert out.read_text(encoding="utf-8").splitlines() == ["C-0012", "C-0020"]


def testExecuteKubescapeScan(tmp_path, monkeypatch):
    zip_file = tmp_path / "project-yamls.zip"
    controls = tmp_path / "controls.txt"
    zip_file.write_bytes(b"fake")
    controls.write_text("C-0012\n", encoding="utf-8")

    class DummyResult:
        def __init__(self):
            self.stdout = (
                '{"frameworks":[{"controls":[{"name":"Audit Logging","severity":"high","score":80,'
                '"failedResources":[{"name":"r1"}],"allResources":[{"name":"r1"},{"name":"r2"}]}]}]}'
            )

    def fake_run(cmd, check, capture_output, text):
        assert "--controls" in cmd
        return DummyResult()

    monkeypatch.setattr(extractor.subprocess, "run", fake_run)

    df = extractor.executeKubescapeScan(str(zip_file), str(controls), _kubescapeBinary="kubescape")

    assert list(df.columns) == [
        "FilePath",
        "Severity",
        "Control name",
        "Failed resources",
        "All Resources",
        "Compliance score",
    ]
    assert df.iloc[0]["Control name"] == "Audit Logging"
    assert df.iloc[0]["Failed resources"] == 1


def testGenerateScanCSV(tmp_path):
    df = extractor.dataframeFromRows(
        [
            {
                "FilePath": "project-yamls.zip",
                "Severity": "high",
                "Control name": "Audit Logging",
                "Failed resources": 2,
                "All Resources": 10,
                "Compliance score": 80,
            }
        ],
        [
            "FilePath",
            "Severity",
            "Control name",
            "Failed resources",
            "All Resources",
            "Compliance score",
        ],
    )
    out = tmp_path / "scan.csv"

    written = extractor.generateScanCSV(df, str(out))

    assert written == out
    csv_text = out.read_text(encoding="utf-8")
    assert "FilePath,Severity,Control name,Failed resources,All Resources,Compliance score" in csv_text
