#!/usr/bin/env node
/**
 * Amazon Bedrock RAG 評価フレームワーク CDK アプリケーション
 *
 * ブログ記事用の作業環境を構築します。
 * タイトル: [Amazon Bedrock Evaluations] Knowledge Bases への Guardrails の適用による、
 *          コンテキストグラウンディング（ハルシネーション防止）の有効性を評価してみました
 *
 * 作成するリソース（プレフィックスは cdk.json の project-name で設定）:
 * 1. S3 バケット（データソース用）
 * 2. S3 バケット（評価出力用）
 *    └ with-guardrails/                  - Guardrails あり評価結果
 *    └ without-guardrails/               - Guardrails なし評価結果
 * 3. S3 バケット（評価データセット用）
 * 4. S3 Vector Bucket
 * 5. S3 Vector Index
 * 6. Knowledge Base
 * 7. Data Source                         - KB に紐づく
 * 8. Guardrails
 * 9. IAM ロール（KB 用）
 * 10. IAM ロール（評価ジョブ用）
 */
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { MainStack } from "../lib/main-stack";

const app = new cdk.App();

// プロジェクト名プレフィックス（cdk.json の context から取得）
const projectName = app.node.tryGetContext("project-name") || "bedrock-rag-eval-guardrails-grounding";

// 環境設定
const env: cdk.Environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || "ap-northeast-1",
};

// メインスタック（全リソースを含む）
new MainStack(app, `${projectName}-stack`, {
  projectName,
  env,
  description:
    "Amazon Bedrock RAG Evaluation Framework - Blog Work Environment",
});
