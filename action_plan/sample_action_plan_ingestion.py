"""
Sample Action Plan Ingestion Pipeline

Demonstrates:

- REST API extraction
- Pagination
- Action plan tracking
- Data cleansing
- Date normalization
- Delta Lake persistence

This example uses fictional endpoints
and anonymized structures.
"""

import re
import unicodedata

import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pyspark.sql import functions as F
from pyspark.sql.types import *

# ==============================================================================
# CONFIGURATION
# ==============================================================================

BASE_URL = "https://api.example.com/v1/action-plans"

TARGET_TABLE = "catalog.schema.action_plan_dataset"

API_KEY = "sample_api_key"

# ==============================================================================
# HELPERS
# ==============================================================================

def normalize_column(column_name):

    column_name = unicodedata.normalize(
        "NFKD",
        str(column_name)
    )

    column_name = (
        column_name.encode(
            "ASCII",
            "ignore"
        ).decode("utf-8")
    )

    column_name = column_name.lower()

    column_name = re.sub(
        r"[^a-z0-9]",
        "_",
        column_name
    )

    return re.sub(
        r"_+",
        "_",
        column_name
    ).strip("_")

def create_session():

    session = requests.Session()

    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504
        ]
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session.mount(
        "https://",
        adapter
    )

    return session

# ==============================================================================
# EXTRACTION
# ==============================================================================

session = create_session()

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

records = []

page = 0

while True:

    response = session.get(
        f"{BASE_URL}?page={page}",
        headers=headers
    )

    if response.status_code != 200:
        break

    payload = response.json()

    if not payload:
        break

    records.extend(payload)

    page += 1

# ==============================================================================
# NORMALIZATION
# ==============================================================================

all_columns = set()

for row in records:
    all_columns.update(row.keys())

schema_columns = sorted(
    [
        normalize_column(c)
        for c in all_columns
    ]
)

schema = StructType([
    StructField(
        c,
        StringType(),
        True
    )
    for c in schema_columns
])

normalized_rows = []

for row in records:

    record = {
        c: None
        for c in schema_columns
    }

    for k, v in row.items():

        record[
            normalize_column(k)
        ] = str(v) if v else None

    normalized_rows.append(record)

df = spark.createDataFrame(
    normalized_rows,
    schema=schema
)

# ==============================================================================
# DATE STANDARDIZATION
# ==============================================================================

date_columns = [
    "start_date",
    "target_date",
    "completion_date"
]

for c in date_columns:

    if c in df.columns:

        df = df.withColumn(
            c,
            F.coalesce(
                F.to_timestamp(c, "yyyy-MM-dd"),
                F.to_timestamp(c, "dd/MM/yyyy")
            )
        )

# ==============================================================================
# METADATA
# ==============================================================================

df = (
    df
    .withColumn(
        "data_source",
        F.lit("API")
    )
    .withColumn(
        "_ingestion_timestamp",
        F.current_timestamp()
    )
)

# ==============================================================================
# WRITE DELTA
# ==============================================================================

(
    df.write
      .format("delta")
      .mode("overwrite")
      .option("overwriteSchema", "true")
      .saveAsTable(TARGET_TABLE)
)

print("Action Plan ingestion pipeline completed.")
