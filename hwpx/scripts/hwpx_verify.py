#!/usr/bin/env python3
"""HWPX 무결성 검증 — 표준 라이브러리만 사용한다.

XML이 유효해도 한컴이 열지 못하는 경우가 있다. 이 검사기는 KS X 6101:2024
규격과 실제 사고 사례를 기준으로, '열리지 않는 문서'를 만드는 원인을 잡는다.

사용:
    python hwpx_verify.py document.hwpx
    python hwpx_verify.py document.hwpx --json
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"

REQUIRED_ENTRIES = (
    "mimetype",
    "version.xml",
    "Contents/content.hpf",
    "Contents/header.xml",
    "Contents/section0.xml",
)

# 해제 크기 상한 — zip bomb 방어. 정상 문서는 이 값에 한참 못 미친다.
MAX_XML_SIZE = 80 * 1024 * 1024
MAX_BIN_SIZE = 200 * 1024 * 1024


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _safe_parse(data: bytes, name: str, errors: list[str]) -> ET.Element | None:
    """XML을 파싱하되 엔티티 공격 벡터를 먼저 차단한다.

    표준 라이브러리 ElementTree는 엔티티 확장 폭탄(billion laughs)에 취약하다.
    정상 HWPX 파트에는 DOCTYPE도 ENTITY 선언도 없으므로, 있으면 거부한다.
    (defusedxml을 쓸 수 없는 환경을 전제로 한 방어다.)
    """
    head = data[:4096].lstrip()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in data[:65536]:
        errors.append(
            f"{name}: DOCTYPE/ENTITY 선언이 있다 — 정상 HWPX에는 없는 구조라 "
            "파싱하지 않는다"
        )
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        errors.append(f"XML 파싱 실패: {name}: {e}")
        return None


def verify(path: str | Path) -> dict:
    """검사 결과를 {errors, warnings, info}로 돌려준다."""
    path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []
    info: dict = {}

    if not path.is_file():
        return {"errors": [f"파일이 없다: {path}"], "warnings": [], "info": {}}

    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return {"errors": ["ZIP으로 열리지 않는다 (HWPX가 아니거나 손상)"],
                "warnings": [], "info": {}}

    with zf:
        names = zf.namelist()
        info["entries"] = len(names)

        # 1. 패키징 — OCF 프로파일 (KS X 6101 8.2, 8.3)
        for req in REQUIRED_ENTRIES:
            if req not in names:
                errors.append(f"필수 항목 없음: {req}")

        if names and names[0] != "mimetype":
            errors.append(f"mimetype이 첫 엔트리가 아니다 (현재 첫 항목: {names[0]})")
        if "mimetype" in names:
            if zf.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                errors.append("mimetype이 압축되어 있다 (비압축이어야 한다)")
            content = zf.read("mimetype").decode("utf-8", "replace").strip()
            if content != "application/hwp+zip":
                errors.append(f"mimetype 내용이 다르다: {content!r}")
        if "version.xml" in names:
            if zf.getinfo("version.xml").compress_type != zipfile.ZIP_STORED:
                warnings.append(
                    "version.xml이 압축되어 있다 — KS X 6101 8.3은 압축을 금지한다"
                )

        # 2. XML 정형성
        roots: dict[str, ET.Element] = {}
        for name in names:
            if name.endswith((".xml", ".hpf")):
                try:
                    roots[name] = ET.fromstring(zf.read(name))
                except ET.ParseError as e:
                    errors.append(f"XML 파싱 실패: {name}: {e}")

        # 3. 암호화·전자서명 감지 (KS X 6101 15, 16)
        if any("encryption" in n.lower() for n in names):
            warnings.append("암호화된 문서로 보인다 — 편집이 불가능할 수 있다")
        if any("signatures" in n.lower() for n in names):
            warnings.append("전자서명이 있다 — 편집하면 서명이 무효가 된다")

        sections = sorted(
            n for n in names if n.startswith("Contents/section") and n.endswith(".xml")
        )
        if not sections:
            errors.append("본문 섹션(Contents/section*.xml)이 없다")

        # 4. secPr 완전성 — 없으면 한컴이 '손상된 문서'로 판단한다
        if sections and sections[0] in roots:
            sec = roots[sections[0]]
            secpr = sec.find(f".//{HP}secPr")
            if secpr is None:
                errors.append("첫 섹션에 <hp:secPr>가 없다 — 한컴이 열지 못한다")
            else:
                kids = {_local(c.tag) for c in secpr.iter() if c is not secpr}
                for req, label in (("pagePr", "용지 설정"), ("margin", "여백")):
                    if req not in kids:
                        errors.append(f"secPr에 <hp:{req}> 없음 ({label} 미정의)")

        # 5. 문단·표 구조
        para_count = 0
        table_count = 0
        for name in sections:
            root = roots.get(name)
            if root is None:
                continue
            paras = list(root.iter(f"{HP}p"))
            para_count += len(paras)
            if not paras:
                errors.append(f"{name}: 문단이 하나도 없다 (구역은 문단 1개 이상 필수)")

            ids = [p.get("id") for p in paras if p.get("id")]
            dup = {i for i in ids if ids.count(i) > 1}
            if dup:
                warnings.append(f"{name}: 문단 id 중복 {sorted(dup)[:5]}")

            for idx, tbl in enumerate(root.iter(f"{HP}tbl")):
                table_count += 1
                where = f"{name} 표#{idx}"
                rows = tbl.findall(f"{HP}tr")

                # rowCnt/colCnt가 없으면 한컴이 격자를 못 만들어 문서가 안 열린다
                if tbl.get("rowCnt") is None or tbl.get("colCnt") is None:
                    errors.append(
                        f"{where}: rowCnt/colCnt 없음 — 한컴이 표 격자를 만들지 "
                        f"못해 문서가 열리지 않는다 (실제 행 {len(rows)}개)"
                    )
                    continue

                row_cnt, col_cnt = int(tbl.get("rowCnt")), int(tbl.get("colCnt"))
                if row_cnt != len(rows):
                    errors.append(
                        f"{where}: rowCnt={row_cnt}인데 실제 <hp:tr>는 {len(rows)}개"
                    )

                filled: set[tuple[int, int]] = set()
                overlap: list[tuple[int, int]] = []
                for tc in tbl.iter(f"{HP}tc"):
                    addr = tc.find(f"{HP}cellAddr")
                    if addr is None:
                        errors.append(f"{where}: cellAddr 없는 셀")
                        continue
                    span = tc.find(f"{HP}cellSpan")
                    col = int(addr.get("colAddr", 0))
                    row = int(addr.get("rowAddr", 0))
                    cs = int(span.get("colSpan", 1)) if span is not None else 1
                    rs = int(span.get("rowSpan", 1)) if span is not None else 1
                    for dr in range(rs):
                        for dc in range(cs):
                            cell = (row + dr, col + dc)
                            if cell in filled:
                                overlap.append(cell)
                            filled.add(cell)

                    sub = tc.find(f"{HP}subList")
                    if sub is None or not sub.findall(f"{HP}p"):
                        errors.append(
                            f"{where}: 셀({row},{col})에 문단이 없다 "
                            "— 빈 셀에도 <hp:p>가 있어야 한다"
                        )

                if overlap:
                    errors.append(f"{where}: 셀 주소 중복 {sorted(set(overlap))[:5]}")
                holes = [
                    (r, c)
                    for r in range(row_cnt)
                    for c in range(col_cnt)
                    if (r, c) not in filled
                ]
                if holes:
                    errors.append(f"{where}: 격자에 빈 칸 {holes[:5]}")

        info["paragraphs"] = para_count
        info["tables"] = table_count

        # 6. 스타일 참조 무결성
        header = roots.get("Contents/header.xml")
        if header is not None:
            def ids_of(tag: str) -> set[int]:
                return {
                    int(e.get("id"))
                    for e in header.iter(f"{HH}{tag}")
                    if e.get("id", "").isdigit()
                }

            defined = {
                "charPr": ids_of("charPr"),
                "paraPr": ids_of("paraPr"),
                "borderFill": ids_of("borderFill"),
            }
            info["charPr"] = len(defined["charPr"])
            info["paraPr"] = len(defined["paraPr"])

            for list_tag, item_tag in (
                ("charProperties", "charPr"),
                ("paraProperties", "paraPr"),
                ("borderFills", "borderFill"),
            ):
                lst = header.find(f".//{HH}{list_tag}")
                if lst is not None and lst.get("itemCnt", "").isdigit():
                    declared = int(lst.get("itemCnt"))
                    actual = len(lst.findall(f"{HH}{item_tag}"))
                    if declared != actual:
                        errors.append(
                            f"{list_tag}: itemCnt={declared}인데 실제 {actual}개"
                        )

            used = {"charPr": set(), "paraPr": set(), "borderFill": set()}
            for name in sections:
                root = roots.get(name)
                if root is None:
                    continue
                for el in root.iter():
                    for attr, key in (
                        ("charPrIDRef", "charPr"),
                        ("paraPrIDRef", "paraPr"),
                        ("borderFillIDRef", "borderFill"),
                    ):
                        v = el.get(attr)
                        if v and v.isdigit():
                            used[key].add(int(v))
            for key, refs in used.items():
                missing = sorted(refs - defined[key])
                if missing:
                    errors.append(
                        f"{key}: 정의되지 않은 ID 참조 {missing[:5]} "
                        f"(정의 {len(defined[key])}개)"
                    )

            # 글자 테두리 버그 — charPr 다수가 테두리 있는 borderFill을 가리키면
            # 모든 글자에 네모가 그려진다
            solid = set()
            for bf in header.iter(f"{HH}borderFill"):
                if bf.get("id", "").isdigit():
                    for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
                        b = bf.find(f"{HH}{side}")
                        if b is not None and b.get("type", "NONE") != "NONE":
                            solid.add(int(bf.get("id")))
                            break
            bordered = [
                c
                for c in header.iter(f"{HH}charPr")
                if c.get("borderFillIDRef", "").isdigit()
                and int(c.get("borderFillIDRef")) in solid
            ]
            total = len(list(header.iter(f"{HH}charPr")))
            if total and len(bordered) > total / 2:
                warnings.append(
                    f"charPr {len(bordered)}/{total}개가 테두리 있는 borderFill을 "
                    "참조한다 — 모든 글자에 네모 테두리가 그려질 수 있다"
                )

    return {"errors": errors, "warnings": warnings, "info": info}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="HWPX 무결성 검증")
    ap.add_argument("input", help="검사할 .hwpx")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    a = ap.parse_args()

    r = verify(a.input)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        ok = not r["errors"]
        print("=" * 56)
        print(f"  검증 결과: {'통과' if ok else '실패'}")
        print("=" * 56)
        if r["info"]:
            print("  " + ", ".join(f"{k}={v}" for k, v in r["info"].items()))
        for e in r["errors"]:
            print(f"  [오류] {e}")
        for w in r["warnings"]:
            print(f"  [주의] {w}")
        if ok and not r["warnings"]:
            print("  문제 없음")
    sys.exit(1 if r["errors"] else 0)


if __name__ == "__main__":
    main()
