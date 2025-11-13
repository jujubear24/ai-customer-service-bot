"""CloudWatch embedded metrics configuration."""

from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit

metrics = Metrics()

__all__ = ["metrics", "MetricUnit"]
