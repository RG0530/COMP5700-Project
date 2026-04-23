import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import types

import extractor
from helpers import extractTableOfContentsPages


def testLoadDocumentsValidatesAndLoads(monkeypatch, tmp_path):
    doc1 = tmp_path / "cis-r1.pdf"
    doc2 = tmp_path / "cis-r2.pdf"
    doc1.write_bytes(b"%PDF-1.4")
    doc2.write_bytes(b"%PDF-1.4")

    class DummyPage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class DummyPdfReader:
        def __init__(self, _):
            self.pages = [
                DummyPage("Cover"),
                DummyPage("Table of Contents\n1.1 Intro\n1.2 Scope"),
                DummyPage("2.1 Controls\n2.2 Logging"),
                DummyPage("Overview\nThis is the next section"),
                DummyPage("Body content"),
            ]

    monkeypatch.setitem(__import__("sys").modules, "pypdf", types.SimpleNamespace(PdfReader=DummyPdfReader))

    docs = extractor.loadDocuments(str(doc1), str(doc2))

    assert "cis-r1.pdf" in docs
    assert len(docs["cis-r1.pdf"]) == 1
    assert "Table of Contents" in docs["cis-r1.pdf"][0]


def testExtractTableOfContentsPagesLeavesNonCISDocsUnchanged():
    pages = ["P1", "P2", "P3"]
    assert extractTableOfContentsPages("random.pdf", pages) == pages


def testBuildZeroShotPrompt():
    docs = {"cis-r1.pdf": ["A"], "cis-r2.pdf": ["B"]}
    prompt = extractor.buildZeroShotPrompt("cis-r1.pdf", "cis-r2.pdf", docs)
    assert "Document A (cis-r1.pdf)" in prompt
    assert "Return ONLY valid JSON" in prompt


def testBuildFewShotPrompt():
    docs = {"cis-r1.pdf": ["A"], "cis-r2.pdf": ["B"]}
    prompt = extractor.buildFewShotPrompt("cis-r1.pdf", "cis-r2.pdf", docs)
    assert "Example Input" in prompt
    assert "Return ONLY valid JSON" in prompt


def testBuildChainOfThoughtPrompt():
    docs = {"cis-r1.pdf": ["A"], "cis-r2.pdf": ["B"]}
    prompt = extractor.buildChainOfThoughtPrompt("cis-r1.pdf", "cis-r2.pdf", docs)
    assert "Think silently and extract KDEs" in prompt
    assert "Return ONLY valid JSON" in prompt


def testRunKDEExtractionWithPrompts(tmp_path):
    prompts = [
        ("zero_shot", "prompt-z"),
        ("few_shot", "prompt-f"),
    ]

    def fakeLLM(messages):
        assert len(messages) == 2
        assert messages[0][0]["role"] == "system"
        assert messages[0][1]["role"] == "user"
        return [
            json.dumps({"element1": {"name": "audit_logging", "requirements": ["enable logs"]}}),
            json.dumps({"element1": {"name": "secrets_encryption", "requirements": ["encrypt secrets"]}}),
        ]

    outYAML = tmp_path / "cis-r1-cis-r2-kdes.yaml"
    result = extractor.runKDEExtractionWithPrompts(prompts, fakeLLM, str(outYAML))

    assert "zero_shot" in result
    assert "few_shot" in result
    assert outYAML.exists()

def testRunKDEExtractionWithPromptsHandlesNonJSONOutput(tmp_path):
    prompts = [
        ("zero_shot", "prompt-z"),
        ("few_shot", "prompt-f"),
    ]

    def fakeLLM(_messages):
        return [
            "I cannot comply with that request.",
            "",
        ]

    outYAML = tmp_path / "cis-r1-cis-r2-kdes.yaml"
    result = extractor.runKDEExtractionWithPrompts(prompts, fakeLLM, str(outYAML))

    assert result["zero_shot"] == {}
    assert result["few_shot"] == {}
    assert outYAML.exists()

def testRunKDEExtractionWithPromptsNormalizesLegacyShape(tmp_path):
    prompts = [("zero_shot", "prompt-z")]

    def fakeLLM(_messages):
        return [json.dumps({"element": "audit_logging", "value": "Enable audit Logs"})]

    outYAML = tmp_path / "legacy-kdes.yaml"
    result = extractor.runKDEExtractionWithPrompts(prompts, fakeLLM, str(outYAML))

    assert result["zero_shot"]["element1"]["name"] == "audit_logging"
    assert result["zero_shot"]["element1"]["requirements"] == ["Enable audit Logs"]

def testDumpLLMRunsToText(tmp_path):
    out_file = tmp_path / "llm-runs.txt"
    extractor.dumpLLMRunsToText(
        [
            {
                "llm_name": "Gemma-3-1B",
                "prompt_used": "Extract KDEs",
                "prompt_type": "zero_shot",
                "llm_output": "{\"element1\":{\"name\":\"x\",\"requirements\":[\"y\"]}}",
            }
        ],
        str(out_file),
    )

    text = out_file.read_text(encoding="utf-8")
    assert "*LLM Name*" in text
    assert "Gemma-3-1B" in text

    
def testExtractRequirementCandidatesParsesAndDeduplicates():
    pages = [
        "3.2.1 Ensure that the Anonymous Auth is Not Enabled (Automated)\n"
        "3.2.1 Ensure that the Anonymous Auth is Not Enabled (Automated)\n"
        "4.4.2 Consider external secret storage (Manual)"
    ]

    candidates = extractor.extractRequirementCandidates(pages)

    assert candidates == [
        "3.2.1 Ensure that the Anonymous Auth is Not Enabled (Automated)",
        "4.4.2 Consider external secret storage (Manual)",
    ]


def testExtractRequirementCandidatesBuildsHierarchicalPathsAndFiltersNoise():
    pages = [
        "Table of Contents",
        "2 Control Plane Configuration ............................................................. 13",
        "2.1 Logging ........................................................................................... 14",
        "2.1.1 Enable audit Logs (Manual) ............................................................ 15",
        "Page 3",
        "Appendix: Summary Table .................................................................... 151",
        "3 Worker Nodes .................................................................................... 17",
        "3.1 Worker Node Configuration Files .................................................... 19",
        "3.1.1 Ensure that the kubeconfig file permissions are set to 644 or more restrictive (Manual) ... 20",
    ]

    candidates = extractor.extractRequirementCandidates(pages)

    assert candidates == [
        "2 Control Plane Configuration",
        "2 Control Plane Configuration -> 2.1 Logging",
        "2 Control Plane Configuration -> 2.1 Logging -> 2.1.1 Enable audit Logs (Manual)",
        "3 Worker Nodes",
        "3 Worker Nodes -> 3.1 Worker Node Configuration Files",
        (
            "3 Worker Nodes -> 3.1 Worker Node Configuration Files -> "
            "3.1.1 Ensure that the kubeconfig file permissions are set to 644 or more restrictive (Manual)"
        ),
    ]
