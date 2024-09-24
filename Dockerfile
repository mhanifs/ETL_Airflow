# Use the Apache Airflow image as the base
FROM apache/airflow:2.5.1-python3.8

# Switch to root user to install necessary packages
USER root

# Update and install necessary packages including wget
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
    openjdk-11-jdk \
    ca-certificates-java \
    wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Spark
ENV SPARK_VERSION=3.5.2
ENV HADOOP_VERSION=3

# Download and install Spark
RUN wget https://downloads.apache.org/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz && \
    tar xzf spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz && \
    mv spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} /opt/spark && \
    rm spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz

# Add Spark to the PATH environment variable
ENV PATH=$PATH:/opt/spark/bin

# Set the SPARK_HOME environment variable
ENV SPARK_HOME=/opt/spark

# Switch back to airflow user for pip installation
USER airflow

# Install PySpark as airflow user
RUN pip install pyspark==3.5.2
