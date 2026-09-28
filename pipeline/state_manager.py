import os
import json
import logging
from typing import Optional, List
from datetime import datetime

from storage.models import PipelineRun

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, checkpoints_dir: str = "checkpoints"):
        self.checkpoints_dir = checkpoints_dir
        os.makedirs(self.checkpoints_dir, exist_ok=True)

    def _get_filepath(self, run_id: str) -> str:
        return os.path.join(self.checkpoints_dir, f"{run_id}.json")

    def save_checkpoint(self, run: PipelineRun) -> None:
        filepath = self._get_filepath(run.run_id)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(run.model_dump_json(indent=2))
        except Exception as e:
            logger.error(f"Failed to save checkpoint for run {run.run_id}: {e}")

    def load_checkpoint(self, run_id: str) -> Optional[PipelineRun]:
        filepath = self._get_filepath(run_id)
        if not os.path.exists(filepath):
            return None
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return PipelineRun.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load checkpoint for run {run_id}: {e}")
            return None

    def list_checkpoints(self) -> List[str]:
        checkpoints = []
        try:
            for filename in os.listdir(self.checkpoints_dir):
                if filename.endswith(".json"):
                    checkpoints.append(filename[:-5])
        except Exception as e:
            logger.error(f"Failed to list checkpoints: {e}")
        return checkpoints

    def delete_checkpoint(self, run_id: str) -> None:
        filepath = self._get_filepath(run_id)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                logger.error(f"Failed to delete checkpoint for run {run_id}: {e}")

    def get_last_incomplete(self) -> List[PipelineRun]:
        incomplete_runs = []
        run_ids = self.list_checkpoints()
        for run_id in run_ids:
            run = self.load_checkpoint(run_id)
            if run and run.status and run.status.value not in ["COMPLETED", "FAILED"]:
                incomplete_runs.append(run)
        return incomplete_runs
