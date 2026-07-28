#!/usr/bin/env python3
"""기존 HWPX 편집 — 표준 라이브러리만 사용한다.

양식 파일의 텍스트를 바꾸거나 표 행을 늘릴 때 쓴다. 문단·런 구조를 건드리지
않고 ZIP 안의 XML 문자열을 직접 다루므로 서식이 보존된다.

사용:
    python hwpx_edit.py in.hwpx -o out.hwpx --replace "{{이름}}=홍길동" --replace "{{날짜}}=2026-07-28"
    python hwpx_edit.py in.hwpx -o out.hwpx --list-text
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

STORED_ENTRIES = ("mimetype", "version.xml")
TEXT_PARTS = ("Contents/", "Preview/PrvText.txt")


def _is_editable(name: str) -> bool:
    return name.endswith((".xml", ".hpf")) or name == "Preview/PrvText.txt"


def read_texts(path: str | Path) -> list[str]:
    """문서의 <hp:t> 텍스트를 등장 순서대로 뽑는다(표 셀 포함)."""
    out: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            if name.startswith("Contents/section") and name.endswith(".xml"):
                xml = zf.read(name).decode("utf-8", "replace")
                for m in re.finditer(r"<hp:t>(.*?)</hp:t>", xml, re.S):
                    t = _unescape(m.group(1))
                    if t.strip():
                        out.append(t)
    return out


def _unescape(s: str) -> str:
    return (
        s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
    )


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def replace_text(
    src: str | Path,
    dst: str | Path,
    mapping: dict[str, str],
    *,
    strip_linesegs: bool = True,
) -> dict:
    """ZIP 전체에서 문자열을 치환한다.

    표 셀 안이든 머리말이든 위치와 무관하게 바뀐다. 치환 후에는 줄바꿈 캐시
    (linesegarray)를 제거한다 — 낡은 캐시가 남으면 한컴이 해당 문단부터
    내용을 조용히 버릴 수 있다. 이 요소는 KS X 6101 스키마에 없는 한컴 확장이라
    지워도 규격 위반이 아니고, 다시 열 때 재계산된다.
    """
    src, dst = Path(src), Path(dst)
    stats = {"replaced": 0, "parts": 0, "linesegs_removed": 0}

    same = src.resolve() == dst.resolve()
    target = Path(tempfile.mkdtemp(prefix="hwpx-edit-")) / "out.hwpx" if same else dst

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        target, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if _is_editable(info.filename):
                text = data.decode("utf-8", "replace")
                before = text
                for old, new in mapping.items():
                    if not old:
                        continue
                    esc_old, esc_new = _escape(old), _escape(new)
                    count = text.count(esc_old)
                    if count:
                        text = text.replace(esc_old, esc_new)
                        stats["replaced"] += count
                    # 이스케이프되지 않은 원문도 시도(PrvText 등)
                    if old != esc_old and old in text:
                        stats["replaced"] += text.count(old)
                        text = text.replace(old, new)
                if strip_linesegs and "linesegarray" in text:
                    text, n = re.subn(
                        r"<hp:linesegarray>.*?</hp:linesegarray>", "", text, flags=re.S
                    )
                    stats["linesegs_removed"] += n
                if text != before:
                    stats["parts"] += 1
                data = text.encode("utf-8")

            # 원본의 압축 방식을 유지한다(mimetype·version.xml 비압축 보존)
            mode = (
                zipfile.ZIP_STORED
                if info.filename in STORED_ENTRIES
                else info.compress_type
            )
            zout.writestr(_clone_info(info, mode), data)

    if same:
        shutil.move(str(target), str(dst))
        shutil.rmtree(target.parent, ignore_errors=True)
    return stats


def _clone_info(info: zipfile.ZipInfo, compress_type: int) -> zipfile.ZipInfo:
    out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    out.compress_type = compress_type
    out.external_attr = info.external_attr
    out.internal_attr = info.internal_attr
    out.create_system = info.create_system
    return out


def add_table_rows(
    src: str | Path, dst: str | Path, table_index: int = 0, count: int = 1
) -> dict:
    """표 끝에 행을 복제해 추가하고 rowCnt·rowAddr·높이를 함께 보정한다.

    행만 늘리고 rowCnt를 그대로 두면 한컴이 격자를 만들지 못해 문서가 열리지
    않는다(KS X 6101 표 194).
    """
    src, dst = Path(src), Path(dst)
    same = src.resolve() == dst.resolve()
    target = Path(tempfile.mkdtemp(prefix="hwpx-row-")) / "out.hwpx" if same else dst
    stats = {"added": 0}

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        target, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(
                ".xml"
            ):
                xml = data.decode("utf-8")
                xml = _add_rows_to_xml(xml, table_index, count, stats)
                data = xml.encode("utf-8")
            mode = (
                zipfile.ZIP_STORED
                if info.filename in STORED_ENTRIES
                else info.compress_type
            )
            zout.writestr(_clone_info(info, mode), data)

    if same:
        shutil.move(str(target), str(dst))
        shutil.rmtree(target.parent, ignore_errors=True)
    return stats


def _add_rows_to_xml(xml: str, table_index: int, count: int, stats: dict) -> str:
    tables = list(re.finditer(r"<hp:tbl\b.*?</hp:tbl>", xml, re.S))
    if table_index >= len(tables):
        raise IndexError(f"표 #{table_index}가 없다 (총 {len(tables)}개)")

    m = tables[table_index]
    tbl = m.group(0)
    rows = re.findall(r"<hp:tr>.*?</hp:tr>", tbl, re.S)
    if not rows:
        raise ValueError("복제할 행이 없다")

    last = rows[-1]
    row_cnt = int(re.search(r'\browCnt="(\d+)"', tbl).group(1))
    new_rows = []
    for i in range(count):
        row = last
        new_index = row_cnt + i
        row = re.sub(r'rowAddr="\d+"', f'rowAddr="{new_index}"', row)
        row = re.sub(r"<hp:t>.*?</hp:t>", "<hp:t/>", row, flags=re.S)
        new_rows.append(row)

    tbl_new = tbl.replace(last, last + "".join(new_rows), 1)
    tbl_new = re.sub(r'\browCnt="\d+"', f'rowCnt="{row_cnt + count}"', tbl_new, count=1)

    # 표 전체 높이도 늘린다
    heights = re.findall(r'<hp:cellSz width="\d+" height="(\d+)"', last)
    if heights:
        add_h = int(heights[0]) * count
        def bump(mm: re.Match) -> str:
            return f'{mm.group(1)}{int(mm.group(2)) + add_h}"'
        tbl_new = re.sub(
            r'(<hp:sz width="\d+" widthRelTo="\w+" height=")(\d+)"', bump, tbl_new, count=1
        )

    stats["added"] += count
    return xml[: m.start()] + tbl_new + xml[m.end():]


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="HWPX 편집")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument(
        "--replace",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="치환 규칙 (여러 번 지정 가능)",
    )
    ap.add_argument("--list-text", action="store_true", help="문서의 텍스트를 나열")
    ap.add_argument("--add-rows", type=int, metavar="N", help="표에 행 N개 추가")
    ap.add_argument("--table", type=int, default=0, help="대상 표 번호 (기본 0)")
    a = ap.parse_args()

    if a.list_text:
        for i, t in enumerate(read_texts(a.input)):
            print(f"{i:3d}: {t}")
        return

    if not a.output:
        ap.error("--output이 필요하다")

    if a.add_rows:
        s = add_table_rows(a.input, a.output, a.table, a.add_rows)
        print(f"행 {s['added']}개 추가 → {a.output}")
        return

    mapping = {}
    for rule in a.replace:
        if "=" not in rule:
            ap.error(f"--replace 형식은 OLD=NEW 여야 한다: {rule}")
        old, new = rule.split("=", 1)
        mapping[old] = new
    if not mapping:
        ap.error("--replace 규칙이 없다")

    s = replace_text(a.input, a.output, mapping)
    print(
        f"{s['replaced']}건 치환, 파트 {s['parts']}개 수정, "
        f"lineseg {s['linesegs_removed']}개 제거 → {a.output}"
    )


if __name__ == "__main__":
    main()
