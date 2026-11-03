"""Draw a document model to PDF and record where every checkable thing landed.

The location map (id -> page, box, label, text) is ground truth: it stays on the evaluation side and lets the
matcher turn an agent's "page 3, row 'Sonstige Rückstellungen', column 2025" into a location id. A scanned
document is drawn the same way, then each page is replaced by its picture, so it carries no text layer.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from .document import Document, Heading, Paragraph, Table

MARGIN = 56
FONT, BOLD = "Helvetica", "Helvetica-Bold"
SIZE = {"h1": 13, "h2": 10.5, "body": 9, "table": 8.5, "table_small": 7}
LEADING = {"body": 12.5, "row": 13.5, "row_small": 12}
SCAN_DPI_SCALE = 1.6  # rasterising scale for "scanned" pages (about 115 dpi)


@dataclass
class Placed:
    id: str
    kind: str  # cell | claim | heading | block | row_label
    page: int  # 1-based
    bbox: tuple[float, float, float, float]  # x0, top, x1, bottom (points, origin top-left, as pdfplumber)
    text: str
    label: str = ""  # row label for cells
    column: str = ""  # column header for cells

    def to_json(self) -> dict:
        return asdict(self)


class _Writer:
    def __init__(self, doc: Document, out: io.BytesIO):
        self.doc = doc
        self.c = canvas.Canvas(out, pagesize=A4, pageCompression=1)
        self.c.setTitle(doc.title)
        self.c.setAuthor("audit-agent-evals (synthetic)")
        self.placed: list[Placed] = []
        self.page_no = 0
        self.size = A4
        self.y = 0.0

    def new_page(self, landscape_: bool) -> None:
        if self.page_no:
            self.c.showPage()
        self.page_no += 1
        self.size = landscape(A4) if landscape_ else A4
        self.c.setPageSize(self.size)
        self.y = self.size[1] - MARGIN
        self.c.setFont(FONT, 7)
        self.c.drawRightString(self.size[0] - MARGIN, MARGIN / 2, f"Seite {self.page_no}")

    def top(self, y_baseline: float, size: float) -> float:
        return self.size[1] - y_baseline - size

    def place(
        self, pid: str, kind: str, x0: float, y_baseline: float, x1: float, size: float, text: str, **kw: str
    ) -> None:
        top = self.size[1] - y_baseline - size * 0.8
        self.placed.append(
            Placed(
                pid,
                kind,
                self.page_no,
                (round(x0, 1), round(top, 1), round(x1, 1), round(top + size * 1.1, 1)),
                text,
                **kw,
            )
        )

    def heading(self, h: Heading) -> None:
        size = SIZE["h1"] if h.level == 1 else SIZE["h2"]
        self.y -= size * 0.6
        self.c.setFont(BOLD, size)
        self.c.drawString(MARGIN, self.y, h.text)
        width = self.c.stringWidth(h.text, BOLD, size)
        self.place(f"{self.doc.id}:heading:{h.id}", "heading", MARGIN, self.y, MARGIN + width, size, h.text)
        self.y -= size * 1.2

    def paragraph(self, p: Paragraph) -> None:
        width = self.size[0] - 2 * MARGIN
        lines = simpleSplit(p.text, FONT, SIZE["body"], width)
        self.c.setFont(FONT, SIZE["body"])
        start = self.y
        for line in lines:
            self.c.drawString(MARGIN, self.y, line)
            self.y -= LEADING["body"]
        top = self.size[1] - start - SIZE["body"]
        box = (MARGIN, round(top, 1), MARGIN + width, round(self.size[1] - self.y - LEADING["body"] + SIZE["body"], 1))
        self.placed.append(Placed(f"{self.doc.id}:block:{p.id}", "block", self.page_no, box, p.text))
        for part in p.parts:
            if not isinstance(part, str):
                self.placed.append(
                    Placed(
                        f"{self.doc.id}:claim:{part.id}",
                        "claim",
                        self.page_no,
                        box,
                        part.template.replace("{v}", part.value),
                    )
                )
        self.y -= LEADING["body"] * 0.4

    def table(self, t: Table) -> None:
        small = len(t.columns) > 4
        fsize = SIZE["table_small"] if small else SIZE["table"]
        lead = LEADING["row_small"] if small else LEADING["row"]
        width = self.size[0] - 2 * MARGIN
        col_w = 60 if small else 78
        label_w = width - col_w * len(t.columns)
        self.c.setFont(BOLD, fsize + 1)
        self.c.drawString(MARGIN, self.y, t.title)
        self.place(f"{self.doc.id}:block:{t.id}", "block", MARGIN, self.y, MARGIN + width, fsize + 1, t.title)
        self.y -= lead * 1.3
        self.c.setFont(BOLD, fsize)
        for i, (_k, header) in enumerate(t.columns):
            x1 = MARGIN + label_w + col_w * (i + 1) - 4
            for j, part in enumerate(simpleSplit(header, BOLD, fsize, col_w - 6)):
                self.c.drawRightString(x1, self.y - j * (fsize + 1), part)
        self.y -= lead * (1.6 if small else 1.1)
        self.c.line(MARGIN, self.y + lead * 0.6, MARGIN + width, self.y + lead * 0.6)
        for r in t.rows:
            font = BOLD if r.total else FONT
            self.c.setFont(font, fsize)
            indent = 10 * getattr(r, "level", 0)
            label = simpleSplit(r.label, font, fsize, label_w - indent - 8)
            self.c.drawString(MARGIN + indent, self.y, label[0])
            self.place(
                f"{self.doc.id}:{t.id}:{r.key}", "row_label", MARGIN + indent, self.y, MARGIN + label_w, fsize, r.label
            )
            for c in r.cells:
                i = [k for k, _ in t.columns].index(c.col)
                x1 = MARGIN + label_w + col_w * (i + 1) - 4
                self.c.drawRightString(x1, self.y, c.text)
                w = self.c.stringWidth(c.text, font, fsize)
                self.place(
                    f"{self.doc.id}:{t.id}:{r.key}:{c.col}",
                    "cell",
                    x1 - w,
                    self.y,
                    x1,
                    fsize,
                    c.text,
                    label=r.label,
                    column=dict(t.columns)[c.col],
                )
            for extra in label[1:]:
                self.y -= lead * 0.85
                self.c.drawString(MARGIN + indent + 8, self.y, extra)
            if r.total:
                self.c.line(MARGIN + label_w, self.y + lead * 0.7, MARGIN + width, self.y + lead * 0.7)
            self.y -= lead
        self.y -= lead * 0.5

    def finish(self) -> None:
        self.c.save()


def render(doc: Document) -> tuple[bytes, list[Placed]]:
    buf = io.BytesIO()
    w = _Writer(doc, buf)
    for page in doc.pages:
        w.new_page(page.landscape)
        for b in page.blocks:
            if isinstance(b, Heading):
                w.heading(b)
            elif isinstance(b, Paragraph):
                w.paragraph(b)
            elif isinstance(b, Table):
                w.table(b)
    w.finish()
    data = buf.getvalue()
    if doc.scanned:
        data = rasterize(data)
    return data, w.placed


def rasterize(pdf: bytes) -> bytes:
    """Replace each page by its picture: what a scanned document looks like to a reader without OCR."""
    src = pdfium.PdfDocument(pdf)
    out = io.BytesIO()
    c = canvas.Canvas(out)
    for i in range(len(src)):
        page = src[i]
        w, h = page.get_size()
        img = page.render(scale=SCAN_DPI_SCALE, grayscale=True).to_pil()
        png = io.BytesIO()
        img.save(png, format="PNG", optimize=True)
        png.seek(0)
        c.setPageSize((w, h))
        c.drawImage(ImageReader(png), 0, 0, width=w, height=h)
        c.showPage()
    c.save()
    return out.getvalue()


def write(doc: Document, folder: Path) -> list[Placed]:
    data, placed = render(doc)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{doc.id}.pdf").write_bytes(data)
    return placed
