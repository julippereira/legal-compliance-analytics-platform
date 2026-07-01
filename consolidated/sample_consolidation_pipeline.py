"""
Sample Consolidation Pipeline

Demonstrates:

- Multi-source integration
- Schema harmonization
- Data quality processing
- Attribute standardization
- Deduplication
- Analytics-ready dataset creation

This example uses anonymized datasets for
portfolio and educational purposes.
"""

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# ==============================================================================
# CONFIGURATION
# ==============================================================================

HISTORICAL_TABLE = "catalog.schema.historical_dataset"

API_TABLE = "catalog.schema.api_dataset"

TARGET_TABLE = "catalog.schema.consolidated_dataset"

# ==============================================================================
# DATA CLEANSING
# ==============================================================================

def clean_dataframe(df):

    for c in df.columns:

        if dict(df.dtypes)[c] == "string":

            df = df.withColumn(
                c,
                F.when(
                    F.trim(F.col(c)) == "",
                    None
                ).otherwise(
                    F.trim(F.col(c))
                )
            )

    return df

# ==============================================================================
# LOAD SOURCES
# ==============================================================================

historical_df = spark.read.table(HISTORICAL_TABLE)

api_df = spark.read.table(API_TABLE)

# ==============================================================================
# SOURCE PREPARATION
# ==============================================================================

historical_df = (
    historical_df
    .withColumn(
        "data_source",
        F.lit("HISTORICAL")
    )
)

api_df = (
    api_df
    .withColumn(
        "data_source",
        F.lit("API")
    )
)

# ==============================================================================
# CONSOLIDATION
# ==============================================================================

consolidated_df = (
    historical_df
    .unionByName(
        api_df,
        allowMissingColumns=True
    )
)

# ==============================================================================
# DATA QUALITY
# ==============================================================================

consolidated_df = clean_dataframe(
    consolidated_df
)

# ==============================================================================
# TIME DIMENSIONS
# ==============================================================================

if "event_date" in consolidated_df.columns:

    consolidated_df = (
        consolidated_df
        .withColumn(
            "year",
            F.year("event_date")
        )
        .withColumn(
            "month",
            F.month("event_date")
        )
        .withColumn(
            "year_month",
            F.date_format(
                "event_date",
                "yyyy-MM"
            )
        )
    )

# ==============================================================================
# DEDUPLICATION
# ==============================================================================

if "record_id" in consolidated_df.columns:

    window_spec = (
        Window
        .partitionBy("record_id")
        .orderBy(
            F.col("_ingestion_timestamp").desc()
        )
    )

    consolidated_df = (
        consolidated_df
        .withColumn(
            "_row_num",
            F.row_number().over(window_spec)
        )
        .filter(
            F.col("_row_num") == 1
        )
        .drop("_row_num")
    )

# ==============================================================================
# WRITE DELTA
# ==============================================================================

(
    consolidated_df.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(TARGET_TABLE)
)

print("Consolidation pipeline completed.")
