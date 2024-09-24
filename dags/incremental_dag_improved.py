from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import timedelta
from airflow.utils.dates import days_ago
import logging
from pyspark.sql.functions import col, when, to_date, max as spark_max, first, concat, lit
from pyspark.sql import SparkSession
import psycopg2
from datetime import datetime
import os

# Set up Logger
logger = logging.getLogger("airflow.task")

# Define paths
dag_path = "/opt/airflow"
processed_data_path = "/opt/airflow/processed_data"
intermediate_data = "/opt/airflow/intermediate_data"
raw_data_dir = f"{dag_path}/raw_data"

# PostgreSQL connection details
postgres_conn_details = {
    'dbname': 'airflow',
    'user': 'airflow',
    'password': 'airflow',
    'host': 'postgres',
    'port': '5432'
}

# Function to get the latest file
def get_latest_file(directory, prefix):
    files = [f for f in os.listdir(directory) if f.startswith(prefix) and f.endswith('.csv')]
    return max(files) if files else None

# Function to ensure metadata table exists
def ensure_metadata_table_exists():
    try:
        conn = psycopg2.connect(**postgres_conn_details)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata1 (
                key VARCHAR PRIMARY KEY,
                last_processed_composite_id VARCHAR
            );
        """)
        conn.commit()
        conn.close()
        logger.info("Metadata table ensured to exist.")
    except Exception as e:
        logger.error(f"Error occurred while ensuring metadata table exists: {e}")
        raise

# Function to get the last processed composite ID
def get_last_processed_id():
    try:
        ensure_metadata_table_exists()
        conn = psycopg2.connect(**postgres_conn_details)
        cursor = conn.cursor()
        cursor.execute("SELECT last_processed_composite_id FROM metadata1 WHERE key = 'last_processed_composite_id'")
        result = cursor.fetchone()
        conn.close()
        if result:
            return result[0]
        return '0_1970-01-01_0_0'  # Default if no info found
    except Exception as e:
        logger.error(f"Error occurred while fetching last processed ID: {e}")
        raise

# Function to update the last processed composite ID
def update_last_processed_id(new_id):
    try:
        ensure_metadata_table_exists()
        conn = psycopg2.connect(**postgres_conn_details)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO metadata1 (key, last_processed_composite_id) VALUES (%s, %s) 
            ON CONFLICT (key) DO UPDATE SET last_processed_composite_id = EXCLUDED.last_processed_composite_id
        """, ('last_processed_composite_id', new_id))
        conn.commit()
        conn.close()
        logger.info(f"Updated last processed composite ID successfully: {new_id}")
    except Exception as e:
        logger.error(f"Error occurred while updating last processed ID: {e}")
        raise


# Define the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retries': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

dag = DAG(
    dag_id='improved_incremental_load_dag',
    description='Improved Incremental Data Load DAG',
    schedule_interval=None,
    start_date=days_ago(1),
    default_args=default_args
)

# Define the tasks
def load_data():
    try:
        spark = SparkSession.builder.appName("Improved Incremental Load").getOrCreate()

        # Get the latest files
        booking_file = get_latest_file(raw_data_dir, 'booking_') or "booking.csv"
        client_file = get_latest_file(raw_data_dir, 'client_') or "client.csv"
        hotel_file = get_latest_file(raw_data_dir, 'hotel_') or "hotel.csv"

        # Define paths
        booking_path = os.path.join(raw_data_dir, booking_file)
        client_path = os.path.join(raw_data_dir, client_file)
        hotel_path = os.path.join(raw_data_dir, hotel_file)
        
        # Load CSV files
        booking = spark.read.option("header", True).option("delimiter", "\t").csv(booking_path)
        client = spark.read.option("header", True).option("delimiter", "\t").csv(client_path)
        hotel = spark.read.option("header", True).option("delimiter", "\t").csv(hotel_path)

        # Ensure date format consistency
        booking = booking.withColumn('booking_date', to_date(col('booking_date'), 'dd-MM-yyyy'))

        # Create a composite ID for incremental loading
        booking = booking.withColumn('composite_id', 
                                     concat(col('client_id'), lit('_'), 
                                            col('booking_date'), lit('_'), 
                                            col('room_type'), lit('_'), 
                                            col('hotel_id')))

        # Get the last processed composite ID
        last_processed_composite_id = get_last_processed_id()

        # Filter data for incremental load
        booking_filtered = booking.filter(col('composite_id') > last_processed_composite_id)
        
        # Save the filtered DataFrames to Parquet
        booking_filtered.write.parquet(f"{intermediate_data}/booking_filtered.parquet", mode="overwrite")
        client.write.parquet(f"{intermediate_data}/client.parquet", mode="overwrite")
        hotel.write.parquet(f"{intermediate_data}/hotel.parquet", mode="overwrite")

        spark.stop()

        logger.info(f"Data successfully loaded and filtered for incremental processing. Used files: {booking_file}, {client_file}, {hotel_file}")

    except Exception as e:
        logger.error(f"Error occurred in load_data: {e}")
        raise

