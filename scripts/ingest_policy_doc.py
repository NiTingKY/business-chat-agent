from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib import request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
JAVA_PROJECT = ROOT.parent / "travel-agent-guide-main" / "project-java"
DEFAULT_DOC = JAVA_PROJECT / "travel.doc"


def _run(cmd: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout.strip()


def _maven_classpath(java_project: Path) -> str:
    cp_file = java_project / "target" / "doc-extract-classpath.txt"
    wrapper = java_project / "mvnw.cmd"
    _run(
        [
            str(wrapper),
            "-q",
            "-DincludeScope=runtime",
            f"-Dmdep.outputFile={cp_file}",
            "dependency:build-classpath",
        ],
        cwd=java_project,
    )
    return cp_file.read_text(encoding="utf-8").strip()


def extract_doc_text(doc_path: Path, *, java_project: Path = JAVA_PROJECT) -> str:
    if not doc_path.exists():
        raise FileNotFoundError(doc_path)
    classpath = _maven_classpath(java_project)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "DocTextExtractor.java"
        source.write_text(
            """
import java.io.FileInputStream;
import org.apache.poi.hwpf.HWPFDocument;
import org.apache.poi.hwpf.extractor.WordExtractor;

public class DocTextExtractor {
    public static void main(String[] args) throws Exception {
        try (FileInputStream in = new FileInputStream(args[0]);
             HWPFDocument doc = new HWPFDocument(in);
             WordExtractor extractor = new WordExtractor(doc)) {
            System.out.print(extractor.getText());
        }
    }
}
""".strip(),
            encoding="utf-8",
        )
        _run(["javac", "-encoding", "UTF-8", "-cp", classpath, str(source)], cwd=tmp_path)
        cp = f"{tmp_path};{classpath}"
        proc = subprocess.run(
            ["java", "-cp", cp, "DocTextExtractor", str(doc_path)],
            cwd=str(tmp_path),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        text = proc.stdout.decode("gbk", errors="replace")
    lines = [
        line.rstrip()
        for line in text.splitlines()
        if "org.apache.poi" not in line and "Unsupported Sprm operation" not in line
    ]
    return "\n".join(line for line in lines if line.strip() not in {"", "?"}).strip()


def ingest(base_url: str, *, title: str, content: str, doc_type: str) -> dict:
    payload = json.dumps(
        {"title": title, "content": content, "doc_type": doc_type, "metadata": {"source": "travel.doc"}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        base_url.rstrip("/") + "/api/v1/documents/ingest",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract old Word .doc policy and ingest it.")
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    parser.add_argument("--java-project", default=str(JAVA_PROJECT))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--title", default="企业差旅政策")
    parser.add_argument("--doc-type", default="policy")
    parser.add_argument("--extract-only", action="store_true")
    args = parser.parse_args()

    text = extract_doc_text(Path(args.doc), java_project=Path(args.java_project))
    print(json.dumps({"chars": len(text), "preview": text[:240]}, ensure_ascii=False, indent=2))
    if args.extract_only:
        return 0
    result = ingest(args.base_url, title=args.title, content=text, doc_type=args.doc_type)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
