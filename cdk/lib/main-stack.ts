/**
 * Amazon Bedrock RAG 評価フレームワーク メインスタック
 *
 * ブログ記事用の作業環境を構築します。
 * タイトル: [Amazon Bedrock Evaluations] Knowledge Bases への Guardrails の適用による、
 *          コンテキストグラウンディング（ハルシネーション防止）の有効性を評価してみました
 *
 * 作成するリソース:
 * 1. S3 バケット（データソース用）
 * 2. S3 バケット（評価出力用）+ サブフォルダ
 * 3. S3 バケット（評価データセット用）
 * 4. S3 Vector Bucket
 * 5. S3 Vector Index
 * 6. Knowledge Base
 * 7. Data Source
 * 8. Guardrails（コンテキストグラウンディング）
 * 9. IAM ロール（KB 用）
 * 10. IAM ロール（評価ジョブ用）
 */
import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3vectors from "aws-cdk-lib/aws-s3vectors";
import * as iam from "aws-cdk-lib/aws-iam";
import * as bedrock from "aws-cdk-lib/aws-bedrock";
import * as cr from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";

export interface MainStackProps extends cdk.StackProps {
  projectName: string;
}

export class MainStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: MainStackProps) {
    super(scope, id, props);

    const { projectName } = props;

    // ===========================================
    // 1. S3 バケット（データソース用）
    // ===========================================
    const dataSourceBucket = new s3.Bucket(this, "DataSourceBucket", {
      bucketName: `${projectName}-datasource-${this.account}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      versioned: true,
    });

    // ===========================================
    // 2. S3 バケット（評価出力用）+ サブフォルダ
    // ===========================================
    const evaluationOutputBucket = new s3.Bucket(
      this,
      "EvaluationOutputBucket",
      {
        bucketName: `${projectName}-output-${this.account}`,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        autoDeleteObjects: true,
        blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
        encryption: s3.BucketEncryption.S3_MANAGED,
        versioned: true,
      }
    );

    // サブフォルダを事前作成（コンソールから選択できるように）
    const folders = ["with-guardrails/", "without-guardrails/"];
    folders.forEach((folder) => {
      new cr.AwsCustomResource(
        this,
        `CreateFolder${folder.replace(/[/-]/g, "")}`,
        {
          onCreate: {
            service: "S3",
            action: "putObject",
            parameters: {
              Bucket: evaluationOutputBucket.bucketName,
              Key: folder,
              Body: "",
            },
            physicalResourceId: cr.PhysicalResourceId.of(
              `${evaluationOutputBucket.bucketName}/${folder}`
            ),
          },
          policy: cr.AwsCustomResourcePolicy.fromSdkCalls({
            resources: [`${evaluationOutputBucket.bucketArn}/*`],
          }),
        }
      );
    });

    // ===========================================
    // 3. S3 バケット（評価データセット用）
    // ===========================================
    const evaluationDatasetBucket = new s3.Bucket(
      this,
      "EvaluationDatasetBucket",
      {
        bucketName: `${projectName}-dataset-${this.account}`,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        autoDeleteObjects: true,
        blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
        encryption: s3.BucketEncryption.S3_MANAGED,
        versioned: true,
      }
    );

    // ===========================================
    // 4. S3 Vector Bucket
    // ===========================================
    const vectorBucketName = `${projectName}-vector-store-${this.account}`;
    const vectorBucket = new s3vectors.CfnVectorBucket(this, "VectorBucket", {
      vectorBucketName: vectorBucketName,
    });

    // ===========================================
    // 5. S3 Vector Index
    // ===========================================
    const vectorIndexName = `${projectName}-index`;
    const vectorIndex = new s3vectors.CfnIndex(this, "VectorIndex", {
      vectorBucketName: vectorBucketName,
      indexName: vectorIndexName,
      dataType: "float32",
      dimension: 1024, // Titan Embed Text v2 は 1024 次元
      distanceMetric: "cosine",
    });
    vectorIndex.node.addDependency(vectorBucket);

    // ===========================================
    // 9. IAM ロール（KB 用）
    // ===========================================
    const kbRole = new iam.Role(this, "KnowledgeBaseRole", {
      roleName: `${projectName}-kb-role`,
      assumedBy: new iam.ServicePrincipal("bedrock.amazonaws.com"),
      inlinePolicies: {
        KnowledgeBasePolicy: new iam.PolicyDocument({
          statements: [
            // S3 データソースアクセス
            new iam.PolicyStatement({
              actions: ["s3:GetObject", "s3:ListBucket"],
              resources: [
                dataSourceBucket.bucketArn,
                `${dataSourceBucket.bucketArn}/*`,
              ],
            }),
            // S3 Vectors アクセス
            new iam.PolicyStatement({
              actions: [
                "s3vectors:CreateIndex",
                "s3vectors:DeleteIndex",
                "s3vectors:GetIndex",
                "s3vectors:ListIndexes",
                "s3vectors:PutVectors",
                "s3vectors:GetVectors",
                "s3vectors:DeleteVectors",
                "s3vectors:QueryVectors",
              ],
              resources: [
                `arn:aws:s3vectors:${this.region}:${this.account}:bucket/${vectorBucketName}`,
                `arn:aws:s3vectors:${this.region}:${this.account}:bucket/${vectorBucketName}/*`,
              ],
            }),
            // Bedrock モデルアクセス（埋め込みモデル用）
            new iam.PolicyStatement({
              actions: ["bedrock:InvokeModel"],
              resources: [
                `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
              ],
            }),
          ],
        }),
      },
    });

    // ===========================================
    // 6. Knowledge Base
    // ===========================================
    const knowledgeBase = new bedrock.CfnKnowledgeBase(this, "KnowledgeBase", {
      name: `${projectName}-kb`,
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: "VECTOR",
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
        },
      },
      storageConfiguration: {
        type: "S3_VECTORS",
        s3VectorsConfiguration: {
          vectorBucketArn: `arn:aws:s3vectors:${this.region}:${this.account}:bucket/${vectorBucketName}`,
          indexArn: `arn:aws:s3vectors:${this.region}:${this.account}:bucket/${vectorBucketName}/index/${vectorIndexName}`,
        },
      },
      description: "Knowledge Base for RAG evaluation",
    });
    knowledgeBase.node.addDependency(vectorIndex);

    // ===========================================
    // 7. Data Source
    // ===========================================
    const dataSource = new bedrock.CfnDataSource(this, "DataSource", {
      name: `${projectName}-datasource`,
      knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
      dataSourceConfiguration: {
        type: "S3",
        s3Configuration: {
          bucketArn: dataSourceBucket.bucketArn,
        },
      },
      description: "S3 data source for knowledge base",
    });

    // ===========================================
    // 8. Guardrails（コンテキストグラウンディング）
    // ===========================================
    const guardrail = new bedrock.CfnGuardrail(this, "Guardrail", {
      name: `${projectName}-guardrail`,
      blockedInputMessaging:
        "申し訳ございません。この入力は処理できません。",
      blockedOutputsMessaging:
        "申し訳ございません。この応答は提供できません。",
      description: "RAG 用ガードレール - コンテキストグラウンディング",
      contextualGroundingPolicyConfig: {
        filtersConfig: [
          {
            type: "GROUNDING",
            threshold: 0.7,
          },
          {
            type: "RELEVANCE",
            threshold: 0.7,
          },
        ],
      },
      tags: [
        {
          key: "Project",
          value: projectName,
        },
      ],
    });

    const guardrailVersion = new bedrock.CfnGuardrailVersion(
      this,
      "GuardrailVersion",
      {
        guardrailIdentifier: guardrail.attrGuardrailId,
        description: "Version 1",
      }
    );

    // ===========================================
    // 10. IAM ロール（評価ジョブ用）
    // ===========================================
    const evalRole = new iam.Role(this, "EvaluationRole", {
      roleName: `${projectName}-eval-role`,
      assumedBy: new iam.ServicePrincipal("bedrock.amazonaws.com"),
      inlinePolicies: {
        EvaluationPolicy: new iam.PolicyDocument({
          statements: [
            // S3 読み取り（評価データセット + データソース）
            new iam.PolicyStatement({
              actions: ["s3:GetObject", "s3:ListBucket"],
              resources: [
                evaluationDatasetBucket.bucketArn,
                `${evaluationDatasetBucket.bucketArn}/*`,
                dataSourceBucket.bucketArn,
                `${dataSourceBucket.bucketArn}/*`,
              ],
            }),
            // S3 書き込み（評価結果出力）
            new iam.PolicyStatement({
              actions: ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
              resources: [
                evaluationOutputBucket.bucketArn,
                `${evaluationOutputBucket.bucketArn}/*`,
              ],
            }),
            // Bedrock アクセス
            new iam.PolicyStatement({
              actions: [
                "bedrock:RetrieveAndGenerate",
                "bedrock:Retrieve",
                "bedrock:InvokeModel",
                "bedrock:ApplyGuardrail",
              ],
              resources: ["*"],
            }),
            // 評価ジョブ
            new iam.PolicyStatement({
              actions: [
                "bedrock:CreateEvaluationJob",
                "bedrock:GetEvaluationJob",
                "bedrock:ListEvaluationJobs",
                "bedrock:StopEvaluationJob",
              ],
              resources: ["*"],
            }),
          ],
        }),
      },
    });

    // ===========================================
    // Outputs
    // ===========================================
    new cdk.CfnOutput(this, "DataSourceBucketName", {
      value: dataSourceBucket.bucketName,
      description: "S3 bucket for documents",
    });

    new cdk.CfnOutput(this, "EvaluationOutputBucketName", {
      value: evaluationOutputBucket.bucketName,
      description: "S3 bucket for evaluation outputs",
    });

    new cdk.CfnOutput(this, "EvaluationDatasetBucketName", {
      value: evaluationDatasetBucket.bucketName,
      description: "S3 bucket for evaluation datasets",
    });

    new cdk.CfnOutput(this, "VectorBucketName", {
      value: vectorBucketName,
      description: "S3 Vector Bucket",
    });

    new cdk.CfnOutput(this, "KnowledgeBaseId", {
      value: knowledgeBase.attrKnowledgeBaseId,
      description: "Knowledge Base ID",
    });

    new cdk.CfnOutput(this, "DataSourceId", {
      value: dataSource.attrDataSourceId,
      description: "Data Source ID",
    });

    new cdk.CfnOutput(this, "GuardrailId", {
      value: guardrail.attrGuardrailId,
      description: "Guardrail ID",
    });

    new cdk.CfnOutput(this, "GuardrailVersionOutput", {
      value: guardrailVersion.attrVersion,
      description: "Guardrail Version",
    });

    new cdk.CfnOutput(this, "KnowledgeBaseRoleArn", {
      value: kbRole.roleArn,
      description: "Knowledge Base IAM Role ARN",
    });

    new cdk.CfnOutput(this, "EvaluationRoleArn", {
      value: evalRole.roleArn,
      description: "Evaluation Job IAM Role ARN",
    });
  }
}
