# Docker Container Resource Monitor

A Python tool that monitors CPU and memory usage across all running Docker containers via the Docker API. Displays a live formatted table, alerts on threshold breaches, and logs historical usage to CSV for trend analysis.

## Features

- Real-time CPU and memory monitoring across all running containers
- Configurable alert thresholds — highlights containers exceeding limits in red
- Historical logging to CSV for trend analysis
- Summary report showing per-container averages and peak usage
- Single snapshot mode or continuous polling mode
- Connects directly to the Docker Engine API — no shell command parsing

## Requirements

- Python 3.6+
- Docker Desktop running
- One dependency: `docker` Python SDK

## Installation

    git clone https://github.com/hamzanaqvix-code/docker-container-monitor.git
    cd docker-container-monitor
    pip3 install -r requirements.txt

## Usage

    # Single snapshot
    python3 monitor.py --once

    # Continuous monitoring with default settings (80% thresholds, 10s interval)
    python3 monitor.py

    # Custom thresholds and interval
    python3 monitor.py --cpu 70 --mem 75 --interval 30

    # Generate summary report from collected data
    python3 monitor.py --report

    # Custom log file location
    python3 monitor.py --log /tmp/my_stats.csv

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| --cpu | 80.0 | CPU alert threshold percentage |
| --mem | 80.0 | Memory alert threshold percentage |
| --interval | 10 | Seconds between polls |
| --log | logs/container_stats.csv | CSV log file path |
| --once | False | Single snapshot and exit |
| --report | False | Generate summary report from log file |

## Example output

    Docker Container Monitor — 2026-06-01 07:09:28
    ─────────────────────────────────────────────────────────────────────────────────────
    CONTAINER                  STATUS        CPU %    MEM %    MEM USAGE    MEM LIMIT
    ─────────────────────────────────────────────────────────────────────────────────────
    lemp_nginx                 running         0.0%     0.2%      16.4MB    7936.2MB
    lemp_php                   running         0.0%     0.6%      49.5MB    7936.2MB
    lemp_redis                 running         0.6%     0.2%      18.0MB    7936.2MB
    lemp_mariadb               running         0.0%     1.8%     144.7MB    7936.2MB
    ─────────────────────────────────────────────────────────────────────────────────────
      4 container(s) running

## Example report

    Container Resource Report
    ────────────────────────────────────────────────────────────────────────────────
    CONTAINER                  SAMPLES   AVG CPU   PEAK CPU   AVG MEM   PEAK MEM
    ────────────────────────────────────────────────────────────────────────────────
    lemp_mariadb               6           0.0%      0.1%      1.8%      1.8%
    lemp_nginx                 6           0.0%      0.0%      0.2%      0.2%
    lemp_php                   6           0.0%      0.0%      0.6%      0.6%
    lemp_redis                 6           0.9%      1.0%      0.2%      0.2%
    ────────────────────────────────────────────────────────────────────────────────

## How it works

The monitor connects to the Docker Engine via the Unix socket using the official Docker Python SDK. For each running container it fetches a stats snapshot and calculates CPU percentage from the delta between current and previous CPU tick counts — the same method Docker uses internally for `docker stats`. Memory usage subtracts the page cache from raw usage to give accurate application memory consumption.

Stats are appended to a CSV file on every poll. The report command reads the CSV and aggregates per-container averages and peak values.

## Notes

- CPU calculation requires two measurements (current and previous ticks) so the first poll takes slightly longer than subsequent ones
- Memory limit reflects the Docker host total RAM when no container memory limit is set
- Log files are gitignored — CSV data stays local

## Verified on

- Python 3.9.6 on darwin/arm64 (Apple M2 Pro)
- Docker 29.5.2, Docker Compose v5.1.3
- Tested against docker-lemp-stack (4 containers)

## Related projects

- docker-lemp-stack: https://github.com/hamzanaqvix-code/docker-lemp-stack
