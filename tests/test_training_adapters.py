"""
Tests for Adapter Training Pipeline

These tests validate the adapter management, evaluation,
and configuration systems — not full model training,
which requires GPU resources and large model downloads.
"""

import pytest
from pathlib import Path
import sys

# Ensure repo root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.training.adapters import AdapterInfo, AdapterRegistry, AdapterManager
from core.training.config import AdapterTrainingConfig


class TestAdapterInfo:
    def test_create(self):
        info = AdapterInfo(
            adapter_path="./test-adapter",
            base_model="gpt2",
            strategy="lora",
            rank=16,
            trainable_params=4_000_000,
            total_params=124_000_000,
        )
        assert info.name == "test-adapter"
        assert info.trainable_pct == pytest.approx(4_000_000 / 124_000_000 * 100, rel=1e-3)

    def test_to_dict(self):
        info = AdapterInfo(adapter_path="./adapters/my", base_model="gpt2", strategy="lora")
        d = info.to_dict()
        assert d["base_model"] == "gpt2"
        assert d["name"] == "my"

    def test_save_load_metadata(self, tmp_path):
        info = AdapterInfo(adapter_path=str(tmp_path / "adapter"), base_model="gpt2", strategy="qlora", rank=32)
        meta_path = info.save_metadata(str(tmp_path / "adapter" / "adapter_info.json"))
        loaded = AdapterInfo.load_metadata(meta_path)
        assert loaded.base_model == info.base_model
        assert loaded.rank == info.rank


class TestAdapterRegistry:
    def test_register_and_list(self, tmp_path):
        registry = AdapterRegistry(registry_dir=str(tmp_path / "registry"))
        info = AdapterInfo(adapter_path=str(tmp_path / "adapter"), base_model="gpt2", strategy="lora")
        registry.register(info)
        adapters = registry.list_adapters()
        assert len(adapters) == 1
        assert adapters[0].base_model == "gpt2"


class TestAdapterConfig:
    def test_default_config(self):
        config = AdapterTrainingConfig()
        assert config.strategy == "lora"
        assert config.rank == 16
        assert config.base_model == "gpt2"

    def test_config_to_dict(self):
        config = AdapterTrainingConfig(adapter_name="test")
        d = config.to_dict()
        assert d["adapter_name"] == "test"
        assert "output_path" in d


class TestAdapterMemoryEstimates:
    def test_memory_estimate_qlora(self):
        manager = AdapterManager("gpt2")
        estimates = manager.estimate_memory(model_size_b=7.0, strategy="qlora", batch_size=4)
        assert estimates["base_model_memory_gb"] < 10  # 4-bit quantization should be ~3.5GB for 7B
        assert "adapter_memory_gb" in estimates

    def test_memory_estimate_lora(self):
        manager = AdapterManager("gpt2")
        estimates = manager.estimate_memory(model_size_b=7.0, strategy="lora", batch_size=4)
        assert estimates["base_model_memory_gb"] > 10  # fp16 should be ~14GB


class TestAdapterPipelineFixes:
    def test_strategy_mapping_in_pretrain(self):
        # The pretrain pipeline should handle string strategies correctly
        from core.training.pretrain import PipelineConfig
        config = PipelineConfig(strategy="qlora", base_model="gpt2")
        assert config.strategy == "qlora"

    def test_training_config_enum_handling(self):
        from core.training.trainer import TrainingConfig, TrainingStrategy
        tc = TrainingConfig(strategy=TrainingStrategy.QLORA)
        assert tc.strategy == TrainingStrategy.QLORA


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
