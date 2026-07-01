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

# HISTORICAL DATA INGESTION PIPELINE (SAMPLE)

import pyspark.sql.functions as F
import unicodedata
import re

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================

INPUT_FILE = "/path/to/sample_data.csv"
TARGET_TABLE = "catalog.schema.historical_dataset"

# ==============================================================================
# 2. COLUMN STANDARDIZATION
# ==============================================================================

def normalize_column_name(column_name):

    column_name = unicodedata.normalize("NFKD", column_name)
    column_name = column_name.encode("ASCII", "ignore").decode("UTF-8")

    column_name = column_name.lower()
    column_name = re.sub(r"[^a-z0-9]", "_", column_name)

    return re.sub(r"_+", "_", column_name).strip("_")

# ==============================================================================
# 3. INGESTION
# ==============================================================================

df = (
    spark.read
    .option("header", True)
    .option("sep", ";")
    .option("encoding", "UTF-8")
    .option("multiLine", True)
    .csv(INPUT_FILE)
)

df = df.toDF(*[normalize_column_name(c) for c in df.columns])

# ==============================================================================
# 4. DATA CLEANSING
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
            F.lower(F.trim(F.col(c))).isin(invalid_values),
            None
        )
        .otherwise(F.trim(F.col(c)))
        .alias(c)
        for c in df.columns
    ]
)

# ==============================================================================
# 5. TEMPORAL STANDARDIZATION
# ==============================================================================

date_columns = [
    "event_date",
    "review_date",
    "target_date"
]

for column_name in date_columns:

    if column_name in df.columns:

        df = df.withColumn(
            column_name,
            F.coalesce(
                F.to_timestamp(column_name, "yyyy-MM-dd"),
                F.to_timestamp(column_name, "dd/MM/yyyy")
            )
        )

# ==============================================================================
# 6. ENTITY STANDARDIZATION
# ==============================================================================

if "business_unit" in df.columns:

    df = df.withColumn(
        "entity_code",
        F.when(F.upper(F.col("business_unit")).contains("SITE_A"), "A")
         .when(F.upper(F.col("business_unit")).contains("SITE_B"), "B")
         .otherwise("UNK")
    )

# ==============================================================================
# 7. IDENTIFIER GENERATION
# ==============================================================================

key_columns = [
    "business_unit",
    "category",
    "process",
    "reference"
]

df = df.withColumn(

    "record_id",

    F.substring(

        F.md5(
            F.concat_ws(
                "||",
                *[
                    F.coalesce(
                        F.lower(F.trim(F.col(c))),
                        F.lit("")
                    )
                    for c in key_columns
                ]
            )
        ),

        1,
        16
    )
)

# ==============================================================================
# 8. METADATA
# ==============================================================================

df = df.withColumn(
    "_ingestion_timestamp",
    F.current_timestamp()
)

# ==============================================================================
# 9. PERSISTENCE
# ==============================================================================

(
    df.write
      .format("delta")
      .mode("overwrite")
      .option("overwriteSchema", "true")
      .saveAsTable(TARGET_TABLE)
)

# ==============================================================================
# 10. VALIDATION
# ==============================================================================

display(
    spark.read.table(TARGET_TABLE).limit(10)
)
