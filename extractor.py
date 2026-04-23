from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Iterable, List, Tuple

import json

import subprocess
import re

# Function to build a zero-shot prompt for KDE extraction.
def buildZeroShotPrompt(_doc1Name: str, _doc2Name: str, _docsText: Dict[str, List[str]]) -> str:
    sharedContext = buildSharedDocumentContext(_doc1Name, _doc2Name, _docsText)
    return (
        "Extract Kubernetes security KDEs from both documents. "
        "A KDE can map to multiple requirements and should be normalized to snake_case names. "
        f"{buildJSONSchemaInstruction()}\n\n"
        f"{sharedContext}"
    )


# Function to build a few-shot prompt for KDE extraction.
def buildFewShotPrompt(_doc1Name: str, _doc2Name: str, _docsText: Dict[str, List[str]]) -> str:
    sharedContext = buildSharedDocumentContext(_doc1Name, _doc2Name, _docsText)
    return (
        "You extract KDEs from requirements documents.\n"
        "Example Input: 2.1.1 Enable audit Logs; 4.4.2 Consider external secret storage.\n"
        "Example Output: "
        "{\"element1\":{\"name\":\"audit_logging\",\"requirements\":[\"Enable audit Logs\"]},"
        "\"element2\":{\"name\":\"external_secret_storage\",\"requirements\":[\"Consider external secret storage\"]}}\n\n"
        f"{buildJSONSchemaInstruction()}\n\n"
        f"{sharedContext}"
    )


# Function to build a chain-of-thought prompt for KDE extraction.
def buildChainOfThoughtPrompt(_doc1Name: str, _doc2Name: str, _docsText: Dict[str, List[str]]) -> str:
    sharedContext = buildSharedDocumentContext(_doc1Name, _doc2Name, _docsText)
    return (
        "Think silently and extract KDEs that represent configuration and policy controls. "
        "Do not output explanation. "
        f"{buildJSONSchemaInstruction()}\n\n"
        f"{sharedContext}"
    )


# Function to load and validate two PDF documents.
def loadDocuments(_doc1Path: str, _doc2Path: str) -> Dict[str, List[str]]:
    from helpers import extractTableOfContentsPages

    paths = [Path(_doc1Path), Path(_doc2Path)]
    for p in paths:
        if not p.exists():
            raise ValueError(f"Document does not exist: {p}")
        if p.suffix.lower() != ".pdf":
            raise ValueError(f"Document must be a PDF: {p}")

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ValueError("pypdf is required to read PDF files.") from exc

    extracted: Dict[str, List[str]] = {}
    for p in paths:
        try:
            reader = PdfReader(str(p))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except Exception as exc:  # pragma: no cover - depends on malformed PDFs
            raise ValueError(f"Unable to read PDF document: {p}") from exc

        pages = extractTableOfContentsPages(str(p), pages)
        if not any(pages):
            raise ValueError(f"No text found in document: {p}")
        extracted[p.name] = pages

    return extracted


# Function to run KDE extraction with prompts and write the YAML output.
def runKDEExtractionWithPrompts(
    _prompts: Iterable[Tuple[str, str]],
    _runGemma31b: Callable[[List[List[Dict[str, object]]]], List[str]],
    _outputYAMLPath: str,
) -> Dict[str, Dict[str, object]]:
    from helpers import toYAML

    def _parseJSONFromLLMOutput(_raw: str) -> Dict[str, object]:
        rawText = _raw.strip()
        if not rawText:
            raise ValueError("LLM returned empty output; expected a JSON object.")

        # Try direct JSON parsing first.
        try:
            parsed = json.loads(rawText)
            if not isinstance(parsed, dict):
                raise ValueError("LLM output must be a JSON object at the top level.")
            return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: extract first JSON object from mixed model output.
        match = re.search(r"\{[\s\S]*\}", rawText)
        if not match:
            raise ValueError("LLM output did not contain a JSON object.")

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("LLM output must be a JSON object at the top level.")
        return parsed

    def normalizeSchema(_parsed: Dict[str, object]) -> Dict[str, object]:
        if "element" in _parsed and "value" in _parsed:
            name = str(_parsed.get("element", "")).strip()
            value = str(_parsed.get("value", "")).strip()
            if name:
                reqs = [value] if value else []
                return {"element1": {"name": name, "requirements": reqs}}
            return {}

        normalized: Dict[str, object] = {}
        idx = 1
        for _, value in _parsed.items():
            if not isinstance(value, dict):
                continue
            name = value.get("name")
            requirements = value.get("requirements", [])
            if not isinstance(name, str) or not name.strip():
                continue
            reqList = [str(req).strip() for req in requirements if str(req).strip()] if isinstance(requirements, list) else []
            normalized[f"element{idx}"] = {"name": name.strip(), "requirements": reqList}
            idx += 1
        return normalized

    promptList = list(_prompts)
    messages: List[List[Dict[str, object]]] = [
        [
            {
                "role": "system",
                "content": [{"type": "text", "text": "You are a helpful assistant."}],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            },
        ]
        for _, prompt in promptList
    ]

    rawOutputs = _runGemma31b(messages)
    if len(rawOutputs) != len(promptList):
        raise ValueError("LLM output count does not match prompt count.")

    results: Dict[str, Dict[str, object]] = {}
    for (promptType, _), raw in zip(promptList, rawOutputs):
        try:
            parsed = normalizeSchema(_parseJSONFromLLMOutput(raw))
        except ValueError:
            parsed = {}
        results[promptType] = parsed

    outPath = Path(_outputYAMLPath)
    outPath.parent.mkdir(parents=True, exist_ok=True)
    outPath.write_text(toYAML(results) + "\n", encoding="utf-8")

    return results


