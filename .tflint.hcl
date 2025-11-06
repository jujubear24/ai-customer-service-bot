config {
  # This is a recommended ruleset for tflint
  call_module_type = "all"
  force  = false
}

# This ruleset provides recommended checks for AWS.
plugin "aws" {
  enabled = true
  version = "0.26.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
