config {
  # Module inspection configuration
  call_module_type = "all"  # Inspect all module calls (local and remote)
  force            = false  # Don't force continue on errors

  # Disable rules for specific modules if needed
  # disabled_by_default = false
}

# AWS-specific ruleset for resource validation
plugin "aws" {
  enabled = true
  version = "0.33.0"  # Updated to latest version
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# Terraform best practices ruleset
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# Custom rule configurations
rule "terraform_naming_convention" {
  enabled = true

  # Enforce naming conventions for resources
  format = "snake_case"

  # Custom patterns for specific resource types (optional)
  # resource {
  #   format = "snake_case"
  # }
  #
  # variable {
  #   format = "snake_case"
  # }
}

rule "terraform_deprecated_index" {
  enabled = true  # Warn about deprecated index syntax
}

rule "terraform_unused_declarations" {
  enabled = true  # Detect unused variables, locals, and outputs
}

rule "terraform_comment_syntax" {
  enabled = true  # Enforce # over // for comments
}

rule "terraform_documented_variables" {
  enabled = true  # Require descriptions for variables
}

rule "terraform_documented_outputs" {
  enabled = true  # Require descriptions for outputs
}

rule "terraform_typed_variables" {
  enabled = true  # Require type declarations for variables
}

rule "terraform_module_pinned_source" {
  enabled = true  # Require version pinning for modules
  style   = "semver"  # Prefer semantic versioning
}

rule "terraform_required_version" {
  enabled = true  # Ensure terraform required_version is set
}

rule "terraform_required_providers" {
  enabled = true  # Ensure required providers are declared
}

rule "terraform_standard_module_structure" {
  enabled = true  # Enforce standard module structure
}

# AWS-specific rules
rule "aws_resource_missing_tags" {
  enabled = true  # Warn about resources without required tags
  tags = [
    "Environment",
    "Project",
    "ManagedBy"
  ]
}
