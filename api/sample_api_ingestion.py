"""
Sample API Ingestion Pipeline

Demonstrates:
- REST API extraction
- Pagination handling
- Retry strategy
- JSON normalization
- Data cleansing
- Delta Lake persistence

This example uses fictional endpoints and mock structures
for portfolio and educational purposes.
"""

import json
import re
import unicodedata

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructField,
    StructType,
    StringType
)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

BASE_URL = "https://api.example.com/v1/resources"

API_KEY = "sample_api_key"

TARGET_TABLE = "catalog.schema.api_dataset"

MAX_PAGES = 100

# ==============================================================================
# UTILITIES
# ==============================================================================

def normalize_column_name(column_name):

    column_name = unicodedata.normalize(
        "NFKD",
        str(column_name)
    )

    column_name = (
        column_name
        .encode("ASCII", "ignore")
        .decode("UTF-8")
    )

    column_name = column_name.lower()
    column_name = re.sub(r"[^a-z0-9]", "_", column_name)

    return re.sub(
        r"_+",
        "_",
        column_name
    ).strip("_")


def create_session():

    session = requests.Session()

    retry_strategy = Retry(
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
        max_retries=retry_strategy
    )

    session.mount("https://", adapter)

    return session

# ==============================================================================
# API EXTRACTION
# ==============================================================================

def fetch_data():

    session = create_session()

    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    records = []

    for page in range(MAX_PAGES):

        url = f"{BASE_URL}?page={page}"

        response = session.get(
            url,
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            break

        payload = response.json()

        if not payload:
            break

        records.extend(payload)

    return records

# ==============================================================================
# EXTRACTION
# ==============================================================================

print("Extracting data...")

records = fetch_data()

if not records:
    raise Exception("No records returned.")

# ==============================================================================
# SCHEMA DISCOVERY
# ==============================================================================

all_columns = set()

for row in records:
    all_columns.update(row.keys())

column_mapping = {
    c: normalize_column_name(c)
    for c in all_columns
}

normalized_columns = sorted(
    set(column_mapping.values())
)

schema = StructType(
    [
        StructField(
            column,
            StringType(),
            True
        )
        for column in normalized_columns
    ]
)

# ==============================================================================
# RECORD NORMALIZATION
# ==============================================================================

normalized_rows = []

for row in records:

    record = {
        column: None
        for column in normalized_columns
    }

    for key, value in row.items():

        record[
            column_mapping[key]
        ] = (
            str(value)
            if value is not None
            else None
        )

    normalized_rows.append(record)

# ==============================================================================
# DATAFRAME CREATION
# ==============================================================================

df = spark.createDataFrame(
    normalized_rows,
    schema=schema
)

# ==============================================================================
# DATA CLEANSING
# ==============================================================================

invalid_values = [
    "",
    " ",
    "n/a",
    "null"
]

df = df.select(
    [
        F.when(F.col(c).isNull(), None)
         .when(
             F.lower(
                 F.trim(F.col(c))
             ).isin(invalid_values),
             None
         )
         .otherwise(
             F.trim(F.col(c))
         )
         .alias(c)

        for c in df.columns
    ]
)

# ==============================================================================
# METADATA
# ==============================================================================

df = (
    df
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

# ==============================================================================
# VALIDATION
# ==============================================================================

print("Pipeline completed successfully.")

display(
    spark.read.table(TARGET_TABLE).limit(10)
)
