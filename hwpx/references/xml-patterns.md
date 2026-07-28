# HWPX XML 구조와 조립 패턴

스크립트로 안 되는 작업을 손으로 해야 할 때 참고한다. 아래 구조는 한컴이 실제로 출력하는 형태이며, 표준 문서의 예시와 다른 부분은 **실물 쪽을 따랐다**.

## 파일 구성

```
문서.hwpx (ZIP)
├── mimetype                 "application/hwp+zip" — 첫 엔트리, 비압축
├── version.xml              비압축 (KS X 6101 8.3)
├── settings.xml
├── META-INF/
│   ├── container.xml
│   ├── container.rdf
│   └── manifest.xml
├── Preview/{PrvImage.png, PrvText.txt}
└── Contents/
    ├── content.hpf          파트 목록(OPF) + 메타데이터
    ├── header.xml           글꼴·글자모양·문단모양·테두리 정의
    └── section0.xml         본문
```

## 네임스페이스

| 접두사 | URI |
|---|---|
| `hp` | `http://www.hancom.co.kr/hwpml/2011/paragraph` |
| `hs` | `http://www.hancom.co.kr/hwpml/2011/section` |
| `hh` | `http://www.hancom.co.kr/hwpml/2011/head` |
| `hc` | `http://www.hancom.co.kr/hwpml/2011/core` |
| `hp10` | `http://www.hancom.co.kr/hwpml/2016/paragraph` |

표준 2024판은 `owpml.org/owpml/2024/*`를 규정하지만 **한컴 실물은 2011 URI를 쓴다.** 실물을 따라야 열린다.

## section0.xml

첫 문단에 `secPr`(구역 설정)과 `colPr`(단 설정)이 있어야 한다. 없으면 한컴이 '손상된 문서'로 판단한다.

```xml
<hp:p id="1" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0">
    <hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000"
              tabStopVal="4000" tabStopUnit="HWPUNIT" outlineShapeIDRef="1"
              memoShapeIDRef="0" textVerticalWidthHead="0" masterPageCnt="0">
      <hp:grid .../><hp:startNum .../><hp:visibility .../><hp:lineNumberShape .../>
      <hp:pagePr landscape="WIDELY" width="59528" height="84186" gutterType="LEFT_ONLY">
        <hp:margin header="4252" footer="4252" gutter="0"
                   left="8504" right="8504" top="5668" bottom="4252"/>
      </hp:pagePr>
      <hp:footNotePr>...</hp:footNotePr><hp:endNotePr>...</hp:endNotePr>
    </hp:secPr>
    <hp:ctrl><hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="1"
                       sameSz="1" sameGap="0"/></hp:ctrl>
  </hp:run>
</hp:p>
```

일반 문단:

```xml
<hp:p id="고유정수" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
  <hp:run charPrIDRef="0"><hp:t>내용</hp:t></hp:run>
</hp:p>
```

빈 줄은 `<hp:t/>`. 쪽 나눔은 `pageBreak="1"`. 한 문단에 서식이 다른 여러 `run`을 둘 수 있다.

## 표

```xml
<hp:p ...><hp:run charPrIDRef="0">
  <hp:tbl id="고유정수" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM"
          textFlow="BOTH_SIDES" lock="0" dropcapstyle="None"
          pageBreak="CELL" repeatHeader="1"
          rowCnt="2" colCnt="2"          <!-- 필수. 없으면 문서가 안 열린다 -->
          cellSpacing="0" borderFillIDRef="2" noAdjust="0">
    <hp:sz width="42520" widthRelTo="ABSOLUTE" height="2400"
           heightRelTo="ABSOLUTE" protect="0"/>
    <hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0"
            holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN"
            vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>
    <hp:outMargin left="0" right="0" top="0" bottom="0"/>
    <hp:inMargin left="510" right="510" top="141" bottom="141"/>
    <hp:tr>
      <hp:tc name="" header="1" hasMargin="0" protect="0" editable="0" dirty="0"
             borderFillIDRef="2">
        <hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER"
                    linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0"
                    hasTextRef="0" hasNumRef="0">
          <hp:p ...><hp:run charPrIDRef="0"><hp:t>머리칸</hp:t></hp:run></hp:p>
        </hp:subList>
        <hp:cellAddr colAddr="0" rowAddr="0"/>
        <hp:cellSpan colSpan="1" rowSpan="1"/>
        <hp:cellSz width="21260" height="1200"/>
        <hp:cellMargin left="510" right="510" top="141" bottom="141"/>
      </hp:tc>
      <!-- 나머지 셀 -->
    </hp:tr>
  </hp:tbl>
  <hp:t/>        <!-- 표 뒤에 빈 텍스트 노드 -->
</hp:run></hp:p>
```

