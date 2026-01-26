#!/usr/bin/env python3
"""
Daily Export Scheduler

Runs the daily export at a configured time (default: 1:00 AM).
Also supports running export immediately via RUN_NOW=true environment variable.
"""

import os
import time
import logging
import schedule
from datetime import datetime

from daily_export import NutanixExporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
EXPORT_TIME = os.getenv('EXPORT_TIME', '01:00')  # 24-hour format
RUN_NOW = os.getenv('RUN_NOW', 'false').lower() == 'true'


def run_export():
    """Execute the daily export."""
    logger.info("Starting scheduled daily export...")
    try:
        exporter = NutanixExporter()
        output_file = exporter.export_to_csv()
        if output_file:
            logger.info(f"Daily export completed: {output_file}")
        else:
            logger.error("Daily export failed - no output file generated")
    except Exception as e:
        logger.error(f"Daily export failed with error: {e}")


def main():
    """Main scheduler entry point."""
    logger.info(f"Daily Export Scheduler started")
    logger.info(f"Scheduled export time: {EXPORT_TIME}")

    # Run immediately if requested
    if RUN_NOW:
        logger.info("RUN_NOW=true, executing export immediately...")
        run_export()

    # Schedule daily export
    schedule.every().day.at(EXPORT_TIME).do(run_export)
    logger.info(f"Next scheduled run: {schedule.next_run()}")

    # Keep running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


if __name__ == '__main__':
    main()
