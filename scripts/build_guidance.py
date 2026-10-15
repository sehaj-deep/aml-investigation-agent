"""Build the AML guidance corpus: download the sources, extract text, split passages.

    python scripts/build_guidance.py

Sources are US government publications (public domain). The originals go to
data/guidance/raw (gitignored, some are over the repository's file-size limit); the
passages go to guidance/passages.jsonl and the source list to guidance/SOURCES.md, both
committed. Typography is normalized (whitespace, long dashes), nothing else. Loading into
Postgres with embeddings is scripts/load_guidance.py.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "guidance" / "raw"
OUT = ROOT / "guidance"
MAX_WORDS = 140
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SOURCES = [
    {
        "doc_id": "ffiec-appendix-f",
        "title": "FFIEC BSA/AML Examination Manual, Appendix F: Money Laundering and "
        "Terrorist Financing Red Flags",
        "publisher": "FFIEC",
        "url": "https://bsaaml.ffiec.gov/manual/Appendices/07",
        "file": "ffiec_appendix_f.html",
    },
    {
        "doc_id": "fincen-sar-narrative-2003",
        "title": "FinCEN, Guidance on Preparing a Complete and Sufficient Suspicious Activity "
        "Report Narrative (2003)",
        "publisher": "FinCEN",
        "url": "https://www.fincen.gov/sites/default/files/shared/sarnarrcompletguidfinal_112003.pdf",
        "file": "sarnarrcompletguidfinal_112003.pdf",
    },
    {
        "doc_id": "fincen-sar-common-errors",
        "title": "FinCEN, Suggestions for Addressing Common Errors Noted in Suspicious "
        "Activity Reporting (2007)",
        "publisher": "FinCEN",
        "url": "https://www.fincen.gov/sites/default/files/shared/SAR_Common_Errors_Web_Posting.pdf",
        "file": "SAR_Common_Errors_Web_Posting.pdf",
    },
    {
        "doc_id": "fincen-fin-2014-a005",
        "title": "FinCEN Advisory FIN-2014-A005, Update on U.S. Currency Restrictions in "
        "Mexico: Funnel Accounts and TBML (2014)",
        "publisher": "FinCEN",
        "url": "https://www.fincen.gov/sites/default/files/shared/FIN-2014-A005.pdf",
        "file": "FIN-2014-A005.pdf",
    },
    {
        "doc_id": "fincen-fin-2006-g014",
        "title": "FinCEN Guidance FIN-2006-G014, Potential Money Laundering Risks Related to "
        "Shell Companies (2006)",
        "publisher": "FinCEN",
        "url": "https://www.fincen.gov/sites/default/files/shared/AdvisoryOnShells_FINAL.pdf",
        "file": "AdvisoryOnShells_FINAL.pdf",
    },
]


def clean(text: str) -> str:
    text = text.replace(chr(0x2014), " - ").replace("­", "")
    return re.sub(r"\s+", " ", text).strip()


def fetch(src: dict) -> Path:
    path = RAW / src["file"]
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(src["url"], headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as resp:
            path.write_bytes(resp.read())
    return path


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;:?!])\s+(?=[A-Z0-9\"(])", text) if s]


def windows(parts: list[str], max_words: int = MAX_WORDS) -> list[str]:
    """Group sentences or list items into passages of up to max_words words."""
    out, cur, n = [], [], 0
    for part in parts:
        words = len(part.split())
        if cur and n + words > max_words:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(part)
        n += words
    if cur:
        out.append(" ".join(cur))
    return out


def pdf_passages(src: dict, path: Path) -> list[dict]:
    from pypdf import PdfReader

    out = []
    for page_no, page in enumerate(PdfReader(path).pages, start=1):
        text = clean(page.extract_text() or "")
        if len(text.split()) < 20 or text.count("....") > 5:
            continue  # covers, blank pages, page furniture and tables of contents
        for i, chunk in enumerate(windows(sentences(text)), start=1):
            out.append(
                {
                    "id": f"{src['doc_id']}-p{page_no}-{i}",
                    "page": page_no,
                    "section": None,
                    "text": chunk,
                }
            )
    return out


class _Outline(HTMLParser):
    """Headings and the text blocks under them, in page order."""

    BLOCKS = {"p", "li", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__()
        self.items: list[tuple[str, str]] = []  # (tag, text)
        self._tag: str | None = None
        self._buf: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip += 1
        elif tag in self.BLOCKS and not self._skip:
            self._flush()
            self._tag = tag

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = max(0, self._skip - 1)
        elif tag == self._tag:
            self._flush()

    def handle_data(self, data):
        if self._tag and not self._skip:
            self._buf.append(data)

    def _flush(self):
        if self._tag:
            text = clean("".join(self._buf))
            if text:
                self.items.append((self._tag, text))
        self._tag, self._buf = None, []


def html_passages(src: dict, path: Path) -> list[dict]:
    parser = _Outline()
    parser.feed(path.read_text(encoding="utf-8"))
    start = next(i for i, (_, t) in enumerate(parser.items) if t.startswith("The following are"))
    sections: list[tuple[str, list[str]]] = [("Introduction", [])]
    for tag, text in parser.items[start:]:
        if tag.startswith("h"):
            sections.append((text, []))
        else:
            sections[-1][1].append(text)
    out = []
    for s_no, (heading, blocks) in enumerate(sections, start=1):
        for i, chunk in enumerate(windows(blocks), start=1):
            out.append(
                {
                    "id": f"{src['doc_id']}-s{s_no}-{i}",
                    "page": None,
                    "section": heading,
                    "text": f"{heading}: {chunk}" if heading != "Introduction" else chunk,
                }
            )
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    passages, lines = [], []
    for src in SOURCES:
        path = fetch(src)
        rows = pdf_passages(src, path) if path.suffix == ".pdf" else html_passages(src, path)
        meta = {k: src[k] for k in ("doc_id", "title", "publisher", "url")}
        passages += [{**meta, "jurisdiction": "US", **r} for r in rows]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(
            f"| {src['title']} | {src['publisher']} | [{src['file']}]({src['url']}) "
            f"| {len(rows)} | `{digest[:16]}` |"
        )
        print(f"{src['doc_id']}: {len(rows)} passages")
    (OUT / "passages.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in passages),
        encoding="utf-8",
        newline="\n",
    )
    (OUT / "SOURCES.md").write_text(
        "# Guidance sources\n\n"
        "Public AML guidance used by the guidance lookup. All are works of the US federal "
        "government (FinCEN, FFIEC) and are in the public domain. The originals are "
        "downloaded by `scripts/build_guidance.py` into `data/guidance/raw` (not committed); "
        "`passages.jsonl` holds the extracted passages. Typography is normalized "
        "(whitespace, long dashes); the wording is unchanged.\n\n"
        "| Document | Publisher | Original | Passages | SHA-256 (first 16) |\n"
        "|---|---|---|---|---|\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"{len(passages)} passages written to {OUT / 'passages.jsonl'}")


if __name__ == "__main__":
    main()