- `tc`의 자식 순서는 **subList → cellAddr → cellSpan → cellSz → cellMargin**
- `cellAddr`은 0부터. 병합하면 `cellSpan`으로 표시하고, 가려진 자리에는 `tc`를 두지 않는다
- 열 너비 합 = 본문 폭(42520)
- `pageBreak`: `CELL`(기본) / `TABLE`(셀은 안 나눔) / `NONE`(표 전체가 다음 쪽으로)

### 표가 쪽 경계에서 잘릴 때

`pageBreak="NONE"`으로 바꾸면 표가 통째로 다음 쪽으로 넘어간다. 긴 표는 `TABLE` + `repeatHeader="1"`이 낫다. 표 앞 제목이 함께 넘어가게 하려면 그 문단의 paraPr에 `keepWithNext="1"`을 준다.

## header.xml

### 글자 모양

```xml
<hh:charProperties itemCnt="7">
  <hh:charPr id="0" height="1000" textColor="#000000" shadeColor="none"
             useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="2">
    <hh:fontRef hangul="1" latin="1" hanja="1" japanese="1" other="1" symbol="1" user="1"/>
    <hh:ratio hangul="100" .../>
    <hh:spacing hangul="0" .../>
    <hh:relSz hangul="100" .../>
    <hh:offset hangul="0" .../>
    <hh:bold/>                                   <!-- 있으면 굵게 -->
    <hh:underline type="NONE" shape="SOLID" color="#000000"/>
    <hh:strikeout shape="NONE" color="#000000"/>
    <hh:outline type="NONE"/>
    <hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/>
  </hh:charPr>
</hh:charProperties>
```

- `height`는 HWPUNIT (1000 = 10pt)
- `fontRef`의 값은 **글꼴 이름이 아니라 fontface 목록의 id**
- 하위 순서: fontRef → ratio → spacing → relSz → offset → italic → bold → underline → strikeout → outline → shadow → emboss → engrave → supscript → subscript
- `italic`·`bold`·`emboss`·`engrave`·`supscript`·`subscript`는 **빈 요소이며 존재만으로 켜진다.** 끄려면 넣지 않는다

### 문단 모양

```xml
<hh:paraPr id="0" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="1"
           suppressLineNumbers="0" checked="0" textDir="LTR">
  <hh:align horizontal="JUSTIFY" vertical="BASELINE"/>
  <hh:heading type="NONE" idRef="0" level="0"/>
  <hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="KEEP_WORD"
                   widowOrphan="0" keepWithNext="0" keepLines="0"
                   pageBreakBefore="0" lineWrap="BREAK"/>
  <hh:autoSpacing eAsianEng="0" eAsianNum="0"/>
  <hh:margin>
    <hc:intent value="0" unit="HWPUNIT"/>   <!-- 양수 들여쓰기, 음수 내어쓰기 -->
    <hc:left value="0" unit="HWPUNIT"/>
    <hc:right value="0" unit="HWPUNIT"/>
    <hc:prev value="0" unit="HWPUNIT"/>     <!-- 문단 위 간격 -->
    <hc:next value="0" unit="HWPUNIT"/>     <!-- 문단 아래 간격 -->
  </hh:margin>
  <hh:lineSpacing type="PERCENT" value="160" unit="HWPUNIT"/>
  <hh:border borderFillIDRef="2" offsetLeft="0" offsetRight="0" offsetTop="0"
             offsetBottom="0" connect="0" ignoreMargin="0"/>
</hh:paraPr>
```

`margin` 하위는 **`hc:` 접두사**이고 값과 단위를 함께 쓴다. `horizontal`은 JUSTIFY / LEFT / RIGHT / CENTER / DISTRIBUTE / DISTRIBUTE_SPACE.

### 테두리·배경

```xml
<hh:borderFill id="2" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
  <hh:slash type="NONE" Crooked="0" isCounter="0"/>
  <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
  <hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>
  <hh:rightBorder .../><hh:topBorder .../><hh:bottomBorder .../>
  <hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>
  <hh:fillBrush><hc:winBrush faceColor="#FFFFFF" hatchColor="#999999" alpha="0"/></hh:fillBrush>
</hh:borderFill>
```

면 채우기는 `hc:winBrush`다(`windowBrush`가 아니다). 선 굵기는 `"0.12 mm"`처럼 단위를 붙인 문자열이고 값은 0.1/0.12/0.15/0.2/0.25/0.3/0.4/0.5/0.6/0.7/1.0/1.5/2.0/3.0/4.0/5.0 중 하나다.

## ID 규칙

- 문단·표 `id`는 문서 안에서 고유한 정수
- `charPrIDRef`·`paraPrIDRef`·`borderFillIDRef`는 header.xml에 **정의된 id만** 가리켜야 한다
- 목록에 항목을 추가하면 `itemCnt`도 함께 올린다
- **새 charPr/paraPr은 목록 끝에만 추가한다** — 한컴이 순서로 해석하므로 중간 삽입은 뒤쪽 서식을 전부 밀어버린다
