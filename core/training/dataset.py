"""
Dataset Handling

Utilities for loading, preprocessing, and managing training datasets.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import structlog

logger = structlog.get_logger(__name__)

# Try to import datasets library
try:
    from datasets import (
        Dataset as HFDataset,
        DatasetDict,
        load_dataset,
        load_from_disk,
        concatenate_datasets,
    )
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False
    HFDataset = None
    DatasetDict = None


@dataclass
class DatasetConfig:
    """Configuration for dataset loading."""
    name: str = ""
    path: str = ""
    split: str = "train"
    text_column: str = "text"
    chat_column: str = "messages"
    
    # Preprocessing
    max_length: int = 2048
    truncation: bool = True
    padding: bool = False
    
    # Filtering
    min_length: int = 0
    max_length_filter: Optional[int] = None
    filter_empty: bool = True
    
    # Augmentation
    shuffle: bool = False
    shuffle_seed: int = 42


class Dataset:
    """
    Dataset wrapper for training.
    
    Supports:
    - HuggingFace datasets
    - JSON/JSONL files
    - CSV files
    - Direct list input
    - Chat/conversation formats
    """

    def __init__(
        self,
        data: Any,
        text_column: str = "text",
        config: Optional[DatasetConfig] = None,
    ):
        self._dataset = data
        self.text_column = text_column
        self.config = config or DatasetConfig()
        
        if not DATASETS_AVAILABLE and data is not None:
            logger.warning("datasets_library_not_available")

    @classmethod
    def from_list(
        cls,
        data: list[dict[str, Any]],
        text_column: str = "text",
    ) -> "Dataset":
        """Create dataset from a list of dictionaries."""
        if DATASETS_AVAILABLE:
            hf_dataset = HFDataset.from_list(data)
            return cls(hf_dataset, text_column)
        return cls(data, text_column)

    @classmethod
    def from_json(
        cls,
        path: str,
        text_column: str = "text",
        split: Optional[str] = None,
    ) -> "Dataset":
        """Load dataset from JSON/JSONL file."""
        if DATASETS_AVAILABLE:
            hf_dataset = load_dataset("json", data_files=path, split=split)
            # If split is None, load_dataset returns DatasetDict; select 'train' split
            if isinstance(hf_dataset, DatasetDict) and 'train' in hf_dataset:
                hf_dataset = hf_dataset['train']
            return cls(hf_dataset, text_column)
        
        # Fallback to manual loading
        data = []
        with open(path, "r") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
        return cls.from_list(data, text_column)

    @classmethod
    def from_csv(
        cls,
        path: str,
        text_column: str = "text",
        split: Optional[str] = None,
    ) -> "Dataset":
        """Load dataset from CSV file."""
        if DATASETS_AVAILABLE:
            hf_dataset = load_dataset("csv", data_files=path, split=split)
            return cls(hf_dataset, text_column)
        
        import csv
        data = []
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
        return cls.from_list(data, text_column)

    @classmethod
    def load_huggingface(
        cls,
        name: str,
        text_column: str = "text",
        split: Optional[str] = None,
        config_name: Optional[str] = None,
    ) -> "Dataset":
        """Load from HuggingFace Hub."""
        if not DATASETS_AVAILABLE:
            raise ImportError("datasets library required for HuggingFace loading")
        
        hf_dataset = load_dataset(name, config_name, split=split)
        return cls(hf_dataset, text_column)

    @classmethod
    def from_conversations(
        cls,
        data: list[dict[str, Any]],
        role_mapping: Optional[dict[str, str]] = None,
    ) -> "Dataset":
        """
        Create dataset from conversation data.
        
        Expected format:
        [
            {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]},
            ...
        ]
        """
        role_mapping = role_mapping or {
            "user": "user",
            "assistant": "assistant",
            "system": "system",
        }
        
        formatted = []
        for item in data:
            messages = item.get("messages", [])
            text = ""
            for msg in messages:
                role = role_mapping.get(msg.get("role", ""), msg.get("role", ""))
                content = msg.get("content", "")
                text += f"<|{role}|>\n{content}<|end|>\n"
            formatted.append({"text": text})
        
        return cls.from_list(formatted, "text")

    def map(
        self,
        function: Callable,
        batched: bool = False,
        remove_columns: Optional[list[str]] = None,
    ) -> "Dataset":
        """Apply a function to the dataset."""
        if DATASETS_AVAILABLE and hasattr(self._dataset, 'map'):
            self._dataset = self._dataset.map(function, batched=batched, remove_columns=remove_columns)
        return self

    def filter(
        self,
        function: Callable,
        with_indices: bool = False,
    ) -> "Dataset":
        """Filter the dataset."""
        if DATASETS_AVAILABLE and hasattr(self._dataset, 'filter'):
            self._dataset = self._dataset.filter(function, with_indices=with_indices)
        return self

    def shuffle(self, seed: int = 42) -> "Dataset":
        """Shuffle the dataset."""
        if DATASETS_AVAILABLE and hasattr(self._dataset, 'shuffle'):
            self._dataset = self._dataset.shuffle(seed=seed)
        return self

    def split(
        self,
        train_size: float = 0.9,
        seed: int = 42,
    ) -> tuple["Dataset", "Dataset"]:
        """Split into train and test/eval."""
        if DATASETS_AVAILABLE and hasattr(self._dataset, 'train_test_split'):
            split_data = self._dataset.train_test_split(train_size=train_size, seed=seed)
            train = Dataset(split_data["train"], self.text_column)
            eval_ds = Dataset(split_data["test"], self.text_column)
            return train, eval_ds
        return self, self

    def select(self, indices: list[int]) -> "Dataset":
        """Select rows by indices."""
        if DATASETS_AVAILABLE and hasattr(self._dataset, 'select'):
            self._dataset = self._dataset.select(indices)
        return self

    def select_range(self, start: int, end: int) -> "Dataset":
        """Select rows in a range."""
        return self.select(list(range(start, end)))

    def take(self, n: int) -> "Dataset":
        """Take first n rows."""
        return self.select(list(range(min(n, len(self)))))

    def skip(self, n: int) -> "Dataset":
        """Skip first n rows."""
        return self.select(list(range(n, len(self))))

    def __len__(self) -> int:
        if DATASETS_AVAILABLE and hasattr(self._dataset, '__len__'):
            return len(self._dataset)
        if isinstance(self._dataset, list):
            return len(self._dataset)
        return 0

    def __getitem__(self, idx: int) -> dict[str, Any]:
        if DATASETS_AVAILABLE and hasattr(self._dataset, '__getitem__'):
            return self._dataset[idx]
        if isinstance(self._dataset, list):
            return self._dataset[idx]
        raise IndexError(f"Index {idx} out of range")

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for i in range(len(self)):
            yield self[i]

    def to_list(self) -> list[dict[str, Any]]:
        """Convert to list."""
        if DATASETS_AVAILABLE and hasattr(self._dataset, 'to_list'):
            return self._dataset.to_list()
        return [self[i] for i in range(len(self))]

    def save_to_disk(self, path: str) -> None:
        """Save dataset to disk."""
        if DATASETS_AVAILABLE and hasattr(self._dataset, 'save_to_disk'):
            self._dataset.save_to_disk(path)
            logger.info("dataset_saved", path=path)

    @classmethod
    def load_from_disk(cls, path: str) -> "Dataset":
        """Load dataset from disk."""
        if not DATASETS_AVAILABLE:
            raise ImportError("datasets library required")
        hf_dataset = load_from_disk(path)
        return cls(hf_dataset)

    def preprocess_for_training(
        self,
        tokenizer: Any,
        max_length: int = 2048,
        add_special_tokens: bool = True,
    ) -> "Dataset":
        """Preprocess dataset for training."""
        def tokenize_function(examples):
            texts = examples.get(self.text_column, [])
            if isinstance(texts, str):
                texts = [texts]
            
            result = tokenizer(
                texts,
                truncation=True,
                max_length=max_length,
                padding=False,
                add_special_tokens=add_special_tokens,
            )
            result["labels"] = result["input_ids"].copy()
            return result

        if DATASETS_AVAILABLE and hasattr(self._dataset, 'map'):
            self._dataset = self._dataset.map(
                tokenize_function,
                batched=True,
                remove_columns=[c for c in self._dataset.column_names if c != self.text_column],
            )
        return self


class DataCollator:
    """
    Collates batches of data for training.
    """

    def __init__(
        self,
        tokenizer: Any,
        max_length: int = 2048,
        pad_to_multiple_of: Optional[int] = None,
        label_pad_token_id: int = -100,
    ):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.pad_to_multiple_of = pad_to_multiple_of
        self.label_pad_token_id = label_pad_token_id

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        """Collate a batch."""
        import torch
        
        # Extract inputs and labels
        batch = {
            "input_ids": [],
            "attention_mask": [],
            "labels": [],
        }
        
        for feature in features:
            input_ids = feature.get("input_ids", [])
            labels = feature.get("labels", input_ids)
            
            # Truncate if needed
            if len(input_ids) > self.max_length:
                input_ids = input_ids[:self.max_length]
                labels = labels[:self.max_length]
            
            batch["input_ids"].append(input_ids)
            batch["attention_mask"].append([1] * len(input_ids))
            batch["labels"].append(labels)
        
        # Pad sequences
        max_len = max(len(ids) for ids in batch["input_ids"])
        if self.pad_to_multiple_of:
            max_len = ((max_len + self.pad_to_multiple_of - 1) // self.pad_to_multiple_of) * self.pad_to_multiple_of
        
        padded_batch = {
            "input_ids": [],
            "attention_mask": [],
            "labels": [],
        }
        
        for i in range(len(batch["input_ids"])):
            pad_len = max_len - len(batch["input_ids"][i])
            
            padded_batch["input_ids"].append(
                batch["input_ids"][i] + [self.tokenizer.pad_token_id or 0] * pad_len
            )
            padded_batch["attention_mask"].append(
                batch["attention_mask"][i] + [0] * pad_len
            )
            
            # Pad labels with special value
            padded_labels = batch["labels"][i] + [self.label_pad_token_id] * pad_len
            padded_batch["labels"].append(padded_labels)
        
        # Convert to tensors
        return {
            "input_ids": torch.tensor(padded_batch["input_ids"]),
            "attention_mask": torch.tensor(padded_batch["attention_mask"]),
            "labels": torch.tensor(padded_batch["labels"]),
        }


def prepare_chat_dataset(
    data: list[dict[str, Any]],
    tokenizer: Any,
    max_length: int = 2048,
    system_prompt: str = "",
) -> list[dict[str, Any]]:
    """
    Prepare a chat dataset for training.
    
    Formats conversations into training examples with proper special tokens.
    """
    formatted = []
    
    for item in data:
        messages = item.get("messages", [])
        
        text = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                text += f"<|system|>\n{content}\n"
            elif role == "user":
                text += f"<|user|>\n{content}\n"
            elif role == "assistant":
                text += f"<|assistant|>\n{content}\n"
        
        text += "<|assistant|>"  # Prompt for generation
        
        # Tokenize and create example
        encoding = tokenizer(
            text,
            truncation=True,
            max_length=max_length,
            return_tensors=None,
        )
        
        # Labels are the same as input_ids
        encoding["labels"] = encoding["input_ids"].copy()
        
        formatted.append(encoding)
    
    return formatted


def prepare_instruction_dataset(
    data: list[dict[str, Any]],
    tokenizer: Any,
    max_length: int = 2048,
    prompt_template: str = "### Instruction:\n{instruction}\n\n### Response:\n",
) -> list[dict[str, Any]]:
    """
    Prepare an instruction-following dataset for training.
    """
    formatted = []
    
    for item in data:
        instruction = item.get("instruction", "")
        response = item.get("response", item.get("output", ""))
        
        text = prompt_template.format(instruction=instruction) + response
        
        encoding = tokenizer(
            text,
            truncation=True,
            max_length=max_length,
            return_tensors=None,
        )
        
        encoding["labels"] = encoding["input_ids"].copy()
        formatted.append(encoding)
    
    return formatted
