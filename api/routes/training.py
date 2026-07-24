"""Training Routes - Model fine-tuning and adapter management endpoints.

Exposes the full training pipeline through the API:
- Start training runs (LoRA, QLoRA, full fine-tune)
- Upload/manage training datasets
- Monitor training progress
- Manage trained adapters (list, compare, merge, export)
- Memory estimation and dry-run validation
"""

from __future__ import annotations

import json
import os
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.state import app_state
from database.db import get_db

router = APIRouter()

# In-memory training run tracking (persists for app lifetime)
_training_runs: dict[str, dict[str, Any]] = {}
_adapter_index: dict[str, dict[str, Any]] = {}

# Data directory for uploaded datasets
DATA_DIR = Path(os.getenv("ARENA_DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

ADAPTER_DIR = Path(os.getenv("ARENA_ADAPTER_DIR", "./adapters"))
ADAPTER_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Pydantic models ----------


class TrainingStartRequest(BaseModel):
    """Request to start a training run."""
    base_model: str = "gpt2"
    dataset_path: str = ""
    strategy: str = "lora"  # lora, qlora, full_finetune
    epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 3e-4
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    max_seq_length: int = 2048
    warmup_ratio: float = 0.03
    weight_decay: float = 0.01
    lr_scheduler_type: str = "cosine"
    gradient_accumulation_steps: int = 4
    output_dir: str = ""
    dry_run: bool = False


class TrainingRunResponse(BaseModel):
    """Response for a training run."""
    run_id: str
    status: str
    base_model: str
    strategy: str
    dataset_path: str
    config: dict[str, Any]
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    final_loss: Optional[float] = None
    stages: dict[str, Any] = {}
    error: Optional[str] = None


class DatasetInfoResponse(BaseModel):
    """Dataset information."""
    name: str
    path: str
    format: str
    samples: int
    size_bytes: int
    preview: list[dict[str, Any]] = []


class AdapterInfoResponse(BaseModel):
    """Adapter information."""
    name: str
    base_model: str
    strategy: str
    rank: int
    alpha: int
    trainable_params: int = 0
    total_params: int = 0
    trainable_pct: float = 0.0
    dataset_samples: int = 0
    epochs: int = 0
    path: str = ""


class MemoryEstimateRequest(BaseModel):
    """Request for memory estimation."""
    model_size_b: float = 7.0
    batch_size: int = 4
    seq_length: int = 2048
    strategy: str = "qlora"
    rank: int = 16


# ---------- Routes ----------


@router.get("/runs", response_model=list[TrainingRunResponse])
async def list_runs() -> list[TrainingRunResponse]:
    """List all training runs."""
    runs = []
    for run_id, run_data in sorted(
        _training_runs.items(),
        key=lambda x: x[1].get("started_at", ""),
        reverse=True,
    ):
        runs.append(TrainingRunResponse(
            run_id=run_id,
            status=run_data.get("status", "unknown"),
            base_model=run_data.get("base_model", ""),
            strategy=run_data.get("strategy", ""),
            dataset_path=run_data.get("dataset_path", ""),
            config=run_data.get("config", {}),
            started_at=run_data.get("started_at", ""),
            completed_at=run_data.get("completed_at"),
            duration_seconds=run_data.get("duration_seconds"),
            final_loss=run_data.get("final_loss"),
            stages=run_data.get("stages", {}),
            error=run_data.get("error"),
        ))
    return runs


@router.get("/runs/{run_id}", response_model=TrainingRunResponse)
async def get_run(run_id: str) -> TrainingRunResponse:
    """Get a specific training run."""
    run_data = _training_runs.get(run_id)
    if not run_data:
        raise HTTPException(status_code=404, detail="Training run not found")
    return TrainingRunResponse(
        run_id=run_id,
        status=run_data.get("status", "unknown"),
        base_model=run_data.get("base_model", ""),
        strategy=run_data.get("strategy", ""),
        dataset_path=run_data.get("dataset_path", ""),
        config=run_data.get("config", {}),
        started_at=run_data.get("started_at", ""),
        completed_at=run_data.get("completed_at"),
        duration_seconds=run_data.get("duration_seconds"),
        final_loss=run_data.get("final_loss"),
        stages=run_data.get("stages", {}),
        error=run_data.get("error"),
    )


@router.post("/start", response_model=TrainingRunResponse)
async def start_training(request: TrainingStartRequest) -> TrainingRunResponse:
    """Start a training run.

    Kicks off the full pipeline: data prep → training → eval → export.
    Runs synchronously in this request for now (small datasets / dry-run);
    for production, this should be an async background task.
    """
    from core.training.pretrain import PipelineConfig, run_training_pipeline

    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.utcnow().isoformat()

    # Resolve dataset path
    dataset_path = request.dataset_path
    if not dataset_path:
        # Find the most recent uploaded dataset
        datasets = sorted(DATA_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if datasets:
            dataset_path = str(datasets[0])
        else:
            raise HTTPException(
                status_code=400,
                detail="No dataset_path provided and no uploaded datasets found. Upload a dataset first.",
            )

    if not Path(dataset_path).exists():
        raise HTTPException(status_code=400, detail=f"Dataset not found: {dataset_path}")

    # Build output directory
    output_dir = request.output_dir or str(ADAPTER_DIR)

    # Create pipeline config
    # Map strategy string
    strategy_map = {
        "lora": "lora",
        "qlora": "qlora",
        "full": "full_finetune",
        "full_finetune": "full_finetune",
    }
    strategy = strategy_map.get(request.strategy, "lora")

    # Select target modules based on model
    model_lower = request.base_model.lower()
    if "gpt2" in model_lower:
        target_modules = ["c_attn", "c_proj"]
    elif any(k in model_lower for k in ("llama", "mistral", "phi", "qwen")):
        target_modules = ["q_proj", "v_proj"]
    else:
        target_modules = ["c_attn", "c_proj"]

    config = PipelineConfig(
        project_name=f"training-{run_id}",
        base_model=request.base_model,
        train_data_path=dataset_path,
        output_dir=output_dir,
        epochs=request.epochs,
        batch_size=request.batch_size,
        learning_rate=request.learning_rate,
        strategy=strategy,
        lora_r=request.lora_r,
        lora_alpha=request.lora_alpha,
        lora_dropout=request.lora_dropout,
        lora_target_modules=target_modules,
        max_seq_length=request.max_seq_length,
    )

    # Register run as started
    _training_runs[run_id] = {
        "status": "running",
        "base_model": request.base_model,
        "strategy": strategy,
        "dataset_path": dataset_path,
        "config": config.__dict__,
        "started_at": started_at,
        "stages": {},
    }

    try:
        results = run_training_pipeline(config, dry_run=request.dry_run)

        completed_at = datetime.utcnow().isoformat()
        _training_runs[run_id].update({
            "status": results.get("status", "completed"),
            "completed_at": completed_at,
            "stages": results.get("stages", {}),
        })

        # Extract final loss if available
        training_stage = results.get("stages", {}).get("training", {})
        if training_stage.get("final_loss"):
            _training_runs[run_id]["final_loss"] = training_stage["final_loss"]

        # Calculate duration
        if started_at and completed_at:
            start_dt = datetime.fromisoformat(started_at)
            end_dt = datetime.fromisoformat(completed_at)
            _training_runs[run_id]["duration_seconds"] = (end_dt - start_dt).total_seconds()

        # Register adapter if training completed
        if results.get("status") == "completed" and not request.dry_run:
            export_stage = results.get("stages", {}).get("export", {})
            adapter_path = export_stage.get("path", "")
            _adapter_index[run_id] = {
                "name": f"adapter-{run_id}",
                "base_model": request.base_model,
                "strategy": strategy,
                "rank": request.lora_r,
                "alpha": request.lora_alpha,
                "path": adapter_path,
                "run_id": run_id,
                "created_at": completed_at,
            }

        return TrainingRunResponse(
            run_id=run_id,
            status=_training_runs[run_id]["status"],
            base_model=request.base_model,
            strategy=strategy,
            dataset_path=dataset_path,
            config=_training_runs[run_id]["config"],
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=_training_runs[run_id].get("duration_seconds"),
            final_loss=_training_runs[run_id].get("final_loss"),
            stages=_training_runs[run_id]["stages"],
        )

    except Exception as e:
        completed_at = datetime.utcnow().isoformat()
        _training_runs[run_id].update({
            "status": "failed",
            "completed_at": completed_at,
            "error": str(e),
        })
        raise HTTPException(status_code=500, detail=f"Training failed: {e}")


@router.post("/datasets/upload")
async def upload_dataset(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload a training dataset (JSONL, JSON, or CSV)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".jsonl", ".json", ".csv"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}. Use .jsonl, .json, or .csv")

    # Save file
    save_path = DATA_DIR / file.filename
    content = await file.read()
    save_path.write_bytes(content)

    # Validate and count samples
    samples = 0
    preview = []
    try:
        if ext == ".jsonl":
            with open(save_path) as f:
                for line in f:
                    if line.strip():
                        samples += 1
                        if samples <= 3:
                            preview.append(json.loads(line))
        elif ext == ".json":
            with open(save_path) as f:
                data = json.load(f)
                if isinstance(data, list):
                    samples = len(data)
                    preview = data[:3]
                else:
                    samples = 1
                    preview = [data]
        elif ext == ".csv":
            import csv
            with open(save_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    samples += 1
                    if samples <= 3:
                        preview.append(dict(row))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse dataset: {e}")

    return {
        "name": file.filename,
        "path": str(save_path),
        "format": ext.lstrip("."),
        "samples": samples,
        "size_bytes": len(content),
        "preview": preview,
    }


@router.get("/datasets", response_model=list[DatasetInfoResponse])
async def list_datasets() -> list[DatasetInfoResponse]:
    """List uploaded training datasets."""
    datasets = []
    for fpath in sorted(DATA_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if fpath.suffix not in (".jsonl", ".json", ".csv"):
            continue

        ext = fpath.suffix.lstrip(".")
        samples = 0
        preview = []
        try:
            if fpath.suffix == ".jsonl":
                with open(fpath) as f:
                    for line in f:
                        if line.strip():
                            samples += 1
                            if samples <= 2:
                                preview.append(json.loads(line))
            elif fpath.suffix == ".json":
                with open(fpath) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        samples = len(data)
                        preview = data[:2]
                    else:
                        samples = 1
                        preview = [data]
            elif fpath.suffix == ".csv":
                import csv
                with open(fpath) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        samples += 1
                        if samples <= 2:
                            preview.append(dict(row))
        except Exception:
            samples = -1  # parse error

        datasets.append(DatasetInfoResponse(
            name=fpath.name,
            path=str(fpath),
            format=ext,
            samples=samples,
            size_bytes=fpath.stat().st_size,
            preview=preview,
        ))

    return datasets


@router.get("/adapters", response_model=list[AdapterInfoResponse])
async def list_adapters() -> list[AdapterInfoResponse]:
    """List trained adapters."""
    adapters = []
    for adapter_id, data in _adapter_index.items():
        adapters.append(AdapterInfoResponse(
            name=data.get("name", ""),
            base_model=data.get("base_model", ""),
            strategy=data.get("strategy", ""),
            rank=data.get("rank", 16),
            alpha=data.get("alpha", 32),
            path=data.get("path", ""),
        ))

    # Also scan adapter directory for any saved adapters not in index
    for adapter_dir in ADAPTER_DIR.iterdir():
        if not adapter_dir.is_dir():
            continue
        info_file = adapter_dir / "adapter_info.json"
        if info_file.exists():
            try:
                with open(info_file) as f:
                    info = json.load(f)
                # Only add if not already in index
                if not any(a.name == info.get("name", adapter_dir.name) for a in adapters):
                    adapters.append(AdapterInfoResponse(
                        name=info.get("name", adapter_dir.name),
                        base_model=info.get("base_model", ""),
                        strategy=info.get("strategy", "lora"),
                        rank=info.get("rank", 16),
                        alpha=info.get("alpha", 32),
                        path=str(adapter_dir),
                    ))
            except Exception:
                pass

    return adapters


@router.post("/estimate-memory")
async def estimate_memory(request: MemoryEstimateRequest) -> dict[str, Any]:
    """Estimate memory requirements for a training configuration."""
    from core.training.loRA import calculate_lora_memory

    estimate = calculate_lora_memory(
        model_size_b=request.model_size_b,
        batch_size=request.batch_size,
        seq_length=request.seq_length,
        precision="fp16",
        lora_r=request.rank,
    )

    return {
        "model": f"{request.model_size_b}B",
        "strategy": request.strategy,
        "estimate": estimate,
    }


@router.post("/dry-run")
async def dry_run(request: TrainingStartRequest) -> TrainingRunResponse:
    """Validate a training configuration without actually training."""
    request.dry_run = True
    return await start_training(request)
