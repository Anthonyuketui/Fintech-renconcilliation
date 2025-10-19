terraform {
  backend "s3" {
    bucket         = "fintech-terraform-state-1760119671"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}