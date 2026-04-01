# Amazon Bedrock RAG Evaluation Framework - Guardrails Contextual Grounding Evaluation

A framework for evaluating the **effectiveness of hallucination prevention** by applying Guardrails (Contextual Grounding) to Knowledge Bases using Amazon Bedrock Evaluations.

## Features

- Automated infrastructure deployment with AWS CDK (TypeScript)
- S3 Vectors as vector store for Knowledge Base
- Guardrails Contextual Grounding configuration for hallucination prevention
- Evaluation job setup for comparing with/without Guardrails
- Report generation script with optional LLM analysis

## Overview

This repository quantitatively evaluates how effective the Guardrails Contextual Grounding feature is at preventing hallucinations in RAG (Retrieval-Augmented Generation) systems.

### Evaluation Contents

- Run evaluation jobs in two patterns: **without Guardrails** and **with Guardrails**
- Compare scores using 4 metrics (Correctness, Completeness, Faithfulness, Helpfulness)
- Evaluate hallucination avoidance particularly through the **Faithfulness** metric

### Key Components

| Component | Description |
|-----------|-------------|
| **Knowledge Base** | Uses S3 Vectors as vector store |
| **Guardrails** | Hallucination prevention through Contextual Grounding |
| **Evaluation Job** | Compare response quality with/without Guardrails |

## Architecture

![](images/architecture.png)

### Data Flow

1. **Sync Phase**: S3 Data Source → S3 Vectors (vectorize documents)
2. **Evaluation Phase**:
   - Evaluation Job reads questions from S3 Dataset
   - Knowledge Base performs search and response generation
   - Guardrails checks for hallucinations (two patterns: with/without)
   - Results output to S3 Output

## Resources Created by CDK

| # | Resource | Name |
|---|----------|------|
| 1 | S3 (Data Source) | `bedrock-rag-eval-guardrails-grounding-datasource-{AccountID}` |
| 2 | S3 (Evaluation Output) | `bedrock-rag-eval-guardrails-grounding-output-{AccountID}` |
|   | └ Subfolders | `with-guardrails/`, `without-guardrails/` |
| 3 | S3 (Evaluation Dataset) | `bedrock-rag-eval-guardrails-grounding-dataset-{AccountID}` |
| 4 | S3 Vector Bucket | `bedrock-rag-eval-guardrails-grounding-vector-store-{AccountID}` |
| 5 | S3 Vector Index | `bedrock-rag-eval-guardrails-grounding-index` |
| 6 | Knowledge Base | `bedrock-rag-eval-guardrails-grounding-kb` |
| 7 | Data Source | Linked to KB |
| 8 | Guardrails | `bedrock-rag-eval-guardrails-grounding-guardrail` |
| 9 | IAM Role (for KB) | `bedrock-rag-eval-guardrails-grounding-kb-role` |
| 10 | IAM Role (for Evaluation) | `bedrock-rag-eval-guardrails-grounding-eval-role` |

---

## Prerequisites

- AWS CLI installed and credentials configured
- Node.js 18.x or higher
- pnpm installed
- AWS CDK CLI installed

```bash
npm install -g aws-cdk
```

---

## Setup Instructions

### 1. Clone Repository and Navigate

```bash
git clone https://github.com/your-repo/bedrock-rag-eval-guardrails-grounding.git
cd bedrock-rag-eval-guardrails-grounding/cdk
```

### 2. Install Dependencies

```bash
pnpm install
```

### 3. CDK Bootstrap (First Time Only)

```bash
pnpm cdk bootstrap
```

### 4. Deploy

```bash
pnpm cdk deploy
```

### 5. Verify Deployment

After deployment completes, the following Outputs will be displayed:

| Output | Description |
|--------|-------------|
| DataSourceBucketName | S3 bucket for document storage |
| EvaluationOutputBucketName | S3 bucket for evaluation results |
| EvaluationDatasetBucketName | S3 bucket for evaluation dataset |
| VectorBucketName | S3 bucket for vector store |
| KnowledgeBaseId | Knowledge Base ID |
| DataSourceId | Data Source ID |
| GuardrailId | Guardrail ID |
| GuardrailVersionOutput | Guardrail Version |
| KnowledgeBaseRoleArn | IAM Role ARN for KB |
| EvaluationRoleArn | IAM Role ARN for evaluation jobs |

