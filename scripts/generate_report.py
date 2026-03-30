#!/usr/bin/env python3
"""
評価結果レポート生成スクリプト

S3から評価結果を取得し、Guardrailsあり/なしを比較したMarkdownレポートを生成します。
オプションでLLM（Claude）を使用して分析コメントを追加できます。

使用方法:
    python scripts/generate_report.py --account-id 123456789012 [--use-llm]
"""
import argparse
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def download_from_s3(s3_uri: str, local_path: str) -> bool:
    """S3からファイルをダウンロード"""
    try:
        result = subprocess.run(
            ["aws", "s3", "cp", s3_uri, local_path, "--recursive", "--region", "ap-northeast-1"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        print(f"S3ダウンロードエラー: {e}")
        return False


def find_output_jsonl(local_dir: str) -> str | None:
    """評価結果のJSONLファイルを検索"""
    for path in Path(local_dir).rglob("*_output.jsonl"):
        return str(path)
    return None


def parse_evaluation_results(jsonl_path: str) -> list[dict[str, Any]]:
    """評価結果JSONLをパース"""
    results = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                for turn in data.get("conversationTurns", []):
                    prompt_text = ""
                    input_record = turn.get("inputRecord", {})
                    prompt = input_record.get("prompt", {})
                    content = prompt.get("content", [])
                    if content:
                        prompt_text = content[0].get("text", "")

                    output = turn.get("output", {})
                    response_text = output.get("text", "")

                    metrics = {}
                    for result in turn.get("results", []):
                        metric_name = result.get("metricName", "").replace("Builtin.", "")
                        metrics[metric_name] = result.get("result", 0)

                    results.append({
                        "prompt": prompt_text,
                        "response": response_text,
                        "metrics": metrics
                    })
    return results


def calculate_averages(results: list[dict[str, Any]]) -> dict[str, float]:
    """メトリクスの平均値を計算"""
    metric_sums: dict[str, list[float]] = {}

    for result in results:
        for metric, value in result.get("metrics", {}).items():
            if metric not in metric_sums:
                metric_sums[metric] = []
            if value is not None:
                metric_sums[metric].append(value)

    averages = {}
    for metric, values in metric_sums.items():
        valid_values = [v for v in values if v is not None]
        if valid_values:
            averages[metric] = sum(valid_values) / len(valid_values)

    return averages


def find_significant_differences(
    without_results: list[dict[str, Any]],
    with_results: list[dict[str, Any]],
    threshold: float = 0.5
) -> list[dict[str, Any]]:
    """大きな差がある質問を特定"""
    differences = []

    metrics = ["Correctness", "Completeness", "Faithfulness", "Helpfulness"]

    for i, (without, with_) in enumerate(zip(without_results, with_results)):
        for metric in metrics:
            without_score = without.get("metrics", {}).get(metric)
            with_score = with_.get("metrics", {}).get(metric)
            if without_score is None or with_score is None:
                continue
            diff = abs(with_score - without_score)

            if diff >= threshold:
                differences.append({
                    "index": i + 1,
                    "prompt": without.get("prompt", ""),
                    "metric": metric,
                    "without_score": without_score,
                    "with_score": with_score,
                    "diff": with_score - without_score,
                    "without_response": without.get("response", ""),
                    "with_response": with_.get("response", "")
                })

    # 差分の絶対値でソート
    differences.sort(key=lambda x: abs(x["diff"]), reverse=True)
    return differences


def generate_llm_analysis(
    without_avg: dict[str, float],
    with_avg: dict[str, float],
    differences: list[dict[str, Any]]
) -> str:
    """LLMを使用して分析コメントを生成"""
    try:
        import boto3

        client = boto3.client("bedrock-runtime", region_name="ap-northeast-1")

        # プロンプト作成
        prompt = f"""以下の評価結果を分析し、Guardrailsの効果について簡潔に考察してください。

## 平均スコア比較
| メトリクス | Guardrailsなし | Guardrailsあり | 差分 |
|-----------|---------------|---------------|------|
| Correctness | {without_avg.get('Correctness', 0):.3f} | {with_avg.get('Correctness', 0):.3f} | {with_avg.get('Correctness', 0) - without_avg.get('Correctness', 0):+.3f} |
| Completeness | {without_avg.get('Completeness', 0):.3f} | {with_avg.get('Completeness', 0):.3f} | {with_avg.get('Completeness', 0) - without_avg.get('Completeness', 0):+.3f} |
| Faithfulness | {without_avg.get('Faithfulness', 0):.3f} | {with_avg.get('Faithfulness', 0):.3f} | {with_avg.get('Faithfulness', 0) - without_avg.get('Faithfulness', 0):+.3f} |
| Helpfulness | {without_avg.get('Helpfulness', 0):.3f} | {with_avg.get('Helpfulness', 0):.3f} | {with_avg.get('Helpfulness', 0) - without_avg.get('Helpfulness', 0):+.3f} |

## 差が大きかった質問（上位3件）
"""
        for i, diff in enumerate(differences[:3]):
            prompt += f"""
### {i+1}. {diff['prompt'][:50]}...
- メトリクス: {diff['metric']}
- Guardrailsなし: {diff['without_score']:.3f}
- Guardrailsあり: {diff['with_score']:.3f}
- 差分: {diff['diff']:+.3f}
"""

        prompt += """
上記の結果から、Guardrails（コンテキストグラウンディング）の効果について、
200文字程度で簡潔に考察してください。
"""

        response = client.converse(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 500}
        )

        return response["output"]["message"]["content"][0]["text"]

    except Exception as e:
        return f"LLM分析の生成に失敗しました: {e}"


def generate_markdown_report(
    without_results: list[dict[str, Any]],
    with_results: list[dict[str, Any]],
    without_avg: dict[str, float],
    with_avg: dict[str, float],
    differences: list[dict[str, Any]],
    config: dict[str, str],
    llm_analysis: str | None = None
) -> str:
    """Markdownレポートを生成"""

    report = f"""# 評価結果レポート

## 実行日時
{datetime.now().strftime('%Y年%m月%d日 %H:%M')}

## 評価設定

| 項目 | 設定値 |
|------|--------|
| テストケース数 | {len(without_results)}件 |
| 回答生成モデル | Claude 3 Haiku |
| 評価モデル | Claude 3.5 Sonnet |
| Knowledge Base ID | {config.get('kb_id', 'N/A')} |
| Guardrail ID | {config.get('guardrail_id', 'N/A')} |

---

## 評価スコア比較（平均）

| メトリクス | Guardrailsなし | Guardrailsあり | 差分 |
|-----------|---------------|---------------|------|
| Correctness | {without_avg.get('Correctness', 0):.3f} | {with_avg.get('Correctness', 0):.3f} | {with_avg.get('Correctness', 0) - without_avg.get('Correctness', 0):+.3f} |
| Completeness | {without_avg.get('Completeness', 0):.3f} | {with_avg.get('Completeness', 0):.3f} | {with_avg.get('Completeness', 0) - without_avg.get('Completeness', 0):+.3f} |
| Faithfulness | {without_avg.get('Faithfulness', 0):.3f} | {with_avg.get('Faithfulness', 0):.3f} | {with_avg.get('Faithfulness', 0) - without_avg.get('Faithfulness', 0):+.3f} |
| Helpfulness | {without_avg.get('Helpfulness', 0):.3f} | {with_avg.get('Helpfulness', 0):.3f} | {with_avg.get('Helpfulness', 0) - without_avg.get('Helpfulness', 0):+.3f} |

### メトリクスの説明

- **Correctness**: 回答の正確性（期待される回答との一致度）
- **Completeness**: 回答の完全性（必要な情報がすべて含まれているか）
- **Faithfulness**: 忠実性（ソースドキュメントに基づいているか、ハルシネーション回避度）
- **Helpfulness**: 有用性（ユーザーにとって役立つ回答か）

---

## 質問別の詳細結果

### Guardrailsなし

| # | 質問 | Correct | Complete | Faithful | Helpful |
|---|------|---------|----------|----------|---------|
"""

    for i, result in enumerate(without_results):
        prompt = result.get("prompt", "")[:50]
        metrics = result.get("metrics", {})
        corr = metrics.get('Correctness') or 0
        comp = metrics.get('Completeness') or 0
        faith = metrics.get('Faithfulness') or 0
        help_ = metrics.get('Helpfulness') or 0
        report += f"| {i+1} | {prompt}... | {corr:.2f} | {comp:.2f} | {faith:.2f} | {help_:.2f} |\n"

    report += """
### Guardrailsあり

| # | 質問 | Correct | Complete | Faithful | Helpful |
|---|------|---------|----------|----------|---------|
"""

    for i, result in enumerate(with_results):
        prompt = result.get("prompt", "")[:50]
        metrics = result.get("metrics", {})
        corr = metrics.get('Correctness') or 0
        comp = metrics.get('Completeness') or 0
        faith = metrics.get('Faithfulness') or 0
        help_ = metrics.get('Helpfulness') or 0
        report += f"| {i+1} | {prompt}... | {corr:.2f} | {comp:.2f} | {faith:.2f} | {help_:.2f} |\n"

    report += """
---

## 差が大きかった質問の分析

"""

    for diff in differences[:5]:
        report += f"""### 質問 {diff['index']}: {diff['prompt'][:60]}...

**メトリクス**: {diff['metric']}
- Guardrailsなし: {diff['without_score']:.3f}
- Guardrailsあり: {diff['with_score']:.3f}
- 差分: {diff['diff']:+.3f}

**Guardrailsなしの回答**:
> {diff['without_response'][:200]}{'...' if len(diff['without_response']) > 200 else ''}

**Guardrailsありの回答**:
> {diff['with_response'][:200]}{'...' if len(diff['with_response']) > 200 else ''}

---

"""

    # 結論
    total_diff = sum([
        with_avg.get('Correctness', 0) - without_avg.get('Correctness', 0),
        with_avg.get('Completeness', 0) - without_avg.get('Completeness', 0),
        with_avg.get('Faithfulness', 0) - without_avg.get('Faithfulness', 0),
        with_avg.get('Helpfulness', 0) - without_avg.get('Helpfulness', 0)
    ]) / 4

    report += f"""## 結論

Guardrailsを有効にすることで、平均スコアが **{total_diff:+.3f}** ポイント変化しました。

"""

    if llm_analysis:
        report += f"""### LLMによる分析

{llm_analysis}
"""

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="評価結果レポート生成")
    parser.add_argument("--account-id", required=True, help="AWSアカウントID")
    parser.add_argument("--use-llm", action="store_true", help="LLMで分析コメントを生成")
    parser.add_argument("--output", default="評価結果.md", help="出力ファイル名")
    parser.add_argument("--kb-id", default="", help="Knowledge Base ID（レポート用）")
    parser.add_argument("--guardrail-id", default="", help="Guardrail ID（レポート用）")
    args = parser.parse_args()

    bucket_name = f"bedrock-rag-eval-output-{args.account_id}"

    print("=" * 50)
    print("評価結果レポート生成")
    print("=" * 50)

    # 一時ディレクトリを作成
    with tempfile.TemporaryDirectory() as tmpdir:
        without_dir = Path(tmpdir) / "without-guardrails"
        with_dir = Path(tmpdir) / "with-guardrails"
        without_dir.mkdir()
        with_dir.mkdir()

        # S3からダウンロード
        print("\n[1/5] S3から評価結果をダウンロード中...")

        without_s3 = f"s3://{bucket_name}/without-guardrails/"
        with_s3 = f"s3://{bucket_name}/with-guardrails/"

        if not download_from_s3(without_s3, str(without_dir)):
            print(f"エラー: {without_s3} のダウンロードに失敗しました")
            return

        if not download_from_s3(with_s3, str(with_dir)):
            print(f"エラー: {with_s3} のダウンロードに失敗しました")
            return

        # JSONLファイルを検索
        print("[2/5] 評価結果ファイルを検索中...")

        without_jsonl = find_output_jsonl(str(without_dir))
        with_jsonl = find_output_jsonl(str(with_dir))

        if not without_jsonl:
            print("エラー: Guardrailsなしの評価結果が見つかりません")
            return

        if not with_jsonl:
            print("エラー: Guardrailsありの評価結果が見つかりません")
            return

        print(f"  - Guardrailsなし: {Path(without_jsonl).name}")
        print(f"  - Guardrailsあり: {Path(with_jsonl).name}")

        # パース
        print("[3/5] 評価結果をパース中...")

        without_results = parse_evaluation_results(without_jsonl)
        with_results = parse_evaluation_results(with_jsonl)

        print(f"  - Guardrailsなし: {len(without_results)}件")
        print(f"  - Guardrailsあり: {len(with_results)}件")

        # 集計
        print("[4/5] メトリクスを集計中...")

        without_avg = calculate_averages(without_results)
        with_avg = calculate_averages(with_results)

        differences = find_significant_differences(without_results, with_results)

        print(f"  - 大きな差がある質問: {len(differences)}件")

        # LLM分析（オプション）
        llm_analysis = None
        if args.use_llm:
            print("[4.5/5] LLMで分析中...")
            llm_analysis = generate_llm_analysis(without_avg, with_avg, differences)

        # レポート生成
        print("[5/5] Markdownレポートを生成中...")

        config = {
            "kb_id": args.kb_id or "N/A",
            "guardrail_id": args.guardrail_id or "N/A"
        }

        report = generate_markdown_report(
            without_results,
            with_results,
            without_avg,
            with_avg,
            differences,
            config,
            llm_analysis
        )

        # 出力
        output_path = Path(args.output)
        output_path.write_text(report, encoding="utf-8")

        print("\n" + "=" * 50)
        print(f"レポートを生成しました: {output_path.absolute()}")
        print("=" * 50)

        # サマリー表示
        print("\n## 評価スコア比較（平均）")
        print(f"| メトリクス | Guardrailsなし | Guardrailsあり | 差分 |")
        print(f"|-----------|---------------|---------------|------|")
        for metric in ["Correctness", "Completeness", "Faithfulness", "Helpfulness"]:
            w = without_avg.get(metric, 0)
            g = with_avg.get(metric, 0)
            print(f"| {metric} | {w:.3f} | {g:.3f} | {g-w:+.3f} |")


if __name__ == "__main__":
    main()
