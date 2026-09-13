from pyspark.sql import SparkSession
from pyspark.sql.functions import col, trim, lower, to_date, trunc, when, count, desc, explode, from_unixtime
from pyspark.sql.functions import sum as spark_sum


from config import CONFIG, project_path
from pathlib import Path
from logger import get_logger

from database import upsert_jobs

logger = get_logger(__name__)


SPARK_CONFIG = CONFIG["spark"]

LINKEDIN_RAW_DIR = project_path(
    CONFIG["paths"]["linkedin_raw"]
)

API_RAW_DIR = project_path(
    CONFIG["paths"]["api_raw"]
)

OUTPUT_PATH = project_path(
    CONFIG["paths"]["processed_jobs"]
)


LINKEDIN_PATH = LINKEDIN_RAW_DIR / "jobs_latest.csv"

API_PATH = API_RAW_DIR / "jobs_page_*.json"
#PROJECT_ROOT = Path(__file__).resolve().parent.parent
#
#LINKEDIN_PATH = PROJECT_ROOT / "data" / "raw" / "linkedin" / "jobs_latest.csv"
#API_PATH = PROJECT_ROOT / "data" / "raw" / "api" / "jobs_page_*.json"
#OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "jobs"


def create_spark_session():
    return (
        SparkSession.builder
        .appName(SPARK_CONFIG["app_name"])
        .master(SPARK_CONFIG["master"])
        .getOrCreate()
    )


def read_linkedin_data(spark):
    return (
        spark.read
        .option("header", True)
        .option("inferSchema", True)
        .csv(str(LINKEDIN_PATH))
    )


def read_api_data(spark):
    return (
        spark.read
        .option("multiline", "true")
        .json(str(API_PATH))
    )


def clean_linkedin_data(df):

    clean_df = (
        df
        .withColumn("job_title", trim(col("job_title")))
        .withColumn("company", trim(col("company")))
        .withColumn("location", lower(trim(col("location"))))
        .withColumn("date_posted", to_date(col("date_posted")))
    )

    clean_df = clean_df.withColumn(
        "country",
        when(
            col("location").isin("be", "belgium"),
            "belgium",
        )
        .when(
            col("location").isin(
                "nl",
                "netherlands",
                "the netherlands",
            ),
            "netherlands",
        )
        .when(
            col("location").contains("belgium"),
            "belgium",
        )
        .when(
            col("location").contains("netherlands"),
            "netherlands",
        )
        .otherwise("unknown"),
    )

    clean_df = clean_df.dropna(
        subset=["job_id","job_title", "company"]
    )

    clean_df = clean_df.dropDuplicates(["job_id"])

    #return clean_df
    return clean_df.select(
    "job_id",
    "job_title",
    "company",
    "location",
    "date_posted",
    "country",
    "job_url",
    "application_type",
    "description",
)



def filter_candidate_jobs(df):
    return (
        df
        .filter(col("description").isNotNull())
        .filter(
            ~lower(col("job_title")).rlike(
                r"\b(senior|sr\.?|lead|principal|staff|director|head)\b"
            )
        )
        .filter(
            ~lower(col("description")).rlike(
                r"\b(5\+ years|6\+ years|7\+ years|8\+ years|senior-level|senior position)\b"
            )
        )
    )


def clean_api_data(api_raw_df):

    api_jobs_df = api_raw_df.select(
        explode(col("data")).alias("job")
    )

    api_flat_df = api_jobs_df.select(
        col("job.title").alias("title"),
        col("job.company_name").alias("company_name"),
        col("job.location").alias("location"),
        col("job.created_at").alias("created_at"),
    )

    api_clean_df = (
        api_flat_df
        .withColumn(
            "job_title",
            trim(col("title")),
        )
        .withColumn(
            "company",
            trim(col("company_name")),
        )
        .withColumn(
            "location",
            lower(trim(col("location"))),
        )
        .withColumn(
            "date_posted",
            to_date(from_unixtime(col("created_at"))),
        )
    )

    api_clean_df = api_clean_df.withColumn(
        "country",
        when(
            col("location").contains("belgium"),
            "belgium",
        )
        .when(
            col("location").contains("netherlands"),
            "netherlands",
        )
        .when(
            col("location").contains("berlin")
            | col("location").contains("munich")
            | col("location").contains("münchen")
            | col("location").contains("hamburg")
            | col("location").contains("dresden"),
            "germany",
        )
        .otherwise("unknown"),
    )

    return api_clean_df.select(
        "job_title",
        "company",
        "location",
        "date_posted",
        "country",
    )