---

## Upload Sample Data

### Upload Documents

```bash
aws s3 cp sample_data/product_manual.txt s3://bedrock-rag-eval-guardrails-grounding-datasource-{AccountID}/
```

### Upload Evaluation Dataset

```bash
aws s3 cp sample_data/evaluation_dataset.jsonl s3://bedrock-rag-eval-guardrails-grounding-dataset-{AccountID}/
```

---

## Sync Knowledge Base

### Sync from Console

1. Open [Amazon Bedrock Console](https://console.aws.amazon.com/bedrock/)
2. Navigate to **Knowledge bases** → Select `bedrock-rag-eval-guardrails-grounding-kb`
3. In **Data sources** section, select `bedrock-rag-eval-guardrails-grounding-datasource`
4. Click **Sync** button
5. Wait for sync to complete (status becomes "Available")

### Sync from CLI (Alternative)

```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id {KnowledgeBaseId} \
  --data-source-id {DataSourceId} \
  --region ap-northeast-1
```

---

## Create Evaluation Jobs (From Console)

### Evaluation Dataset Format

The evaluation dataset is a JSONL file in `conversationTurns` format.

```jsonl
{"conversationTurns": [{"prompt": {"content": [{"text": "What are the dimensions of SmartHub X1?"}]}, "referenceResponses": [{"content": [{"text": "The dimensions of SmartHub X1 are 120mm x 120mm x 35mm."}]}]}]}
{"conversationTurns": [{"prompt": {"content": [{"text": "How many devices can SmartHub X1 support at maximum?"}]}, "referenceResponses": [{"content": [{"text": "SmartHub X1 supports up to 100 devices."}]}]}]}
```

---

### Create Evaluation Job (Without Guardrails)

1. Open [Amazon Bedrock Console](https://console.aws.amazon.com/bedrock/)
2. Click **Assessments** → **Model evaluation** → **Create evaluation**
3. Configure the following:

| Item | Value |
|------|-------|
| Evaluation type | Knowledge Base evaluation |
| Evaluation name | `eval-without-guardrails` |

4. **Inference source** section:

| Item | Value |
|------|-------|
| Select source | Bedrock Knowledge Base |
| Knowledge Base | `bedrock-rag-eval-guardrails-grounding-kb` |
| Evaluation type | Retrieval and response generation |
| Response generator model | Claude 3 Haiku |

5. **Metrics** section (select all 4):

| Metric | Description | Select |
|--------|-------------|--------|
| Helpfulness | Response usefulness | ✅ |
| Correctness | Response accuracy | ✅ |
| Faithfulness | Hallucination avoidance | ✅ |
| Completeness | Response completeness | ✅ |

6. **Dataset** section:

| Item | Value |
|------|-------|
| Dataset location | `s3://bedrock-rag-eval-guardrails-grounding-dataset-{AccountID}/evaluation_dataset.jsonl` |
| Output destination | `s3://bedrock-rag-eval-guardrails-grounding-output-{AccountID}/without-guardrails/` |

7. **IAM role** section:

| Item | Value |
|------|-------|
| Service role | Select `bedrock-rag-eval-guardrails-grounding-eval-role` |

8. Click **Create evaluation**

---

### Create Evaluation Job (With Guardrails)

1. Click **Assessments** → **Model evaluation** → **Create evaluation**
2. Configure the following:

| Item | Value |
|------|-------|
| Evaluation type | Knowledge Base evaluation |
| Evaluation name | `eval-with-guardrails` |

3. **Inference source** section:

| Item | Value |
|------|-------|
| Select source | Bedrock Knowledge Base |
| Knowledge Base | `bedrock-rag-eval-guardrails-grounding-kb` |
| Evaluation type | Retrieval and response generation |
| Response generator model | Claude 3 Haiku |

4. Click **configurations** to expand

5. **Guardrails** section:

| Item | Value |
|------|-------|
| Name | `bedrock-rag-eval-guardrails-grounding-guardrail` |
| Version | `Version 1` |

6. **Metrics** section (select all 4):

| Metric | Select |
|--------|--------|
| Helpfulness | ✅ |
| Correctness | ✅ |
| Faithfulness | ✅ |
| Completeness | ✅ |

7. **Dataset** section:

| Item | Value |
|------|-------|
| Dataset location | `s3://bedrock-rag-eval-guardrails-grounding-dataset-{AccountID}/evaluation_dataset.jsonl` |
| Output destination | `s3://bedrock-rag-eval-guardrails-grounding-output-{AccountID}/with-guardrails/` |

8. **IAM role** section:

| Item | Value |
|------|-------|
| Service role | Select `bedrock-rag-eval-guardrails-grounding-eval-role` |

9. Click **Create evaluation**

---

## Check Evaluation Results

### Check from Console

1. Open **Assessments** → **Model evaluation**
2. Select the created evaluation job
3. Check results when status becomes "Completed"

### Check from S3

```bash
# Without Guardrails
aws s3 ls s3://bedrock-rag-eval-guardrails-grounding-output-{AccountID}/without-guardrails/ --recursive

# With Guardrails
aws s3 ls s3://bedrock-rag-eval-guardrails-grounding-output-{AccountID}/with-guardrails/ --recursive
```

---

## Generate Evaluation Report

Aggregate evaluation results output to S3 and generate a Markdown report.

### Run Script

```bash
python scripts/generate_report.py \
  --account-id {AccountID} \
  --output evaluation_results.md
```

### Options

| Option | Description |
|--------|-------------|
| `--account-id` | AWS Account ID (required) |
| `--output` | Output filename (default: evaluation_results.md) |
| `--use-llm` | Add analysis comments using LLM (Claude) |
| `--kb-id` | Knowledge Base ID (for report) |
| `--guardrail-id` | Guardrail ID (for report) |

### Run with LLM Analysis

```bash
python scripts/generate_report.py \
  --account-id {AccountID} \
  --use-llm \
  --kb-id {KnowledgeBaseId} \
  --guardrail-id {GuardrailId} \
  --output evaluation_results.md
```

### Report Contents

| Section | Content |
|---------|---------|
| Evaluation Settings | Number of test cases, model information |
| Score Comparison | Average score comparison with/without Guardrails |
| Detailed Results by Question | Metrics list for each question |
| Analysis of Questions with Large Differences | Response comparison |
| Conclusion | Overall evaluation |

---

## Evaluation Metrics

| Metric | Description |
|--------|-------------|
| **Correctness** | Response accuracy (match with expected answer) |
| **Completeness** | Response completeness (whether all necessary information is included) |
| **Faithfulness** | Fidelity (based on source documents, **hallucination avoidance**) |
| **Helpfulness** | Usefulness (whether the response is helpful to the user) |

---

## Directory Structure

```
bedrock-rag-eval-guardrails-grounding/
├── cdk/
│   ├── bin/
│   │   └── app.ts              # CDK entry point
│   ├── lib/
│   │   └── main-stack.ts       # Stack containing all resources
│   ├── package.json
│   └── tsconfig.json
├── sample_data/
│   ├── product_manual.txt      # Sample document
│   └── evaluation_dataset.jsonl # Evaluation dataset
├── scripts/
│   └── generate_report.py      # Evaluation report generator
├── images/                     # Documentation images
├── README.md                   # English documentation
└── README.ja.md                # Japanese documentation
```

---

## Cleanup

```bash
cd cdk
pnpm cdk destroy
```

> **Note**: Objects in S3 buckets will also be automatically deleted (`auto_delete_objects=True`).

---

## References

- [Amazon S3 Vectors](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors.html)
- [Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Amazon Bedrock Guardrails - Contextual Grounding](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html)
- [Amazon Bedrock Model Evaluation](https://docs.aws.amazon.com/bedrock/latest/userguide/model-evaluation.html)

---

## License

MIT License
