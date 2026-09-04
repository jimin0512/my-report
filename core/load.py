# -*- coding: utf-8 -*-
"""데이터 적재.

**세 가지 모드가 있고, 갈리는 곳은 이 파일뿐이다.**
계산(metrics.py)은 어느 모드에서 왔든 동일한 DataFrame을 받는다.

  로컬·원본     BigQuery에서 읽는다        (수업·개발)
  로컬·오프라인  동봉 parquet을 읽는다      (BigQuery 없이 실습)
  배포          동봉 parquet을 읽는다      (발표·공유)

dtype 최적화가 중요하다. 그냥 읽으면 393MB, 최적화하면 147MB다.
Streamlit Community Cloud 무료 한도가 1,024MB이므로 이 차이가 배포 가능 여부를 가른다.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import config as C
from core.todo import todo


def to_dt(s: pd.Series) -> pd.Series:
    """날짜 컬럼을 datetime으로 바꾼다.

    optimize()가 문자열을 category로 바꿔놓기 때문에 그냥 to_datetime을 호출하면
    비교·집계에서 터진다. astype(str)로 되돌린 뒤 변환한다.
    """
    return pd.to_datetime(s.astype(str), errors="coerce")


def optimize(df: pd.DataFrame) -> pd.DataFrame:
    """메모리를 줄인다. 배포본이 한도 안에 들어가려면 반드시 필요하다."""
    for col in df.columns:
        s = df[col]
        if s.dtype == "object":
            # 카디널리티가 낮은 문자열만 category로. ID 컬럼은 그대로 둔다.
            if len(s) and s.nunique(dropna=True) / len(s) < 0.5:
                df[col] = s.astype("category")
        elif str(s.dtype).startswith("int"):
            df[col] = pd.to_numeric(s, downcast="integer")
        elif str(s.dtype).startswith("float"):
            df[col] = pd.to_numeric(s, downcast="float")
    return df


def read_csv(path_or_buf) -> pd.DataFrame:
    """CSV를 읽는다. **한글 인코딩을 자동으로 맞춘다.**

    엑셀에서 저장한 CSV는 인코딩이 두 갈래다.

        "CSV UTF-8 (쉼표로 분리)"   utf-8
        "CSV (쉼표로 분리)"         cp949   ← 이쪽을 utf-8로 읽으면 에러가 난다

    어느 쪽인지 파일만 봐서는 모르므로, utf-8로 먼저 읽고 실패하면 cp949로 다시 읽는다.
    (`utf-8-sig` 는 파일 맨 앞의 안 보이는 표시(BOM)까지 함께 처리한다)

    ★ 한글이 깨져 보이면 여기가 아니라 **파일 저장 형식**을 확인하십시오.
    """
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path_or_buf, encoding=enc)
        except UnicodeDecodeError:
            if hasattr(path_or_buf, "seek"):
                path_or_buf.seek(0)
    raise UnicodeDecodeError(
        "utf-8/cp949", b"", 0, 1,
        "CSV 인코딩을 알 수 없습니다. 엑셀에서 'CSV UTF-8' 형식으로 다시 저장해 보십시오.")


# 읽을 수 있는 형식. parquet 을 먼저 찾고, 없으면 csv · 엑셀 순으로 본다.
READERS = {
    ".parquet": pd.read_parquet,
    ".csv": read_csv,
    ".xlsx": pd.read_excel,
    ".xls": pd.read_excel,
}


@st.cache_data(show_spinner=False)
def load_table(name: str) -> pd.DataFrame:
    """테이블 하나를 읽는다. 캐시되므로 앱 수명 동안 1회만 읽는다.

    ★ 내 데이터를 data/ 에 넣고 config.TABLES 에 파일명(확장자 제외)을 적는다.
      parquet · csv · 엑셀 중 아무 형식이나 된다.

    큰 데이터는 parquet 이 훨씬 작고 빠르다. CSV 78MB 가 parquet 11MB 가 된다.

        df.to_parquet("data/내테이블.parquet")
    """
    for ext, reader in READERS.items():
        path = C.DATA_DIR / f"{name}{ext}"
        if path.exists():
            return optimize(reader(path))
    raise FileNotFoundError(
        f"{C.DATA_DIR / name} (.parquet / .csv / .xlsx) 를 찾을 수 없습니다. "
        f"내 데이터 파일을 data/ 에 넣고 config.TABLES 의 이름과 맞추십시오."
    )


def find_file(name: str):
    """테이블 이름에 맞는 파일을 찾는다. 없으면 None."""
    for ext in READERS:
        p = C.DATA_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


@st.cache_data(show_spinner=False)
def load_all() -> dict[str, pd.DataFrame]:
    """config.TABLES 의 테이블을 전부 읽는다.

    파일이 하나도 없으면 예외 대신 **안내로 멈춘다.** 화면에 무엇을 해야 하는지 뜬다.
    """
    missing = [t for t in C.TABLES if find_file(t) is None]
    if len(missing) == len(C.TABLES):
        todo("Day1 준비", "내 데이터를 연결하십시오",
             "data/ 폴더가 비어 있습니다. 7주차에 받은 parquet 을 그대로 복사하거나, "
             "내 파일(parquet · csv · 엑셀)을 넣고 config.TABLES 에 이름을 적으십시오.",
             "data/README.md 에 자세히 적어 두었습니다")
    if missing:
        todo("Day1 준비", "일부 테이블을 찾을 수 없습니다",
             "없는 파일: " + ", ".join(missing[:5])
             + (" 외" if len(missing) > 5 else "")
             + " — data/ 에 넣거나 config.TABLES 에서 빼십시오.",
             "core/config.py  TABLES")
    return {t: load_table(t) for t in C.TABLES}


def load_uploaded(files) -> dict[str, pd.DataFrame]:
    """업로드된 파일을 읽는다. **파일명이 테이블명**이어야 한다."""
    out = {}
    for f in files:
        name, _, ext = f.name.rpartition(".")
        reader = READERS.get(f".{ext.lower()}", read_csv)
        out[name] = optimize(reader(f))
    return out


def memory_mb(tables: dict[str, pd.DataFrame]) -> float:
    return sum(df.memory_usage(deep=True).sum() for df in tables.values()) / 1e6


# ── BigQuery 모드 (로컬 전용) ─────────────────────────────────────
# 배포본에서는 인증 키가 없으므로 호출되지 않는다.
# 공개 URL에 BigQuery를 직결하면 누구나 쿼리를 돌려 비용을 발생시킬 수 있다.
def load_from_bigquery(project: str, dataset: str) -> dict[str, pd.DataFrame]:
    from google.cloud import bigquery  # 로컬에만 설치되어 있으면 된다

    client = bigquery.Client(project=project)
    out = {}
    for t in C.TABLES:
        out[t] = optimize(
            client.query(f"SELECT * FROM `{project}.{dataset}.{t}`").to_dataframe()
        )
    return out
