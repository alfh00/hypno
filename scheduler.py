#!/usr/bin/env python3
"""
Drift Scheduler — runs the pipeline on a cron schedule using APScheduler.
Alternative to system cron — useful if you want in-process scheduling
with retry logic and structured logging.

Usage:
    python scheduler.py
"""

import traceback
import yaml
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from pipeline.logger import get_logger
from run import run_pipeline

load_dotenv()
logger = get_logger("drift.scheduler")


def scheduled_run():
    try:
        with open("./config.yaml") as f:
            config = yaml.safe_load(f)
        run_pipeline(config)
    except Exception:
        logger.error("Scheduled run failed:\n" + traceback.format_exc())


def main():
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        scheduled_run,
        CronTrigger(hour=3, minute=0),
        id="drift_daily",
        name="Drift daily pipeline",
        max_instances=1,
        misfire_grace_time=3600,
    )

    logger.info("Drift scheduler started — running daily at 03:00 UTC")
    logger.info("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
