#
# Networking Module
# Creates a VPC, subnets, NAT Gateway, and default Security Group.
#

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_vpc" "main" {
  cidr_block = var.vpc_cidr

  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-vpc-${var.environment}"
  })
}

# --- Public Subnets ---
resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)

  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true # nosemgrep: codacy.tools-configs.terraform.aws.security.aws-subnet-has-public-ip-address.aws-subnet-has-public-ip-address

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-public-subnet-${count.index + 1}-${var.environment}"
  })
}

# --- Private Subnets ---
resource "aws_subnet" "private" {
  count = length(var.private_subnet_cidrs)

  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-private-subnet-${count.index + 1}-${var.environment}"
  })
}

# --- NAT Gateway ---
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-nat-eip-${var.environment}"
  })
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id # Place NAT in the first public subnet

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-nat-gateway-${var.environment}"
  })

  depends_on = [aws_internet_gateway.main]
}

# --- Internet Gateway ---
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-igw-${var.environment}"
  })
}

# --- Routing Tables ---

# Public route table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-public-rt-${var.environment}"
  })
}

# Associate public subnets with public route table
resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private route table
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-private-rt-${var.environment}"
  })
}

# Associate private subnets with private route table
resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# --- Default Security Group ---
resource "aws_security_group" "default" {
  name        = "${var.project_name}-default-sg-${var.environment}"
  description = "Default security group"
  vpc_id      = aws_vpc.main.id

  # Allow all outbound traffic by default
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Inbound rules will be managed by specific services
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-default-sg-${var.environment}"
  })
}
