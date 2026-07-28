#!/usr/bin/env python3
"""HWPX 문서 생성 — 표준 라이브러리만 사용한다.

KS X 6101:2024(OWPML) 규격과 한컴 실제 출력에 맞춰 XML을 조립한다.
lxml·python-hwpx 없이 zipfile + 문자열 조립으로만 동작하므로
패키지 설치가 불가능한 환경에서도 쓸 수 있다.

사용 예:
    from hwpx_build import HwpxDoc

    doc = HwpxDoc()
    doc.add_heading("2026학년도 운영 계획", size=16, align="CENTER")
    doc.add_paragraph("아래와 같이 계획을 수립함.")
    doc.add_table(
        [["구분", "내용"], ["기간", "2026. 3. ~ 2027. 2."]],
        header=True,
    )
    doc.save("output.hwpx")
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "base"

# KS X 6101:2024 7.2.4 — 단위 환산
PT = 100          # 1 pt
MM = 283.456      # 1 mm
A4_WIDTH = 59528
A4_HEIGHT = 84186
BODY_WIDTH = 42520   # A4 폭에서 좌우 여백(8504×2)을 뺀 본문 폭

NS_DECL = (
    'xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph" '
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" '
    'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
    'xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history" '
    'xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page" '
    'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:opf="http://www.idpf.org/2007/opf/" '
    'xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart" '
    'xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar" '
    'xmlns:epub="http://www.idpf.org/2007/ops" '
    'xmlns:config="http://www.hancom.co.kr/hwpml/2016/config"'
)

# mimetype과 version.xml은 압축하지 않는다 (KS X 6101:2024 8.3)
STORED_ENTRIES = ("mimetype", "version.xml")


def esc(text: str) -> str:
    """XML 특수문자 이스케이프."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class HwpxDoc:
    """base 템플릿 위에 문단·표를 쌓아 HWPX를 만든다."""

    def __init__(self, template_dir: str | Path | None = None):
        src = Path(template_dir) if template_dir else TEMPLATE_DIR
        if not src.is_dir():
            raise FileNotFoundError(f"템플릿 폴더가 없다: {src}")
        self._tmp = Path(tempfile.mkdtemp(prefix="hwpx-build-"))
        self.root = self._tmp / "doc"
        shutil.copytree(src, self.root)

        self.header_path = self.root / "Contents" / "header.xml"
        self.header = self.header_path.read_text(encoding="utf-8")
        self._body: list[str] = []
        self._next_id = 2000000000
        self._style_cache: dict[tuple, int] = {}

    # ------------------------------------------------------------------ 내부
    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _count(self, tag: str) -> int:
        return len(re.findall(rf"<hh:{tag}\b", self.header))

    def _last_block(self, tag: str) -> str:
        """목록의 마지막 항목 XML을 통째로 돌려준다(복제용 원본)."""
        blocks = re.findall(rf"<hh:{tag}\b.*?</hh:{tag}>", self.header, re.S)
        if not blocks:
            raise RuntimeError(f"{tag}를 header에서 찾지 못했다")
        return blocks[-1]

    def _append_style(self, list_tag: str, item_tag: str, xml: str) -> None:
        """스타일 목록 '끝'에만 추가하고 itemCnt를 갱신한다.

        한컴은 charPr/paraPr을 id가 아니라 목록 내 물리적 순서로 해석한다.
        중간에 끼워 넣으면 그 뒤 모든 참조가 한 칸씩 밀려 문서 서식이 깨진다.
        """
        close = f"</hh:{list_tag}>"
        if close not in self.header:
            raise RuntimeError(f"{list_tag} 목록이 없다")
        self.header = self.header.replace(close, xml + close, 1)

        def bump(m: re.Match) -> str:
            return f'{m.group(1)}{int(m.group(2)) + 1}"'

        self.header = re.sub(
            rf'(<hh:{list_tag}\b[^>]*itemCnt=")(\d+)"',
            bump,
            self.header,
            count=1,
        )

    def ensure_char_style(
        self,
        size_pt: float = 10,
        bold: bool = False,
        color: str = "#000000",
        font: str | None = None,
    ) -> int:
        """글자 모양을 확보하고 charPr id를 돌려준다. 없으면 목록 끝에 추가."""
        key = ("char", size_pt, bold, color, font)
        if key in self._style_cache:
            return self._style_cache[key]

        base = self._last_block("charPr")
        new_id = self._count("charPr")
        xml = base

        xml = re.sub(r'(<hh:charPr id=")\d+(")', rf"\g<1>{new_id}\g<2>", xml, count=1)
        xml = re.sub(
            r'(<hh:charPr[^>]*\bheight=")\d+(")',
            rf"\g<1>{int(size_pt * PT)}\g<2>",
            xml,
            count=1,
        )
        xml = re.sub(
            r'(<hh:charPr[^>]*\btextColor=")[^"]*(")', rf"\g<1>{color}\g<2>", xml, count=1
        )
        if font is not None:
            fid = self._ensure_font(font)
            xml = re.sub(
                r"<hh:fontRef[^/]*/>",
                f'<hh:fontRef hangul="{fid}" latin="{fid}" hanja="{fid}" '
                f'japanese="{fid}" other="{fid}" symbol="{fid}" user="{fid}"/>',
                xml,
                count=1,
            )

        # bold는 속성이 아니라 '요소의 존재'로 켜진다 (KS X 6101:2024 표 46).
        # 순서도 스키마상 offset 뒤, underline 앞이다.
        xml = xml.replace("<hh:bold/>", "")
        if bold:
            if "<hh:underline" in xml:
                xml = xml.replace("<hh:underline", "<hh:bold/><hh:underline", 1)
            else:
                xml = xml.replace("</hh:charPr>", "<hh:bold/></hh:charPr>", 1)

        self._append_style("charProperties", "charPr", xml)
        self._style_cache[key] = new_id
        return new_id

    def _ensure_font(self, face: str) -> int:
        """HANGUL fontface에 글꼴이 없으면 추가하고 id를 돌려준다."""
        m = re.search(
            r'<hh:fontface lang="HANGUL"[^>]*>(.*?)</hh:fontface>', self.header, re.S
        )
        if not m:
            return 0
        block = m.group(1)
        found = re.search(rf'<hh:font id="(\d+)" face="{re.escape(face)}"', block)
        if found:
            return int(found.group(1))

        fonts = re.findall(r'<hh:font id="(\d+)"', block)
        new_id = max(int(f) for f in fonts) + 1 if fonts else 0
        entry = (
            f'<hh:font id="{new_id}" face="{esc(face)}" type="TTF" isEmbedded="0">'
            '<hh:typeInfo familyType="FCAT_GOTHIC" weight="6" proportion="4" contrast="0"'
            ' strokeVariation="1" armStyle="1" letterform="1" midline="1" xHeight="1"/>'
            "</hh:font>"
        )
        old = m.group(0)
        new = old.replace("</hh:fontface>", entry + "</hh:fontface>")
        new = re.sub(r'(fontCnt=")(\d+)"', lambda x: f'{x.group(1)}{int(x.group(2)) + 1}"', new, count=1)
        self.header = self.header.replace(old, new, 1)
        return new_id

    def ensure_para_style(
        self,
        align: str = "JUSTIFY",
        line_spacing: int = 160,
        indent: int = 0,
        left: int = 0,
        prev: int = 0,
        next_: int = 0,
    ) -> int:
        """문단 모양을 확보하고 paraPr id를 돌려준다."""
        key = ("para", align, line_spacing, indent, left, prev, next_)
        if key in self._style_cache:
            return self._style_cache[key]

        base = self._last_block("paraPr")
        new_id = self._count("paraPr")
        xml = base
        xml = re.sub(r'(<hh:paraPr id=")\d+(")', rf"\g<1>{new_id}\g<2>", xml, count=1)
        xml = re.sub(
            r'(<hh:align[^>]*horizontal=")[^"]*(")', rf"\g<1>{align}\g<2>", xml, count=1
        )
        xml = re.sub(
            r'(<hh:lineSpacing[^>]*value=")\d+(")',
            rf"\g<1>{line_spacing}\g<2>",
            xml,
            count=1,
        )
        for tag, val in (("intent", indent), ("left", left), ("prev", prev), ("next", next_)):
            # 값과 단위는 반드시 함께 쓴다. unit을 빼면 CHAR(500 HWPUNIT)로 해석된다.
            xml = re.sub(
                rf'<hc:{tag} value="-?\d+" unit="\w+"/>',
                f'<hc:{tag} value="{val}" unit="HWPUNIT"/>',
                xml,
                count=1,
            )

        self._append_style("paraProperties", "paraPr", xml)
        self._style_cache[key] = new_id
        return new_id

    # ------------------------------------------------------------------ 본문
    def add_paragraph(
        self,
        text: str = "",
        size_pt: float = 10,
        bold: bool = False,
        align: str = "JUSTIFY",
        color: str = "#000000",
        font: str | None = None,
        line_spacing: int = 160,
        indent: int = 0,
        left: int = 0,
        page_break: bool = False,
    ) -> None:
        """문단 하나를 추가한다. text가 비면 빈 줄."""
        cid = self.ensure_char_style(size_pt, bold, color, font)
        pid = self.ensure_para_style(align, line_spacing, indent, left)
        body = f"<hp:t>{esc(text)}</hp:t>" if text else "<hp:t/>"
        self._body.append(
            f'<hp:p id="{self._new_id()}" paraPrIDRef="{pid}" styleIDRef="0" '
            f'pageBreak="{1 if page_break else 0}" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cid}">{body}</hp:run></hp:p>'
        )

    def add_heading(self, text: str, size: float = 14, align: str = "LEFT", font: str | None = None) -> None:
        """제목 문단. 굵게 + 위아래 간격."""
        cid = self.ensure_char_style(size, True, "#000000", font)
        pid = self.ensure_para_style(align, 160, 0, 0, prev=300, next_=200)
        self._body.append(
            f'<hp:p id="{self._new_id()}" paraPrIDRef="{pid}" styleIDRef="0" '
            f'pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cid}"><hp:t>{esc(text)}</hp:t></hp:run></hp:p>'
        )

    def add_page_break(self) -> None:
        self.add_paragraph("", page_break=True)

    def add_table(
        self,
        rows: list[list[str]],
        header: bool = True,
        widths: list[int] | None = None,
        row_height: int = 1200,
        size_pt: float = 10,
        page_break: str = "CELL",
    ) -> None:
        """표를 추가한다.

        rows       2차원 문자열 배열. 모든 행의 길이가 같아야 한다.
        widths     열 너비(HWPUNIT). 생략하면 본문 폭을 균등 분할한다.
        page_break 페이지 경계 처리 — CELL(기본) / TABLE(셀은 안 나눔) / NONE(표 전체가 다음 쪽)
        """
        if not rows or not rows[0]:
            raise ValueError("빈 표는 만들 수 없다")
        n_row, n_col = len(rows), len(rows[0])
        for r in rows:
            if len(r) != n_col:
                raise ValueError(f"행마다 열 수가 다르다: {n_col} vs {len(r)}")
        if page_break not in ("CELL", "TABLE", "NONE"):
            raise ValueError("page_break는 CELL/TABLE/NONE 중 하나여야 한다")

        if widths is None:
            base_w = BODY_WIDTH // n_col
            widths = [base_w] * n_col
            widths[-1] = BODY_WIDTH - base_w * (n_col - 1)

        cid_normal = self.ensure_char_style(size_pt)
        cid_header = self.ensure_char_style(size_pt, bold=True)
        pid_cell = self.ensure_para_style("CENTER", 160, 0, 0)

        trs = []
        for r, row in enumerate(rows):
            tcs = []
            for c, cell in enumerate(row):
                cid = cid_header if (header and r == 0) else cid_normal
                # tc 자식 순서는 subList → cellAddr → cellSpan → cellSz → cellMargin
                tcs.append(
                    f'<hp:tc name="" header="{1 if (header and r == 0) else 0}" '
                    f'hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="2">'
                    f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
                    f'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" '
                    f'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
                    f'<hp:p id="{self._new_id()}" paraPrIDRef="{pid_cell}" styleIDRef="0" '
                    f'pageBreak="0" columnBreak="0" merged="0">'
                    f'<hp:run charPrIDRef="{cid}"><hp:t>{esc(cell)}</hp:t></hp:run>'
                    f"</hp:p></hp:subList>"
                    f'<hp:cellAddr colAddr="{c}" rowAddr="{r}"/>'
                    f'<hp:cellSpan colSpan="1" rowSpan="1"/>'
                    f'<hp:cellSz width="{widths[c]}" height="{row_height}"/>'
                    f'<hp:cellMargin left="510" right="510" top="141" bottom="141"/>'
                    f"</hp:tc>"
                )
            trs.append("<hp:tr>" + "".join(tcs) + "</hp:tr>")

        total_h = row_height * n_row
        # rowCnt/colCnt는 필수다. 빠지면 한컴이 격자를 만들지 못해 문서가 열리지 않는다.
        tbl = (
            f'<hp:tbl id="{self._new_id()}" zOrder="0" numberingType="TABLE" '
            f'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
            f'dropcapstyle="None" pageBreak="{page_break}" repeatHeader="1" '
            f'rowCnt="{n_row}" colCnt="{n_col}" cellSpacing="0" '
            f'borderFillIDRef="2" noAdjust="0">'
            f'<hp:sz width="{BODY_WIDTH}" widthRelTo="ABSOLUTE" height="{total_h}" '
            f'heightRelTo="ABSOLUTE" protect="0"/>'
            f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" '
            f'allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" '
            f'vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
            f'<hp:inMargin left="510" right="510" top="141" bottom="141"/>'
            + "".join(trs)
            + "</hp:tbl>"
        )
        pid = self.ensure_para_style("JUSTIFY", 160, 0, 0)
        self._body.append(
            f'<hp:p id="{self._new_id()}" paraPrIDRef="{pid}" styleIDRef="0" '
            f'pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cid_normal}">{tbl}<hp:t/></hp:run></hp:p>'
        )

    # ------------------------------------------------------------------ 저장
    def _section_xml(self) -> str:
        original = (self.root / "Contents" / "section0.xml").read_text(encoding="utf-8")
        m = re.search(r"<hp:p\b.*?</hp:p>", original, re.S)
        if not m or "<hp:secPr" not in m.group(0):
            raise RuntimeError("템플릿 첫 문단에서 secPr을 찾지 못했다")
        first = m.group(0)
        return (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
            f"<hs:sec {NS_DECL}>" + first + "".join(self._body) + "</hs:sec>"
        )

    def save(self, path: str | Path, title: str | None = None) -> Path:
        out = Path(path)
        (self.root / "Contents" / "header.xml").write_text(self.header, encoding="utf-8")
        (self.root / "Contents" / "section0.xml").write_text(
            self._section_xml(), encoding="utf-8"
        )

        if title:
            hpf = self.root / "Contents" / "content.hpf"
            if hpf.is_file():
                t = hpf.read_text(encoding="utf-8")
                t = re.sub(
                    r"(<opf:title>).*?(</opf:title>)", rf"\g<1>{esc(title)}\g<2>", t
                )
                t = re.sub(r"(<dc:title>).*?(</dc:title>)", rf"\g<1>{esc(title)}\g<2>", t)
                hpf.write_text(t, encoding="utf-8")

        files = sorted(
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file()
        )
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            # mimetype이 첫 엔트리여야 하고 비압축이어야 한다
            zf.write(self.root / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
            for rel in files:
                if rel == "mimetype":
                    continue
                mode = (
                    zipfile.ZIP_STORED if rel in STORED_ENTRIES else zipfile.ZIP_DEFLATED
                )
                zf.write(self.root / rel, rel, compress_type=mode)
        return out

    def close(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def markdown_to_hwpx(md_text: str, output: str | Path, title: str | None = None) -> Path:
    """간단한 마크다운을 HWPX로 옮긴다.

    지원: #~#### 제목, | 표 |, - 목록, 빈 줄, 일반 문단.
    """
    doc = HwpxDoc()
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            doc.add_paragraph("")
            i += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            doc.add_heading(
                heading.group(2),
                size={1: 16, 2: 14, 3: 12, 4: 11}[level],
                align="CENTER" if level == 1 else "LEFT",
            )
            i += 1
            continue

        if line.lstrip().startswith("|") and line.rstrip().endswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows = []
            for row in block:
                if re.match(r"^\|[\s:\-|]+\|$", row):  # 구분선
                    continue
                cells = [c.strip() for c in row.strip("|").split("|")]
                rows.append(cells)
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [""] * (width - len(r)) for r in rows]
                doc.add_table(rows, header=True)
            continue

        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        if bullet:
            doc.add_paragraph(f"- {bullet.group(1)}", left=1000)
            i += 1
            continue

        doc.add_paragraph(line)
        i += 1

    out = doc.save(output, title=title)
    doc.close()
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="마크다운을 HWPX로 변환한다")
    ap.add_argument("input", help="마크다운 파일 (- 이면 표준 입력)")
    ap.add_argument("-o", "--output", required=True, help="출력 .hwpx 경로")
    ap.add_argument("--title", help="문서 제목 메타데이터")
    a = ap.parse_args()

    import sys

    text = sys.stdin.read() if a.input == "-" else Path(a.input).read_text(encoding="utf-8")
    p = markdown_to_hwpx(text, a.output, a.title)
    print(f"생성: {p}")
