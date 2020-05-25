"""
PySpark Decision Tree Regression Example.
"""

import platform
import click
import pyspark
from pyspark.sql import SparkSession
from pyspark.ml import Pipeline
from pyspark.ml.regression import DecisionTreeRegressor
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.feature import VectorAssembler
import mlflow
import mlflow.spark
from common import *

spark = SparkSession.builder.appName("App").getOrCreate()

print("Versions:")
print("  Operating System:",platform.version()+" - "+platform.release())
print("  MLflow Version:", mlflow.__version__)
print("  Spark Version:", spark.version)
print("  PySpark Version:", pyspark.__version__)
print("  MLflow Tracking URI:", mlflow.tracking.get_tracking_uri())

def train(data, max_depth, max_bins, model_name, log_as_mleap, log_as_onnx):
    (trainingData, testData) = data.randomSplit([0.7, 0.3], 42)
    print("testData.schema:")
    testData.printSchema()

    # MLflow - log parameters
    print("Parameters:")
    print("  max_depth:", max_depth)
    print("  max_bins:", max_bins)
    mlflow.log_param("max_depth", max_depth)
    mlflow.log_param("max_bins", max_bins)

    # Create pipeline
    dt = DecisionTreeRegressor(labelCol=colLabel, featuresCol=colFeatures, maxDepth=max_depth, maxBins=max_bins)
    assembler = VectorAssembler(inputCols=data.columns[:-1], outputCol=colFeatures)
    pipeline = Pipeline(stages=[assembler, dt])
    
    # Fit model and predict
    model = pipeline.fit(trainingData)
    predictions = model.transform(testData)

    # MLflow - log metrics
    print("Metrics:")
    predictions = model.transform(testData)
    metrics = ["rmse", "r2", "mae"]
    for metric_name in metrics:
        evaluator = RegressionEvaluator(labelCol=colLabel, predictionCol=colPrediction, metricName=metric_name)
        metric_value = evaluator.evaluate(predictions)
        print(f"  {metric_name}: {metric_value}")
        mlflow.log_metric(metric_name,metric_value)

    # MLflow - log spark model
    mlflow.spark.log_model(model, "spark-model", \
        registered_model_name=None if not model_name else f"{model_name}")

    # MLflow - log as MLeap model
    if log_as_mleap:
        scoreData = testData.drop("quality")
        mlflow.mleap.log_model(spark_model=model, sample_input=scoreData, artifact_path="mleap-model", \
            registered_model_name=None if not model_name else f"{model_name}_mleap")

        # Log MLeap schema file for MLeap runtime deserialization
        schema_path = "schema.json"
        with open(schema_path, 'w') as f:
            f.write(scoreData.schema.json())
        print("schema_path:", schema_path)
        mlflow.log_artifact(schema_path, "mleap-model")

    # MLflow - log as ONNX model
    if log_as_onnx:
        import onnx_utils
        scoreData = testData.drop("quality")
        onnx_utils.log_model(spark, model, "onnx-model", model_name, scoreData)

def foo():
    parser = ArgumentParser()
    parser.add_argument("--experiment_name", dest="experiment_name", help="experiment_name", required=False, type=str)
    parser.add_argument("--model_name", dest="model_name", help="Registered model name", default=None)
    parser.add_argument("--data_path", dest="data_path", help="Data path", default=default_data_path)
    parser.add_argument("--max_depth", dest="max_depth", help="Max depth", default=5, type=int) # per doc
    parser.add_argument("--max_bins", dest="max_bins", help="Max bins", default=32, type=int) # per doc
    parser.add_argument("--describe", dest="describe", help="Describe data", default=False, action='store_true')
    parser.add_argument("--log_as_mleap", dest="log_as_mleap", help="Log model as MLeap", default=False, action='store_true')
    parser.add_argument("--log_as_onnx", dest="log_as_onnx", help="Log model as ONNX", default=False, action='store_true')
    parser.add_argument("--spark_autolog", dest="spark_autolog", help="Use spark.autolog", default=False, action='store_true')
    args = parser.parse_args()
    print("Arguments:")
    for arg in vars(args):
        print(f"  {arg}: {getattr(args, arg)}")

@click.command()
@click.option("--experiment_name", help="Experiment name", default=None, type=str)
@click.option("--data_path", help="Data path", default="../../data/train/wine-quality-white.csv", type=str)
@click.option("--model_name", help="Registered model name", default=None, type=str)
@click.option("--max_depth", help="Max depth", default=5, type=int) # per doc
@click.option("--max_bins", help="Max bins", default=32, type=int) # per doc
@click.option("--describe", help="Describe data", default=False, type=bool)
@click.option("--log_as_mleap", help="Score as MLeap", default=False, type=bool)
@click.option("--log_as_onnx", help="Log model as ONNX flavor", default=False, type=bool)
@click.option("--spark_autolog", help="Use spark.autolog", default=False, type=bool)

def main(experiment_name, model_name, data_path, max_depth, max_bins, describe, log_as_mleap, log_as_onnx, spark_autolog):
    print("Options:")
    for k,v in locals().items():
        print(f"  {k}: {v}")

    client = mlflow.tracking.MlflowClient()
    if experiment_name:
        mlflow.set_experiment(experiment_name)
    if spark_autolog:
        mlflow.spark.autolog()
    data_path = data_path or default_data_path
    data = read_data(spark, data_path)
    if (describe):
        print("==== Data")
        data.describe().show()

    with mlflow.start_run() as run:
        print("MLflow:")
        print("  run_id:", run.info.run_id)
        print("  experiment_id:", run.info.experiment_id)
        print("  experiment_name:", client.get_experiment(run.info.experiment_id).name)
        mlflow.set_tag("version.mlflow", mlflow.__version__)
        mlflow.set_tag("version.spark", spark.version)
        mlflow.set_tag("version.pyspark", pyspark.__version__)
        mlflow.set_tag("version.os", platform.system()+" - "+platform.release())

        model_name = None if model_name is None or model_name == "None" else model_name
        train(data, max_depth, max_bins, model_name, log_as_mleap, log_as_onnx)

if __name__ == "__main__":
    main()