def combine_data(linkedin_df, api_df):

    combined_df = linkedin_df.unionByName(api_df)

    deduped_df = combined_df.dropDuplicates(
        [
            "job_title",
            "company",
            "location",
            "date_posted",
        ]
    )

    return deduped_df


def run_transform():

    logger.info("Starting Spark transformation")

    spark = create_spark_session()

    try:
        linkedin_raw_df = read_linkedin_data(spark)
        #api_raw_df = read_api_data(spark)

        linkedin_clean_df = clean_linkedin_data(
            linkedin_raw_df
        )

        #api_clean_df = clean_api_data(
        #    api_raw_df
        #)

        final_df = linkedin_clean_df

        # exclue SENIOR 
        before_filter = final_df.count()

        final_df = filter_candidate_jobs(final_df)

        after_filter = final_df.count()
        logger.info(
            "Junior Candidate filter: %s -> %s jobs",
            before_filter,
            after_filter,
        )

        #final_df = combine_data(
        #    linkedin_clean_df,
        #    api_clean_df,
        #)

        OUTPUT_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        (
            final_df.write
            .mode("overwrite")
            .parquet(str(OUTPUT_PATH))
        )

        #final_count = final_df.count()
        final_count = after_filter

        logger.info(
            "Spark transformation complete: %s jobs",
            final_count,
        )

        logger.info(
            "Parquet written to %s",
            OUTPUT_PATH,
        )

        rows = final_df.collect()

        jobs = [
            {
                "source": "linkedin",
                "source_job_id": str(row["job_id"]),
                "job_title": row["job_title"],
                "company": row["company"],
                "location": row["location"],
                "country": row["country"],
                "date_posted": row["date_posted"],
                "job_url": row["job_url"],
                "application_type": row["application_type"],
                "description": row["description"],
            }
            for row in rows
        ]
        
        #upsert_jobs(jobs)
        db_stats = upsert_jobs(jobs)
        #final_df.printSchema()
        #final_df.show(5, truncate=False)

        #return final_count
        return {
            "input_jobs": before_filter,
            "filtered_out": before_filter - after_filter,
            "final_jobs": final_count,
            "database": db_stats,
        }

    
    finally:
        logger.info("Stopping Spark session")
        spark.stop()


if __name__ == "__main__":
    run_transform()



#spark = (SparkSession.builder
#         .appName("JobMarketPipeline")
#         .master("local[*]")
#         .getOrCreate()
#         )
#
#df = (spark.read 
#      .option("header", True)
#      .option("inferSchema", True)
#      .csv("../data/raw/jobs_latest.csv")
#      )
#api_raw_df = (
#        spark.read.option("multiline", "true")
#        .json("../data/raw/api/jobs_page_*.json")
#        )
#api_jobs_df = (
#        api_raw_df.select(explode(col("data")).alias("job")))
#
#print("\nAPI JOBS SCHEMA")
#api_jobs_df.printSchema()

#print("\nAPI JOBS")
#api_jobs_df.show(5, truncate=True)

#api_jobs_df.select(
#    "job.title",
#    "job.company_name",
#    "job.location",
#    "job.created_at"
#).show(10, truncate=False)
#
#print("API page rows:", api_raw_df.count())
#print("API job rows:", api_jobs_df.count())

#api_flat_df = api_jobs_df.select(
#    col("job.title").alias("title"),
#    col("job.company_name").alias("company_name"),
#    col("job.location").alias("location"),
#    col("job.created_at").alias("created_at"),
#    col("job.remote").alias("remote"),
#    col("job.tags").alias("tags"),
#    col("job.job_types").alias("job_types"),
#    col("job.slug").alias("slug"),
#    col("job.url").alias("url"),
#)
#
#api_clean_df = (
#    api_flat_df
#    .withColumn("job_title", trim(col("title")))
#    .withColumn("company", trim(col("company_name")))
#    .withColumn("location", lower(trim(col("location"))))
#    .withColumn(
#        "date_posted",
#        to_date(from_unixtime(col("created_at")))
#    )
#)

