"""Read a financial statement PDF the way the baseline agent sees it: lines, headings and tables with positions.

Only the text layer is used. A page without one (a scan) is reported as unreadable rather than guessed at;
reading those is what the model-based agent is for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

NUMBER = re.compile(r"^-?\d{1,3}(?:\.\d{3})*$")
PREFIX = re.compile(r"^(?:(?P<roman>[IVX]+)|(?P<letter>[A-Z])|(?P<arabic>\d{1,2}))\.\s+")
LINE_TOLERANCE = 2.0  # points: words whose tops differ by less are on one line
RUN_GAP = 6.0  # points: header words closer than this belong to one header
COLUMN_SNAP = 4.0  # points: a number belongs to the column whose right edge is this close


def parse_number(text: str) -> int:
    return int(text.replace(".", ""))


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bold: bool


@dataclass
class Line:
    page: int
    top: float
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return self.words[0].x0

    @property
    def bold(self) -> bool:
        return all(w.bold for w in self.words)

    def split_numbers(self) -> tuple[list[Word], list[Word]]:
        """Label words, then the trailing numbers."""
        i = len(self.words)
        while i > 0 and NUMBER.match(self.words[i - 1].text):
            i -= 1
        return self.words[:i], self.words[i:]


@dataclass
class TableRow:
    label: str
    page: int
    bold: bool
    values: dict[str, int]  # column header -> value
    level: int = 0  # 1 letter, 2 roman, 3 arabic, 0 none

    @property
    def number(self) -> int | None:
        m = PREFIX.match(self.label)
        return int(m.group("arabic")) if m and m.group("arabic") else None

    @property
    def name(self) -> str:
        return normalise(PREFIX.sub("", self.label))


@dataclass
class ReadTable:
    title: str
    page: int
    columns: list[str]
    rows: list[TableRow] = field(default_factory=list)

    def row(self, name: str) -> TableRow | None:
        n = normalise(name)
        return next((r for r in self.rows if r.name == n), None)


@dataclass
class ReadDocument:
    file: str
    pages: int
    unreadable_pages: list[int]
    lines: list[Line]
    tables: list[ReadTable]

    def page_text(self, page: int) -> str:
        return " ".join(ln.text for ln in self.lines if ln.page == page)

    def text(self) -> str:
        return " ".join(ln.text for ln in self.lines)

    def headings(self) -> list[Line]:
        return [ln for ln in self.lines if ln.bold and not ln.split_numbers()[1]]

    def table(self, title: str) -> ReadTable | None:
        return next((t for t in self.tables if t.title == title), None)


def normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _lines(page: pdfplumber.page.Page, page_no: int) -> list[Line]:
    words = page.extract_words(extra_attrs=["fontname"], keep_blank_chars=False)
    out: list[Line] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        word = Word(w["text"], w["x0"], w["x1"], w["top"], "Bold" in w["fontname"])
        if out and abs(out[-1].top - word.top) < LINE_TOLERANCE:
            out[-1].words.append(word)
        else:
            out.append(Line(page_no, word.top, [word]))
    for ln in out:
        ln.words.sort(key=lambda w: w.x0)
    return [ln for ln in out if not re.fullmatch(r"Seite \d+", ln.text)]


def _runs(words: list[Word]) -> list[tuple[str, float]]:
    """Group header words into runs (one printed header each): (text, right edge)."""
    runs: list[list[Word]] = []
    for w in words:
        if runs and w.x0 - runs[-1][-1].x1 < RUN_GAP:
            runs[-1].append(w)
        else:
            runs.append([w])
    return [(" ".join(w.text for w in r), r[-1].x1) for r in runs]


def _read_table(title: Line, following: list[Line]) -> tuple[ReadTable, int]:
    """Header lines, then rows (a label and right-aligned numbers), then continuation lines of long labels."""
    header: list[Line] = []
    i = 0
    while i < len(following) and following[i].bold and not following[i].split_numbers()[1]:
        header.append(following[i])
        i += 1
    rows: list[tuple[Line, list[Word], list[Word]]] = []
    label_x: float | None = None
    while i < len(following):
        ln = following[i]
        label, numbers = ln.split_numbers()
        if numbers and label:
            rows.append((ln, label, numbers))
            label_x = ln.x0 if label_x is None else min(label_x, ln.x0)
        elif not numbers and rows and label_x is not None and ln.x0 > label_x + 4:
            rows[-1][1].extend(ln.words)  # a wrapped label
        else:
            break
        i += 1
    edges: list[float] = []
    for _ln, _label, numbers in rows:
        for w in numbers:
            if not any(abs(w.x1 - e) < COLUMN_SNAP for e in edges):
                edges.append(w.x1)
    edges.sort()
    names = [""] * len(edges)
    for h in header:
        for text, x1 in _runs(h.words):
            j = min(range(len(edges)), key=lambda k: abs(edges[k] - x1)) if edges else -1
            if j >= 0 and abs(edges[j] - x1) < COLUMN_SNAP * 3:
                names[j] = f"{names[j]} {text}".strip()
    table = ReadTable(title.text, title.page, names)
    for ln, label, numbers in rows:
        values: dict[str, int] = {}
        for w in numbers:
            j = min(range(len(edges)), key=lambda k: abs(edges[k] - w.x1))
            values[names[j]] = parse_number(w.text)
        text = " ".join(w.text for w in label)
        m = PREFIX.match(text)
        level = 0
        if m:
            level = 1 if m.group("letter") else 2 if m.group("roman") else 3
        table.rows.append(TableRow(text, ln.page, ln.bold, values, level))
    return table, i


def read(path: Path, table_titles: list[str]) -> ReadDocument:
    lines: list[Line] = []
    unreadable: list[int] = []
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for k, page in enumerate(pdf.pages, start=1):
            page_lines = _lines(page, k)
            if not page_lines:
                unreadable.append(k)
            lines += page_lines
    tables: list[ReadTable] = []
    i = 0
    titles = set(table_titles)
    while i < len(lines):
        ln = lines[i]
        if ln.bold and ln.text in titles:
            same_page = [x for x in lines[i + 1 :] if x.page == ln.page]
            t, used = _read_table(ln, same_page)
            if t.rows:
                tables.append(t)
            i += 1 + used
        else:
            i += 1
    return ReadDocument(path.name, n, unreadable, lines, tables)
