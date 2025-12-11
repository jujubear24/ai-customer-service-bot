# =============================================================================
# Knowledge Base Module - Input Variables
# =============================================================================

# -----------------------------------------------------------------------------
# Required Variables
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Name of the project (used in resource naming)"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,40}$", var.project_name))
    error_message = "Project name must be 3-41 lowercase alphanumeric characters with hyphens, starting with a letter."
  }
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

# -----------------------------------------------------------------------------
# Embedding Model Configuration
# -----------------------------------------------------------------------------

variable "embedding_model_id" {
  description = "Bedrock embedding model ID"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"

  validation {
    condition = contains([
      "amazon.titan-embed-text-v1",
      "amazon.titan-embed-text-v2:0",
      "cohere.embed-english-v3",
      "cohere.embed-multilingual-v3"
    ], var.embedding_model_id)
    error_message = "Must be a valid Bedrock embedding model ID."
  }
}

variable "embedding_dimensions" {
  description = "Embedding vector dimensions (only for Titan V2: 256, 512, or 1024)"
  type        = number
  default     = 512

  validation {
    condition     = var.embedding_dimensions == null || contains([256, 512, 1024], var.embedding_dimensions)
    error_message = "Embedding dimensions must be 256, 512, or 1024 for Titan V2."
  }
}

# -----------------------------------------------------------------------------
# S3 Configuration
# -----------------------------------------------------------------------------

variable "s3_version_retention_days" {
  description = "Number of days to retain non-current S3 object versions"
  type        = number
  default     = 30

  validation {
    condition     = var.s3_version_retention_days >= 1 && var.s3_version_retention_days <= 365
    error_message = "S3 version retention must be between 1 and 365 days."
  }
}

# -----------------------------------------------------------------------------
# Vector Store Configuration
# -----------------------------------------------------------------------------

variable "vector_table_name" {
  description = "Name of the table in Aurora PostgreSQL for vector storage"
  type        = string
  default     = "bedrock_knowledge_base"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,62}$", var.vector_table_name))
    error_message = "Table name must be 3-63 lowercase alphanumeric characters with underscores."
  }
}

# -----------------------------------------------------------------------------
# Chunking Configuration
# -----------------------------------------------------------------------------

variable "chunking_strategy" {
  description = "Document chunking strategy (NONE, FIXED_SIZE, SEMANTIC, HIERARCHICAL)"
  type        = string
  default     = "SEMANTIC"

  validation {
    condition     = contains(["NONE", "FIXED_SIZE", "SEMANTIC", "HIERARCHICAL"], var.chunking_strategy)
    error_message = "Chunking strategy must be one of: NONE, FIXED_SIZE, SEMANTIC, HIERARCHICAL."
  }
}

# Semantic chunking variables
variable "semantic_chunking_max_tokens" {
  description = "Maximum tokens per chunk for semantic chunking"
  type        = number
  default     = 300

  validation {
    condition     = var.semantic_chunking_max_tokens >= 50 && var.semantic_chunking_max_tokens <= 1000
    error_message = "Semantic chunking max tokens must be between 50 and 1000."
  }
}

variable "semantic_chunking_buffer_size" {
  description = "Number of sentences to overlap between chunks"
  type        = number
  default     = 1

  validation {
    condition     = var.semantic_chunking_buffer_size >= 0 && var.semantic_chunking_buffer_size <= 5
    error_message = "Semantic chunking buffer size must be between 0 and 5."
  }
}

variable "semantic_chunking_breakpoint_threshold" {
  description = "Percentile threshold for semantic breakpoints (higher = fewer breaks)"
  type        = number
  default     = 95

  validation {
    condition     = var.semantic_chunking_breakpoint_threshold >= 50 && var.semantic_chunking_breakpoint_threshold <= 99
    error_message = "Breakpoint threshold must be between 50 and 99."
  }
}

# Fixed size chunking variables
variable "fixed_chunking_max_tokens" {
  description = "Maximum tokens per chunk for fixed size chunking"
  type        = number
  default     = 300

  validation {
    condition     = var.fixed_chunking_max_tokens >= 50 && var.fixed_chunking_max_tokens <= 1000
    error_message = "Fixed chunking max tokens must be between 50 and 1000."
  }
}

variable "fixed_chunking_overlap_percentage" {
  description = "Percentage of overlap between chunks (0-50)"
  type        = number
  default     = 20

  validation {
    condition     = var.fixed_chunking_overlap_percentage >= 0 && var.fixed_chunking_overlap_percentage <= 50
    error_message = "Overlap percentage must be between 0 and 50."
  }
}

# -----------------------------------------------------------------------------
# Tags
# -----------------------------------------------------------------------------

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# VPC Configuration
# -----------------------------------------------------------------------------

variable "vpc_id" {
  description = "Existing VPC ID. If not provided, a new VPC will be created."
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "List of subnet IDs for Aurora. Required if vpc_id is provided."
  type        = list(string)
  default     = []

  validation {
    condition     = var.vpc_id == null || length(var.subnet_ids) >= 2
    error_message = "At least 2 subnet IDs are required when using an existing VPC."
  }
}

# -----------------------------------------------------------------------------
# Aurora PostgreSQL Configuration
# -----------------------------------------------------------------------------

variable "aurora_engine_version" {
  description = "Aurora PostgreSQL engine version (must support pgvector: 15.4+)"
  type        = string
  default     = "15.6"

  validation {
    condition     = can(regex("^1[5-9]\\.", var.aurora_engine_version))
    error_message = "Aurora engine version must be 15.x or higher for pgvector support."
  }
}

variable "aurora_database_name" {
  description = "Name of the database to create"
  type        = string
  default     = "knowledgebase"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,62}$", var.aurora_database_name))
    error_message = "Database name must be 3-63 lowercase alphanumeric characters with underscores."
  }
}

variable "aurora_master_username" {
  description = "Master username for Aurora cluster"
  type        = string
  default     = "kbadmin"
  sensitive   = true

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{2,62}$", var.aurora_master_username))
    error_message = "Username must be 3-63 alphanumeric characters, starting with a letter."
  }
}

variable "aurora_master_password" {
  description = "Master password for Aurora cluster (min 8 characters)"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.aurora_master_password) >= 8
    error_message = "Password must be at least 8 characters."
  }
}

variable "aurora_min_capacity" {
  description = "Minimum ACUs for Aurora Serverless v2 (0.5 to 128)"
  type        = number
  default     = 0.5

  validation {
    condition     = var.aurora_min_capacity >= 0.5 && var.aurora_min_capacity <= 128
    error_message = "Minimum capacity must be between 0.5 and 128 ACUs."
  }
}

variable "aurora_max_capacity" {
  description = "Maximum ACUs for Aurora Serverless v2 (must be >= min_capacity)"
  type        = number
  default     = 4

  validation {
    condition     = var.aurora_max_capacity >= 0.5 && var.aurora_max_capacity <= 128
    error_message = "Maximum capacity must be between 0.5 and 128 ACUs."
  }
}
