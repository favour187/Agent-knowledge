"""
Adapter Evaluation Metrics

Evaluation specifically designed for adapter/fine-tuning performance.
Uses standard NLP metrics plus adapter-specific diagnostics.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from sklearn.metrics import accuracy_score, f1_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class AdapterEvaluator:
    """Evaluator for adapter performance."""

    def __init__(self, tokenizer: Any):
        self.tokenizer = tokenizer

    def perplexity(self, model: Any, dataset: Any) -> Optional[float]:
        """Calculate perplexity on a dataset."""
        try:
            import torch
            import torch.nn.functional as F
            model.eval()
            total_loss = 0.0
            total_items = 0

            for item in dataset:
                if isinstance(item, dict):
                    input_ids = item.get("input_ids")
                    labels = item.get("labels")
                    if input_ids is None or labels is None:
                        continue
                else:
                    input_ids = item["input_ids"]
                    labels = item["labels"]

                if isinstance(input_ids, list):
                    input_ids = torch.tensor([input_ids])
                    labels = torch.tensor([labels])
                else:
                    input_ids = input_ids.unsqueeze(0) if input_ids.dim() == 1 else input_ids
                    labels = labels.unsqueeze(0) if labels.dim() == 1 else labels

                with torch.no_grad():
                    outputs = model(input_ids=input_ids, labels=labels)
                    loss = outputs.loss
                    if loss is not None:
                        total_loss += loss.item()
                        total_items += 1

            avg_loss = total_loss / max(total_items, 1)
            perplexity = np.exp(avg_loss) if NUMPY_AVAILABLE else float(avg_loss)
            return perplexity
        except Exception as e:
            logger.error("perplexity_calculation_failed", error=str(e))
            return None

    def evaluate_accuracy(
        self,
        model: Any,
        dataset: Any,
        max_length: int = 2048,
    ) -> dict[str, float]:
        """Evaluate with accuracy-style metrics for instruction data."""
        try:
            predictions = []
            references = []

            for item in dataset:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    instruction = item.get("instruction", "")
                    reference = item.get("response", item.get("output", ""))
                else:
                    text = str(item)
                    instruction = ""
                    reference = ""

                # Skip if no reference available
                if not reference:
                    continue

                # Generate prediction
                input_ids = self.tokenizer(
                    instruction or text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=max_length,
                )

                import torch
                with torch.no_grad():
                    outputs = model.generate(
                        **input_ids,
                        max_new_tokens=50,
                        temperature=0.1,
                        do_sample=False,
                    )
                pred_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

                predictions.append(pred_text)
                references.append(reference)

            # Simple overlap metric
            scores = []
            for pred, ref in zip(predictions, references):
                pred_words = set(pred.lower().split())
                ref_words = set(ref.lower().split())
                overlap = len(pred_words & ref_words) / max(len(pred_words | ref_words), 1)
                scores.append(overlap)

            avg_score = float(np.mean(scores)) if scores and NUMPY_AVAILABLE else 0.0
            return {
                "adapter_accuracy_proxy": avg_score,
                "samples_evaluated": len(scores),
                "predictions": predictions[:3],
                "references": references[:3],
            }
        except Exception as e:
            logger.error("adapter_accuracy_evaluation_failed", error=str(e))
            return {"adapter_accuracy_proxy": 0.0, "error": str(e)}
