# hwpx-skills

한글(한컴오피스) **HWPX 문서를 만들고 편집하고 검증하는 Claude 스킬**이다. claude.ai 웹에 업로드해서 쓴다.

한컴오피스를 설치하지 않아도 되고, 파이썬 패키지도 설치하지 않는다. **표준 라이브러리만으로 동작**한다.

## 설치

1. [`hwpx-web-skill.zip`](hwpx-web-skill.zip)을 내려받는다
2. claude.ai → 설정 → 기능(Features) → 스킬에서 zip을 업로드한다

Claude Code에서 쓰려면 `hwpx/` 폴더를 `~/.claude/skills/`에 두면 된다.

## 쓰는 법

Claude에게 그냥 말하면 된다.

```
"2026학년도 학급 운영 계획을 한글 문서로 만들어줘.
 대상은 5학년 3반, 기간은 2026년 3월부터 1년이야."

"이 hwpx 양식의 {{학교명}}을 서울초등학교로 바꿔줘"   ← .hwpx 파일 첨부
```

직접 부를 수도 있다.

```bash
# 마크다운 → HWPX
python scripts/hwpx_build.py 원고.md -o 결과.hwpx --title "문서 제목"

# 양식 채우기
python scripts/hwpx_edit.py 양식.hwpx --list-text
python scripts/hwpx_edit.py 양식.hwpx -o 완성.hwpx --replace "{{이름}}=홍길동"

# 검증
python scripts/hwpx_verify.py 결과.hwpx
python scripts/hwpx_fontcheck.py 결과.hwpx
```

파이썬에서 조립할 수도 있다.

```python
from hwpx_build import HwpxDoc

doc = HwpxDoc()
doc.add_heading("운영 계획", size=16, align="CENTER")
doc.add_paragraph("아래와 같이 계획을 수립함.")
doc.add_table([["구분", "내용"], ["기간", "2026. 3. ~ 2027. 2."]],
              header=True, page_break="NONE")
doc.save("결과.hwpx")
doc.close()
```

## 구성

```
hwpx/
├── SKILL.md                    스킬 정의와 워크플로
├── scripts/
│   ├── hwpx_build.py           생성 (마크다운 변환 + 조립 API)
│   ├── hwpx_edit.py            편집 (치환, 표 행 추가, lineseg 정리)
│   ├── hwpx_verify.py          구조 검증
│   └── hwpx_fontcheck.py       글꼴 실재 확인
├── references/
│   ├── xml-patterns.md         XML 구조와 조립 패턴
│   ├── ks-x-6101.md            국가표준 근거와 함정
│   └── writing-rules.md        공문서 문체와 기호 체계
└── templates/base/             문서 뼈대
```

## 왜 검증이 필요한가

HWPX는 XML이 유효해도 한컴이 열지 못하는 경우가 있다. 스키마는 통과하는데 의미가 깨진 상태다.

`hwpx_verify.py`는 그런 것들을 잡는다.

| 검사 | 놓치면 |
|---|---|
| 표 `rowCnt`/`colCnt` | **문서가 아예 열리지 않는다** |
| 표 격자의 구멍·중복 | 열리지 않는다 |
| `secPr`의 pagePr·margin | '손상된 문서'로 뜬다 |
| `mimetype`·`version.xml` 비압축 | 형식 위반 (KS X 6101 8.3) |
| 빈 셀의 문단 유무 | 셀에는 빈 문단이라도 있어야 한다 |
| charPr/paraPr 참조 무결성 | 서식이 깨진다 |

`hwpx_fontcheck.py`는 다른 종류의 문제를 본다. 문서가 참조하는 글꼴이 시스템에 없으면 한컴이 임의로 대체하는데, **문서는 정상적으로 열리기 때문에** 자간과 줄 수가 달라져 쪽 나눔이 밀려도 알아채기 어렵다. TTF/TTC의 name 테이블을 직접 읽어 확인한다.

## 알아둘 것

- **표에는 `rowCnt`/`colCnt`가 반드시 있어야 한다.** 없으면 한컴이 격자를 만들지 못해 문서가 열리지 않는다
- **글자·문단 모양은 목록 맨 끝에만 추가한다.** 한컴은 이들을 id가 아니라 목록 내 순서로 해석하므로, 중간에 끼우면 그 뒤 서식이 전부 한 칸씩 밀린다
- **굵게·기울임은 요소의 존재로 켜진다.** `<hh:bold/>`가 있으면 굵은 것이고, `type="NONE"`을 붙여 나열하면 양각·위첨자가 실제로 적용된다
- **값과 단위는 함께 쓴다.** `unit`을 빼면 CHAR(1글자=500 HWPUNIT)로 해석돼 값이 500배가 된다
- **편집 후 `linesegarray`는 지운다.** 줄바꿈 위치 캐시라서, 내용이 바뀐 뒤 낡은 캐시가 남으면 한컴이 그 문단부터 내용을 조용히 버린다

이 규칙들은 KS X 6101:2024 원문(414쪽)을 읽고 한컴 실제 출력과 대조해 정리했다. 근거 조항은 [`references/ks-x-6101.md`](hwpx/references/ks-x-6101.md)에 있다. 표준 문서와 한컴 구현이 어긋나는 지점도 함께 정리해 두었다 — 그런 경우 **실물이 정답**이다.

## 검증 방식

산출물은 실제 한컴오피스로 열어 PDF까지 변환해 확인했다. 구조 검사 통과만으로는 "열린다"를 보장하지 못한다.

## 라이선스

MIT
