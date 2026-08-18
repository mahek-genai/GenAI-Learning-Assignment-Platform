# GenAI Learning Assignment Platform

A GenAI-powered learning and assignment platform for trainers and candidates, built with Streamlit and AWS services.

## What the platform does

### Trainers
- Generate five questions and answers from learning text using Amazon Nova Pro.
- Generate a 512x512 image from the learning text using Amazon Nova Canvas.
- Store generated assignments and images in AWS services.
- Browse assignments from the assignment bank.

### Candidates
- Select an assignment and answer generated questions.
- Compare candidate answers with reference answers using Amazon Titan Text Embeddings v2 and cosine similarity.
- Track scores and highest scores in DynamoDB.
- Receive grammar corrections and sentence-improvement suggestions using Mistral.

## Architecture

```text
Users
  |
  v
Application Load Balancer
  |
  v
Amazon ECS Fargate
(Dockerized Streamlit App :8501)
  |
  +--------------------+--------------------+-------------------+
  |                    |                    |
  v                    v                    v
Amazon Bedrock      Amazon DynamoDB       Amazon S3
  |                    |                    |
  |                    |                    +-- Generated images
  |                    +-- assignments
  |                    +-- answers
  |
  +-- Nova Pro       -> Question generation
  +-- Nova Canvas    -> Image generation
  +-- Titan Embed v2 -> Semantic answer scoring
  +-- Mistral        -> Grammar/sentence suggestions

Deployment flow:
Source -> S3/CodeBuild -> Docker -> Amazon ECR -> ECS Fargate -> ALB
```

## Repository structure

```text
.
├── Home.py
├── components/
│   └── Parameter_store.py
├── pages/
│   ├── 1_Create_Assignments.py
│   ├── 2_Show_Assignments.py
│   └── 3_Complete_Assignments.py
├── Dockerfile.txt
├── ecs-task.json
├── requirements.txt
├── ARCHITECTURE.md
└── README.md
```

## AWS services

- Amazon Bedrock
- Amazon DynamoDB
- Amazon S3
- Amazon ECR
- Amazon ECS Fargate
- Application Load Balancer
- Amazon VPC
- AWS CodeBuild

## Models used

- `amazon.nova-pro-v1:0`
- `amazon.nova-canvas-v1:0`
- `amazon.titan-embed-text-v2:0`
- `mistral.mistral-7b-instruct-v0:2`

## Container deployment

The Streamlit application runs on port 8501 inside the container. The ECS task definition uses Fargate and `awsvpc` networking.

## Security note

The original deployment configuration contains environment-specific AWS account, ECR, IAM, and S3 identifiers. Review and replace these values before deploying the project in another AWS account, and never commit AWS access keys or other secrets.
