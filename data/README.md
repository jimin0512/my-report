# 여기에 내 데이터를 넣습니다

## 7주차에 받은 통신사 데이터를 쓰려면

7주차 실습 폴더의 `.parquet` 9개를 **이 폴더로 복사**하십시오.

```
customers.parquet   sessions.parquet   funnel_events.parquet
campaigns.parquet   ad_spend.parquet   experiments.parquet
experiment_assignments.parquet   usage_monthly.parquet
support_tickets.parquet
```

복사가 번거로우면 `core/config.py` 의 `DATA_DIR` 을 그 폴더로 바꿔도 됩니다.

## 내 데이터를 쓰려면

1. 파일을 이 폴더에 넣는다 — **parquet · csv · 엑셀** 다 됩니다
2. `core/config.py` 의 `TABLES` 에 **파일명(확장자 제외)** 을 적는다

파일이 하나뿐이어도 됩니다. 조인이 없으면 조인 함정도 없습니다.

## 왜 데이터가 비어 있는가

**내 데이터를 앱에 연결하는 것이 8주차의 첫 관문**이기 때문입니다.
데이터가 미리 들어 있으면 그 단계를 건너뛰게 됩니다.

큰 데이터는 parquet 이 훨씬 작고 빠릅니다. CSV 78MB 가 parquet 11MB 가 됩니다.

```
customers.csv 를 읽어서 data/customers.parquet 으로 저장해줘
```
