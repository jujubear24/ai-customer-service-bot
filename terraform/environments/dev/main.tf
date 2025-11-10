#
# This is the main entrypoint for the 'dev' environment.
# It consumes reusable modules from /terraform/modules.
#

# --- Core Networking ---
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