def transform_data():
    try:
        spark = SparkSession.builder.appName("Improved Incremental Load").getOrCreate()

        # Load intermediate data
        booking = spark.read.parquet(f"{intermediate_data}/booking_filtered.parquet")
        client = spark.read.parquet(f"{intermediate_data}/client.parquet")
        hotel = spark.read.parquet(f"{intermediate_data}/hotel.parquet")

        # Data Transformation: Rename `client_id` to `client` in both datasets
        booking = booking.withColumnRenamed("client_id", "client")
        client = client.withColumnRenamed("client_id", "client")
        
        # Merge booking with client on 'client'
        data = booking.join(client, on='client', how='inner')
        data = data.withColumnRenamed('name', 'client_name').withColumnRenamed('type', 'client_type')
        
        # Merge booking, client & hotel on 'hotel_id'
        data = data.join(hotel, on='hotel_id', how='inner')
        data = data.withColumnRenamed('name', 'hotel_name')
        
        # Convert all costs to GBP (convert EUR to GBP)
        data = data.withColumn('booking_cost', when(col('currency') == 'EUR', col('booking_cost') * 0.8).otherwise(col('booking_cost')))
        data = data.withColumn('currency', when(col('currency') == 'EUR', 'GBP').otherwise(col('currency')))
        
        # Group by to avoid duplicates
        data = data.groupBy("client", "booking_date", "room_type", "hotel_id", "composite_id") \
                   .agg(spark_max("booking_cost").alias("max_booking_cost"), first("currency").alias("currency"))

        # Save the transformed data in Parquet format
        data.write.parquet(f"{intermediate_data}/transformed.parquet", mode="overwrite")

        spark.stop()

        logger.info("Data successfully transformed and saved.")

    except Exception as e:
        logger.error(f"Error occurred in transform_data: {e}")
        raise

def save_data():
    try:
        spark = SparkSession.builder.appName("Improved Incremental Load").getOrCreate()

        # Load transformed data
        data = spark.read.parquet(f"{intermediate_data}/transformed.parquet")

        # Save final output
        data.write.parquet(f"{processed_data_path}/final_output.parquet", mode="append")

        # Get the maximum composite ID
        max_composite_id = data.agg({"composite_id": "max"}).collect()[0][0]

        # Update last processed composite ID
        if max_composite_id:
            update_last_processed_id(max_composite_id)
        else:
            logger.warning("No new data processed in this run.")

        logger.info("Data successfully saved and metadata updated.")
    except Exception as e:
        logger.error(f"Error occurred in save_data: {e}")
        raise
    finally:
        spark.stop()

# Define the tasks using the DAG object
load_task = PythonOperator(
    task_id='load_data',
    python_callable=load_data,
    dag=dag,
)

transform_task = PythonOperator(
    task_id='transform_data',
    python_callable=transform_data,
    dag=dag,
)

save_task = PythonOperator(
    task_id='save_data',
    python_callable=save_data,
    dag=dag,
)

# Define task dependencies
load_task >> transform_task >> save_task