#api_clean_df.select(
#    "job_title",
#    "company",
#    "location",
#    "date_posted"
#).show(10, truncate=False)

#api_clean_df = api_clean_df.withColumn(
#    "country",
#    when(
#        col("location").contains("belgium"),
#        "belgium"
#    )
#    .when(
#        col("location").contains("netherlands"),
#        "netherlands"
#    )
#    .when(
#        col("location").contains("berlin") |
#        col("location").contains("munich") |
#        col("location").contains("münchen")|
#        col("location").contains("hamburg")|
#        col("location").contains("dresden"),
#        "germany"
#    )
#    .otherwise("unknown")
#)
#
#
#api_common_df = api_clean_df.select(
#    "job_title",
#    "company",
#    "location",
#    "date_posted",
#    "country"
#)

#api_common_df.printSchema()

#api_common_df.show(20, truncate=False)
#
#print("API common rows:", api_common_df.count())

#print("\nAPI COMMON SCHEMA")
#api_common_df.printSchema()
#
#print("\nAPI COMMON DATA")
#api_common_df.show(20, truncate=False)

#print("\nAPI FLAT SCHEMA")
#api_flat_df.printSchema()
#
#print("\nAPI FLAT DATA")
#api_flat_df.show(10, truncate=False)
#
#api_flat_df.select(
#    "title",
#    "tags",
#    "job_types"
#).show(10, truncate=False)
#
#print("Exploded rows:", api_jobs_df.count())
#print("Flat rows:", api_flat_df.count())

#print("\nAPI RAW Schema")
#api_raw_df.printSchema()
#
#print("\nAPI RAW Data")
#api_raw_df.show(3, truncate=True)
#spark df is different than pandas, it can distribute operations across many workers
# while pandas processes the data mainly in ONE python process

# also , spark has LAZY evaluation, meaning thigns like filter etc done get DONE immediately when they are WRITTEn




# RAW data
#print("RAW data")
#df.show(10, truncate=True) #aka df.head() in pandas
#
#
#print("RAW schema")
#df.printSchema()



# cleaning TIME :P 

#clean_df = (
#        df
#        .withColumn("job_title", trim(col("job_title"))) #spaces
#        .withColumn("company", trim(col("company")))
#        .withColumn("location", lower(trim(col("location"))))
#        #.withColumn("role", lower(trim(col("role"))))
#        #.withColumn("loc", lower(trim(col("loc"))))
#        )
#
#clean_df = clean_df.withColumn("date_posted", to_date(col("date_posted")))


#clean_df = clean_df.withColumn("location",
#                               when(col("location").isin("be", "belgium"), "belgium")
#                               .when(col("location").isin("nl", "netherlands", "the netherlands"), "netherlands")
#                               .otherwise(col("location"))
#                               )

#clean_df = clean_df.withColumn(
#    "country",
#    when(
#        col("location").isin("be", "belgium"),
#        "belgium"
#    )
#    .when(
#        col("location").isin("nl", "netherlands", "the netherlands"),
#        "netherlands"
#    )
#    .when(
#        col("location").contains("belgium"),
#        "belgium"
#    )
#    .when(
#        col("location").contains("netherlands"),
#        "netherlands"
#    )
#    .otherwise("unknown")
#)
#
## remove rows missing given fields
#clean_df = clean_df.dropna(subset=["job_title", "company"])
#
##deduplicate
#clean_df = clean_df.dropDuplicates()

#print("CLEANED DATA")
#clean_df.show(20, truncate=False)
#
#print("CLEANED Schema")
#clean_df.printSchema()
#
#print("RAW row count:", df.count())
#print("CLEAN row count:", clean_df.count())



#print("\nJobs PER Country")
#jobs_per_country = (
#        clean_df
#        .groupBy("country")
#        .count()
#        .orderBy(desc("count"))
#    )
#jobs_per_country.show(truncate=False)


