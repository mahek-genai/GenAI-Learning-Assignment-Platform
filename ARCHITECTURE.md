# Project Architecture

## High-level architecture

```text
                         +----------------------+
                         |       End Users      |
                         | Trainers / Candidates|
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | Application Load     |
                         | Balancer (HTTP :80)  |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |    Amazon ECS        |
                         |      Fargate         |
                         | Docker + Streamlit   |
                         |       :8501          |
                         +----------+-----------+
                                    |
             +----------------------+----------------------+
             |                      |                      |
             v                      v                      v
   +------------------+   +------------------+   +------------------+
   |  Amazon Bedrock  |   | Amazon DynamoDB  |   |    Amazon S3    |
   |                  |   |                  |   |                  |
   | Nova Pro         |   | assignments      |   | Generated images |
   | Nova Canvas      |   | answers          |   | application data |
   | Titan Embed v2   |   +------------------+   +------------------+
   | Mistral          |
   +------------------+

Deployment path

Application source
       |
       v
      S3
       |
       v
   AWS CodeBuild
       |
       v
     Docker
       |
       v
   Amazon ECR
       |
       v
 ECS Fargate
       |
       v
 Application Load Balancer
```

## Trainer workflow

```text
Trainer enters learning text
          |
          v
Amazon Nova Pro
          |
          v
5 Questions + Answers
          |
          +--------------------+
          |                    |
          v                    v
Amazon Nova Canvas        DynamoDB
          |               assignment record
          v                    ^
Generated Image              |
          |                    |
          v                    |
          +-----> S3 ----------+
```

## Candidate workflow

```text
Candidate selects assignment
          |
          v
DynamoDB assignments table
          |
          v
Select question + enter answer
          |
          v
Amazon Titan Text Embeddings v2
          |
          v
Cosine similarity
          |
          v
Score + highest-score tracking
          |
          +-----------------------------+
          |                             |
          v                             v
Mistral grammar correction       Mistral sentence improvement
          |
          v
Candidate feedback
```

## Deployment components

- Streamlit application packaged in Docker.
- Docker container exposes port 8501.
- Amazon ECR stores the container image.
- Amazon ECS Fargate runs the task.
- Application Load Balancer exposes the application.
- DynamoDB stores assignments and candidate answers.
- S3 stores generated images.
- Amazon Bedrock provides the GenAI inference layer.
