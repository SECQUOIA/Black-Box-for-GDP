"""Export the manuscript's plain-text submission statements to editable Word files."""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def write_docx(path: Path, paragraphs: list[str], *, bullets: bool = False) -> None:
    """Write a minimal, editable Word document without optional Python packages."""
    blocks = []
    for paragraph in paragraphs:
        properties = (
            '<w:pPr><w:numPr><w:ilvl w:val="0"/>'
            '<w:numId w:val="1"/></w:numPr></w:pPr>' if bullets else ""
        )
        lines = '</w:t><w:br/><w:t xml:space="preserve">'.join(
            escape(line) for line in paragraph.splitlines()
        )
        blocks.append(
            f'<w:p>{properties}<w:r><w:t xml:space="preserve">'
            f'{lines}</w:t></w:r></w:p>'
        )
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    parts = {
        "[Content_Types].xml": (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
            '</Types>'
        ),
        "_rels/.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'
        ),
        "word/document.xml": (
            f'<w:document xmlns:w="{namespace}"><w:body>{"".join(blocks)}'
            '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
            '</w:sectPr></w:body></w:document>'
        ),
        "word/styles.xml": (
            f'<w:styles xmlns:w="{namespace}"><w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
            '<w:sz w:val="24"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
            '<w:spacing w:after="120"/></w:pPr></w:pPrDefault></w:docDefaults></w:styles>'
        ),
        "word/numbering.xml": (
            f'<w:numbering xmlns:w="{namespace}"><w:abstractNum w:abstractNumId="0">'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
            '<w:lvlText w:val="•"/><w:pPr><w:ind w:left="360" w:hanging="180"/>'
            '</w:pPr></w:lvl></w:abstractNum><w:num w:numId="1">'
            '<w:abstractNumId w:val="0"/></w:num></w:numbering>'
        ),
        "word/_rels/document.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            '</Relationships>'
        ),
    }
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "manuscript" / "submission"
    highlights = (source / "highlights.txt").read_text(encoding="utf-8").splitlines()
    if not 3 <= len(highlights) <= 5 or any(not line or len(line) > 85 for line in highlights):
        raise ValueError("Highlights must contain 3–5 nonempty lines of at most 85 characters")
    cover = (source / "cover-letter.txt").read_text(encoding="utf-8").strip().split("\n\n")
    interests = (source / "competing-interests.tex").read_text(encoding="utf-8").strip()
    if "\\" in interests or any(character in interests for character in "{}%"):
        raise ValueError("The competing-interest source must remain plain prose")
    args.output.mkdir(parents=True, exist_ok=True)
    write_docx(args.output / "Highlights.docx", highlights, bullets=True)
    write_docx(args.output / "Cover-letter.docx", cover)
    write_docx(args.output / "Declaration-of-competing-interests.docx", [interests])


if __name__ == "__main__":
    main()
