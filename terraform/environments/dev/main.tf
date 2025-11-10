#
# This is the main entrypoint for the 'dev' environment.
# It consumes reusable modules from /terraform/modules.
#

# ==============================================================================
# Core Networking
# ==============================================================================

module "networking" {
  source = "../../modules/networking"

  project_name = var.project_name
  environment  = var.environment

  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  private_subnet_cidrs = var.private_subnet_cidrs
  public_subnet_cidrs  = var.public_subnet_cidrs

  common_tags = var.common_tags
}

# ==============================================================================
# Observability
# ==============================================================================

module "observability" {
  source = "../../modules/observability"

  project_name = var.project_name
  environment  = var.environment

  # The list of lambdas we plan to build in Phase 1
  lambda_functions = [
    "intent-classifier",
    "context-builder",
    "bedrock-handler",
    "response-validator",
    "escalation-router",
    "metrics-publisher"
  ]

  log_retention_days = 7 # Keep dev logs for 7 days to save costs

  common_tags = var.common_tags
}
