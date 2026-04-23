# Imports various libraries as necessary
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import List, Tuple
import extractor
from comparator import compareKDENames, compareKDENamesAndRequirements
from executor import executeKubescapeScan, generateScanCSV, mapDifferencesToKubescapeControls

# Defines the pairs of PDF documents to be compared in the pipeline
PDF_PAIRS: List[Tuple[str, str]] = [
    ("cis-r1.pdf", "cis-r1.pdf"),
    ("cis-r1.pdf", "cis-r2.pdf"),
    ("cis-r1.pdf", "cis-r3.pdf"),
    ("cis-r1.pdf", "cis-r4.pdf"),
    ("cis-r2.pdf", "cis-r2.pdf"),
    ("cis-r2.pdf", "cis-r3.pdf"),
    ("cis-r2.pdf", "cis-r4.pdf"),
    ("cis-r3.pdf", "cis-r3.pdf"),
    ("cis-r3.pdf", "cis-r4.pdf"),
]


# Helper function to run the pipeline for all PDF pairs, including loading documents, running LLM inference, comparing results, and executing Kubescape scans.
def runPipeline() -> None:
    llmName = os.getenv("HF_MODEL", "google/gemma-3-1b-it")
    pdfDir=Path("Documents")
    outputDir=Path("Output")
    totalPairs = len(PDF_PAIRS)

    sourceDir = Path(".").resolve()
    outputZip = Path("project-yamls.zip").resolve()
    testsDir = Path("tests").resolve()
    outputZip = outputDir / "project-yamls.zip"
    outputZip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(outputZip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sourceDir.glob("*.py"):
            zf.write(path, arcname=path.name)
        for path in testsDir.rglob("*.py"):
            zf.write(path, arcname=str(path.relative_to(sourceDir.parent)))
    
    try:
        from transformers import pipeline
    except ImportError as exc:
            raise ValueError("transformers required for Hugging Face model inference.") from exc

    # Sets up a function for running Gemma.
    def runGemma31b(_messages):
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise ValueError("transformers is required for Hugging Face model inference.") from exc

        print(f"Running Gemma instance...")
        hfToken = os.getenv("HUGGINGFACE_HUB_TOKEN")
        generator = pipeline(
            "text-generation",
            model=llmName,
            token=hfToken if hfToken else None,
        )
        output = generator(_messages, max_new_tokens=1024)
        outputText = []
        for conversation in output:
            generated = conversation[0]["generated_text"]
            if isinstance(generated, list):
                outputText.append(generated[-1]["content"])
            else:
                outputText.append(generated)
        print(f"Instance run complete.")
        return outputText

    # For each pair of PDF documents, creates output directories, loads the documents, builds prompts, runs LLM inference, compares results, and executes Kubescape scans.
    for i, (docA, docB) in enumerate(PDF_PAIRS, start=1):
        runDir = outputDir / f"input-{i}"
        task1Dir = runDir / "task1"
        task2Dir = runDir / "task2"
        task3Dir = runDir / "task3"
        task1Dir.mkdir(parents=True, exist_ok=True)
        task2Dir.mkdir(parents=True, exist_ok=True)
        task3Dir.mkdir(parents=True, exist_ok=True)

        # Loads documents and builds prompts for the current pair of PDFs
        docsText = extractor.loadDocuments(str(pdfDir / docA), str(pdfDir / docB))
        prompts = extractor.buildDefaultPrompts(docA, docB, docsText)

        # Runs LLM inference with the built prompts. Handles ValueErrors related to missing Gemma dependencies by falling back to the heuristic LLM. Saves the results and compares KDE names and requirements.
        task1Output = task1Dir / f"{docA.replace('.pdf', '')}__{docB.replace('.pdf', '')}-kdes.yaml"
        promptResults = extractor.runKDEExtractionWithPrompts(
            _prompts=prompts,
            _runGemma31b=runGemma31b,
            _outputYAMLPath=str(task1Output),
        )

        # Saves the LLM run records to a text file for auditing and debugging purposes
        runRecords = [
            {
                "llm_name": llmName,
                "prompt_used": prompt,
                "prompt_type": promptType,
                "llm_output": json.dumps(promptResults[promptType]),
            }
            for promptType, prompt in prompts
        ]
        extractor.dumpLLMRunsToText(runRecords, str(task1Dir / "llm-runs.txt"))

        # Writes the primary KDEs extracted from the LLM output to YAML files for both documents, and compares the KDE names to identify differences. 
        # Maps the differences to Kubescape controls and executes a Kubescape scan if the binary is available.
        primaryKDEs = promptResults.get("zero_shot", {})
        docAYAML = task1Dir / f"{docA.replace('.pdf', '')}-kdes.yaml"
        docBYAML = task1Dir / f"{docB.replace('.pdf', '')}-kdes.yaml"

        # Creates parent directories for the output YAML files if they don't exist, and writes the primary KDEs to those files in JSON format (as a stand-in for YAML). 
        docAYAML.parent.mkdir(parents=True, exist_ok=True)
        docAYAML.write_text(json.dumps(primaryKDEs, indent=2), encoding="utf-8")
        docBYAML.parent.mkdir(parents=True, exist_ok=True)
        docBYAML.write_text(json.dumps(primaryKDEs, indent=2), encoding="utf-8")

        # Compares the KDE names and requirements between the two documents, saving the differences to text files. 
        # Then maps those differences to Kubescape controls and executes a scan if possible.
        namesDiff = task2Dir / "element-name-differences.txt"
        reqDiff = task2Dir / "element-requirement-differences.txt"
        compareKDENames(str(docAYAML), str(docBYAML), str(namesDiff))
        compareKDENamesAndRequirements(str(docAYAML), str(docBYAML), str(reqDiff))

        # Determines the controls file 
        controlsFile = task3Dir / "controls-to-scan.txt"
        mapDifferencesToKubescapeControls(str(namesDiff), str(reqDiff), str(controlsFile))

        # Finds a path to the Kubescape binary and executes a scan using the generated controls file. 
        # Saves the scan results to a CSV file. If Kubescape is not available, creates an empty CSV with just headers.
        kubescapePath = shutil.which("kubescape")
        if kubescapePath:
            scanDF = executeKubescapeScan(
                _projectYAMLsZip=str(outputZip),
                _controlsTextPath=str(controlsFile),
                _kubescapeBinary=kubescapePath,
            )
            generateScanCSV(scanDF, str(task3Dir / "kubescape-scan-results.csv"))
        else:
            (task3Dir / "kubescape-scan-results.csv").write_text(
                "FilePath,Severity,Control name,Failed resources,All Resources,Compliance score\n",
                encoding="utf-8",
            )


# Runs the main function to execute the pipeline.
if __name__ == "__main__":
    runPipeline()
