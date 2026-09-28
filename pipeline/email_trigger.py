import os
import time
import json
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

class EmailEventHandler(FileSystemEventHandler):
    def __init__(self, orchestrator: PipelineOrchestrator):
        self.orchestrator = orchestrator
        super().__init__()

    def on_created(self, event):
        if event.is_directory:
            logger.info(f"New email directory detected: {event.src_path}")
            # Slight delay to ensure files are written
            time.sleep(2)
            self._process_directory(event.src_path)
            
    def _process_directory(self, dir_path: str):
        metadata_path = os.path.join(dir_path, "metadata.json")
        if not os.path.exists(metadata_path):
            logger.warning(f"No metadata.json found in {dir_path}. Skipping.")
            return
            
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
                
            customer_id = meta.get("customer_id")
            if not customer_id:
                logger.error(f"No customer_id in metadata for {dir_path}")
                return
                
            self.orchestrator.process_shipment(dir_path, customer_id)
        except Exception as e:
            logger.error(f"Error processing email directory {dir_path}: {e}")

class EmailTrigger:
    def __init__(self, orchestrator: PipelineOrchestrator):
        self.orchestrator = orchestrator
        self.observer = None

    def start(self, watch_dir: str):
        os.makedirs(watch_dir, exist_ok=True)
        event_handler = EmailEventHandler(self.orchestrator)
        self.observer = Observer()
        self.observer.schedule(event_handler, watch_dir, recursive=False)
        self.observer.start()
        logger.info(f"Started watching {watch_dir} for new emails.")

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped watching for emails.")

    def simulate_email(self, email_dir: str):
        logger.info(f"Simulating email arrival at {email_dir}")
        handler = EmailEventHandler(self.orchestrator)
        handler._process_directory(email_dir)
