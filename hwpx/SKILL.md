---
name: hwpx
description: 한글(한컴오피스) HWPX 문서를 만들고 편집하고 검증한다. '한글 문서', 'hwpx', '한글파일', '보고서', '공문', '기안문', '회의록', '계획서'를 한글 형식으로 작성하거나 기존 .hwpx 양식을 채워 달라고 할 때 사용한다. 한컴오피스 설치나 외부 패키지 없이 동작한다.
---

# HWPX 문서 생성·편집·검증

HWPX는 한컴오피스 한글의 개방형 문서 형식이다. 실체는 **ZIP 안에 든 XML 묶음**이며 국가표준 KS X 6101:2024(OWPML)를 따른다.

이 스킬은 **파이썬 표준 라이브러리만으로** 동작한다. `pip install`이 불가능한 환경을 전제로 만들었으므로 `python-hwpx`나 `lxml`을 설치하려 하지 말 것.

## 무엇부터 할지

```
사용자가 .hwpx 양식을 올렸다          → 워크플로 B (양식 채우기)
"보고서/공문/계획서를 한글로 써줘"     → 워크플로 A (새로 만들기)
"이 hwpx 내용 알려줘"                → scripts/hwpx_edit.py --list-text
"만든 문서가 제대로 됐는지"           → 워크플로 C (검증)
```

**양식 파일이 있으면 무조건 그 양식을 쓴다.** 새로 만들어 흉내내지 않는다. 관공서 양식은 칸 위치와 서식이 규정이라, 비슷하게 만든 문서는 반려된다.

---

## 워크플로 A — 새 문서 만들기

마크다운이 이미 있으면 한 줄이면 된다.

```bash
python scripts/hwpx_build.py 원고.md -o 결과.hwpx --title "문서 제목"
```

세밀하게 짜야 하면 파이썬에서 직접 조립한다.

```python
import sys; sys.path.insert(0, "scripts")
from hwpx_build import HwpxDoc

doc = HwpxDoc()
doc.add_heading("2026학년도 운영 계획", size=16, align="CENTER")
doc.add_paragraph("")                                  # 빈 줄
doc.add_paragraph("아래와 같이 계획을 수립함.")
doc.add_heading("1. 개요", size=12)
doc.add_table(
    [["구분", "내용"], ["기간", "2026. 3. ~ 2027. 2."]],
    header=True,
    page_break="NONE",      # 표가 쪽 경계에서 쪼개지지 않게
)
doc.add_paragraph("- 세부 항목", left=1000)             # 들여쓴 목록
doc.save("결과.hwpx", title="운영 계획")
doc.close()
```

`add_paragraph`의 주요 인자: `size_pt`, `bold`, `align`(JUSTIFY/LEFT/RIGHT/CENTER), `color`, `font`, `left`(왼쪽 여백), `indent`(들여쓰기, 음수면 내어쓰기), `page_break`.

**만든 다음에는 반드시 워크플로 C로 검증한다.**

---

## 워크플로 B — 양식 채우기

기존 문서의 서식을 건드리지 않고 텍스트만 바꾼다.

```bash
# 1. 무엇이 들어 있는지 먼저 본다 (표 안 텍스트도 나온다)
python scripts/hwpx_edit.py 양식.hwpx --list-text

# 2. 치환
python scripts/hwpx_edit.py 양식.hwpx -o 완성.hwpx \
    --replace "{{학교명}}=서울초등학교" \
    --replace "{{작성자}}=홍길동"

# 3. 표에 행이 더 필요하면
python scripts/hwpx_edit.py 완성.hwpx -o 완성2.hwpx --add-rows 3 --table 0
```

치환은 ZIP 전체를 대상으로 하므로 표 안이든 머리말이든 위치를 가리지 않는다. 문단·런 구조를 재작성하지 않아 글꼴과 칸 크기가 그대로 남는다.

> `<hp:t>` 노드를 순서대로 덮어쓰거나 XML을 직접 재조립하지 말 것. 런이 사라지고 서식이 깨진다.

---

## 워크플로 C — 검증 (건너뛰지 말 것)

XML이 유효해도 한컴이 못 여는 문서가 나온다. 만들거나 고친 뒤에는 반드시 돌린다.

```bash
python scripts/hwpx_verify.py 결과.hwpx
python scripts/hwpx_fontcheck.py 결과.hwpx      # 글꼴이 실제로 있는지
```

`hwpx_verify.py`가 잡는 것:

| 검사 | 왜 |
|---|---|
| `mimetype` 첫 엔트리·비압축 | 아니면 한컴이 파일로 인식하지 않는다 |
| `version.xml` 비압축 | KS X 6101 8.3이 압축을 금지한다 |
| `secPr`의 pagePr·margin | 없으면 '손상된 문서'로 뜬다 |
| **표 `rowCnt`/`colCnt`** | **없으면 문서가 아예 열리지 않는다** |
| 표 격자의 구멍·중복 | 병합을 잘못하면 열리지 않는다 |
| 빈 셀의 문단 유무 | 셀에는 빈 문단이라도 있어야 한다 |
| charPr/paraPr 참조 무결성 | 없는 ID를 가리키면 서식이 깨진다 |
| `itemCnt`와 실제 개수 | 어긋나면 한컴이 목록을 잘못 읽는다 |

오류가 하나라도 나오면 고쳐서 다시 돌린다. 통과 전에는 사용자에게 파일을 주지 않는다.

---

## 반드시 지킬 것

1. **표에는 `rowCnt`/`colCnt`가 있어야 한다.** 빠지면 한컴이 격자를 만들지 못해 문서가 열리지 않는다. `add_table()`은 자동으로 넣는다.
2. **`mimetype`은 첫 엔트리에 비압축, `version.xml`도 비압축.** ZIP을 직접 다시 만들 때 놓치기 쉽다.
3. **글자 모양(charPr)·문단 모양(paraPr)은 목록 맨 끝에만 추가한다.** 한컴은 이들을 id가 아니라 목록 내 순서로 해석해서, 중간에 끼우면 그 뒤 모든 서식이 한 칸씩 밀린다. `ensure_char_style()`·`ensure_para_style()`을 쓰면 알아서 처리된다.
4. **굵게·기울임은 속성이 아니라 요소의 존재로 켜진다.** `<hh:bold/>`가 있으면 굵은 것이다. `type="NONE"` 같은 걸 붙여 나열하면 양각·위첨자가 실제로 적용된다.
5. **값과 단위는 함께 쓴다.** `<hc:left value="1000" unit="HWPUNIT"/>`에서 `unit`을 빼면 CHAR(1글자=500)로 해석돼 값이 500배가 된다.
6. **편집 후 `linesegarray`는 지운다.** 줄바꿈 위치 캐시인데, 내용이 바뀐 뒤 낡은 캐시가 남으면 한컴이 그 문단부터 내용을 조용히 버린다. `hwpx_edit.py`가 자동으로 제거한다.
7. **XML 특수문자는 이스케이프한다.** `&`, `<`, `>`, `"`. 스크립트의 `esc()`를 쓰면 된다.

## 단위

| 단위 | HWPUNIT |
|---|---|
| 1 pt | 100 |
| 1 mm | 283.456 |
| 1 inch | 7200 |
| 1 char | 500 |

A4 = 59528 × 84186, 본문 폭(좌우 여백 뺀) = 42520.

## 더 자세히

- XML 구조와 조립 패턴: [references/xml-patterns.md](references/xml-patterns.md)
- 국가표준 근거와 함정: [references/ks-x-6101.md](references/ks-x-6101.md)
- 공문서 문체와 기호 체계: [references/writing-rules.md](references/writing-rules.md)