#print("\n TOP Roles")
#top_roles = (
#        clean_df
#        .groupBy("job_title")
#        .count()
#        .orderBy(desc("count"))
#    )
#top_roles.show(10, truncate=False)
#
#
#print("\n Top Companies")
#top_companies = (
#        clean_df
#        .groupBy("company")
#        .count()
#        .orderBy(desc("count"))
#    )
#top_companies.show(10, truncate=False)
#
#print("\n Jobs PER Day")
#jobs_per_day = (
#        clean_df
#        .groupBy("date_posted")
#        .count()
#        .orderBy("date_posted")
#    )
#jobs_per_day.show(7, truncate=False)
#
## now with SQL 
#
#clean_df.createOrReplaceTempView("jobs")
#
#print("\nRole DISTRIBUTION By Country")
#spark.sql("""
#          SELECT
#            country,
#            job_title,
#            COUNT(*) AS job_count 
#          FROM jobs 
#          GROUP BY country, job_title 
#          ORDER BY country, job_count DESC 
#        """).show(50, truncate=False)
#
#
## parquet 
#output_path = "../data/processed/jobs"
#clean_df.write.mode("overwrite").parquet(output_path)
#print(f"Cleaned data written to: {output_path}")
#
#
## reading back the parquet  POC
#parquet_df = spark.read.parquet(output_path)
#print("\nDATA READ BACK FROM PARQUET")
#parquet_df.show(10, truncate=False)
#parquet_df.printSchema()

#clean_df.printSchema()
#api_common_df.printSchema()

#combined_df = clean_df.unionByName(api_common_df)

#print("\nCOMBINED SCHEMA")
#combined_df.printSchema()
#
#print("\nCOMBINED DATA")
#combined_df.show(20, truncate=False)
#
#
#print("Historical rows:", clean_df.count())
#print("API rows:", api_common_df.count())
#print("Combined rows:", combined_df.count())

#deduped_df = combined_df.dropDuplicates([
#    "job_title",
#    "company",
#    "location",
#    "date_posted"
#])
#print("Combined rows:", combined_df.count())
#print("Deduplicated rows:", deduped_df.count())

#deduped_df.select([spark_sum(col(c).isNull().cast("int")).alias(c)
#                   for c in deduped_df.columns]).show()

#string_columns = [
#    "job_title",
#    "company",
#    "location",
#    "country"
#]
#
#deduped_df.select([
#    spark_sum((col(c) == "").cast("int")).alias(c)
#    for c in string_columns
#]).show()
#
#deduped_df.filter(col("location") == "").show(
#    30,
#    truncate=False
#)
#deduped_df.filter(col("location") == "") \
#    .groupBy("country") \
#    .count() \
#    .show()
#duplicate_check = (
#    deduped_df
#    .groupBy(
#        "job_title",
#        "company",
#        "location",
#        "date_posted"
#    )
#    .count()
#    .filter(col("count") > 1)
#)
#
#print("Duplicate groups:", duplicate_check.count())
#combined_count = combined_df.count()
#deduped_count = deduped_df.count()
#
#print("Combined rows:", combined_count)
#print("Final rows:", deduped_count)
#print("Duplicates removed:", combined_count - deduped_count)



#deduped_df.createOrReplaceTempView("final_jobs")

# useful queries 

# jobs per country
#spark.sql("""
#    SELECT
#        country,
#        COUNT(*) AS job_count
#    FROM final_jobs
#    GROUP BY country
#    ORDER BY job_count DESC
#""").show()
#
#
## TOP companies
#
#spark.sql("""
#    SELECT
#        company,
#        COUNT(*) AS job_count
#    FROM final_jobs
#    GROUP BY company
#    ORDER BY job_count DESC
#    LIMIT 10
#""").show(truncate=False)

#OUTPUT_PATH = "../data/processed/jobs"
#
#(
#    deduped_df.write
#    .mode("overwrite")
#    .parquet(OUTPUT_PATH)
#)
#
#final_df = spark.read.parquet(OUTPUT_PATH)
#
#print("Written rows:", final_df.count())
#final_df.printSchema()
#
#spark.stop()