# Function to dump LLM run metadata and outputs into a text file.
def dumpLLMRunsToText(_runRecords: List[Dict[str, str]], _outputTextPath: str) -> None:
    lines: List[str] = []
    for rec in _runRecords:
        lines.extend(
            [
                "*LLM Name*",
                rec["llm_name"],
                "*Prompt Used*",
                rec["prompt_used"],
                "*Prompt Type*",
                rec["prompt_type"],
                "*LLM Output*",
                rec["llm_output"],
                "",
            ]
        )

    out = Path(_outputTextPath)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")



# Helper functions

# Helper function to build the shared document context.
def buildSharedDocumentContext(_doc1Name: str, _doc2Name: str, _docsText: Dict[str, List[str]]) -> str:
    doc1Candidates = extractRequirementCandidates(_docsText.get(_doc1Name, []))
    doc2Candidates = extractRequirementCandidates(_docsText.get(_doc2Name, []))

    doc1 = "\n".join(f"- {item}" for item in doc1Candidates).strip()
    doc2 = "\n".join(f"- {item}" for item in doc2Candidates).strip()

    if not doc1:
        doc1 = "\n".join(_docsText[_doc1Name]).strip()
    if not doc2:
        doc2 = "\n".join(_docsText[_doc2Name]).strip()

    return (
        f"Document A ({_doc1Name}) candidate requirements:\n{doc1}\n\n"
        f"Document B ({_doc2Name}) candidate requirements:\n{doc2}\n"
    )


# Helper function to build JSON schema instructions for the LLM.
def buildJSONSchemaInstruction() -> str:
    return (
        "Return ONLY valid JSON. Do not use markdown fences. "
        "Use exactly this shape: "
        "{\"element1\":{\"name\":\"...\",\"requirements\":[\"...\",\"...\"]},"
        "\"element2\":{\"name\":\"...\",\"requirements\":[\"...\"]}}. "
        "If no KDEs are found, return {}."
    )


# Helper function to build all default prompt types.
def buildDefaultPrompts(_doc1Name: str, _doc2Name: str, _docsText: Dict[str, List[str]]) -> List[Tuple[str, str]]:
    return [
        ("zero_shot", buildZeroShotPrompt(_doc1Name, _doc2Name, _docsText)),
        ("few_shot", buildFewShotPrompt(_doc1Name, _doc2Name, _docsText)),
        ("chain_of_thought", buildChainOfThoughtPrompt(_doc1Name, _doc2Name, _docsText)),
    ]


# Helper function to break down the provided pages into requirement candidates, to lessen the amount of info given to the LLM.
def extractRequirementCandidates(_pages: List[str], _maxCandidates: int = 120) -> List[str]:
   joined = "\n".join(_pages)
   if not joined.strip():
       return []

   linePattern = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.+?)\s*$")
   pagePattern = re.compile(r"^page\s+\d+\s*$", flags=re.IGNORECASE)
   appendixPattern = re.compile(r"^appendix\s*:", flags=re.IGNORECASE)
   trailingPagePattern = re.compile(r"\s*(?:\.{2,}\s*)?\d+\s*$")

   numberedTitles: Dict[str, str] = {}
   orderedNumbers: List[str] = []
   for rawLine in joined.splitlines():
       normalizedLine = re.sub(r"\s+", " ", rawLine).strip()
       if not normalizedLine or pagePattern.match(normalizedLine):
           continue

       match = linePattern.match(normalizedLine)
       if not match:
           continue

       number, rawTitle = match.groups()
       title = trailingPagePattern.sub("", rawTitle).strip().rstrip(".")
       if not title or appendixPattern.match(title):
           continue

       numberedTitles[number] = title
       orderedNumbers.append(number)

   candidates: List[str] = []
   seen = set()
   for number in orderedNumbers:
       parts = number.split(".")
       chain: List[str] = []
       for idx in range(1, len(parts) + 1):
           prefix = ".".join(parts[:idx])
           title = numberedTitles.get(prefix)
           if not title:
               continue
           chain.append(f"{prefix} {title}")

       if not chain:
           continue

       candidate = " -> ".join(chain)
       lowered = candidate.lower()
       if lowered in seen:
           continue
       seen.add(lowered)
       candidates.append(candidate)
       if len(candidates) >= _maxCandidates:
           break
   return candidates