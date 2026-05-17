"""Benchmark module for measuring retrieval quality."""

import time


class BenchmarkSuite:
    """Suite of metrics for evaluating information retrieval benchmarks."""

    def __init__(self):
        self.metrics = {}

    def recall_at_k(self, retrieved, ground_truth, k):
        """Standard recall@k: |relevant_in_top_k| / |ground_truth|."""
        if not ground_truth:
            return 0.0
        top_k = set(retrieved[:k])
        relevant = len(top_k & ground_truth)
        return relevant / len(ground_truth)

    def precision_at_k(self, retrieved, ground_truth, k):
        """Standard precision@k: |relevant_in_top_k| / k."""
        if k <= 0:
            return 0.0
        top_k = set(retrieved[:k])
        relevant = len(top_k & ground_truth)
        return relevant / k

    def context_window_utilization(self, tokens_used, max_tokens):
        """Returns ratio of tokens used to budget, capped at 1.0."""
        if max_tokens <= 0:
            return 0.0
        return min(tokens_used / max_tokens, 1.0)

    def measure_latency(self, func):
        """Calls func(), returns (result, elapsed_seconds)."""
        start = time.perf_counter()
        result = func()
        elapsed = time.perf_counter() - start
        return result, elapsed

    def run_benchmark(self, queries, max_tokens=64000):
        """Run benchmark across multiple queries and aggregate metrics."""
        if not queries:
            self.metrics = {
                "recall": 0.0,
                "precision": 0.0,
                "recall@1": 0.0,
                "recall@5": 0.0,
                "precision@5": 0.0,
                "context_utilization": 0.0,
                "avg_latency": 0.0,
                "num_queries": 0,
            }
            return self.metrics

        total_recall_at_1 = 0.0
        total_recall_at_5 = 0.0
        total_precision_at_5 = 0.0
        total_context_util = 0.0
        total_latency = 0.0
        n = len(queries)

        for q in queries:
            ground_truth = q["ground_truth"]
            retrieved = q["retrieved"]
            tokens_used = q.get("tokens_used", 0)
            latency = q.get("latency", 0.0)

            total_recall_at_1 += self.recall_at_k(retrieved, ground_truth, k=1)
            total_recall_at_5 += self.recall_at_k(retrieved, ground_truth, k=5)
            total_precision_at_5 += self.precision_at_k(retrieved, ground_truth, k=5)
            total_context_util += self.context_window_utilization(tokens_used, max_tokens)
            total_latency += latency

        self.metrics = {
            "recall": total_recall_at_5 / n,
            "precision": total_precision_at_5 / n,
            "recall@1": total_recall_at_1 / n,
            "recall@5": total_recall_at_5 / n,
            "precision@5": total_precision_at_5 / n,
            "context_utilization": total_context_util / n,
            "avg_latency": total_latency / n,
            "latency": total_latency / n,
            "num_queries": n,
        }
        return self.metrics

    def generate_report(self, metrics):
        """Return a formatted string report with all metrics."""
        lines = ["=== Benchmark Report ===", ""]
        for key, value in metrics.items():
            if isinstance(value, float):
                lines.append(f"  {key}: {value:.4f}")
            else:
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)
