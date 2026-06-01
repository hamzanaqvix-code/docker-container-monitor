#!/usr/bin/env python3
"""
Docker Container Resource Monitor
Monitors CPU and memory usage across all running containers,
alerts on threshold breaches, and logs historical usage to CSV.
"""

import docker
import csv
import os
import time
import argparse
from datetime import datetime


# -----------------------------------------------------------------------------
# DEFAULT THRESHOLDS
# -----------------------------------------------------------------------------
DEFAULT_CPU_THRESHOLD    = 80.0   # Alert if CPU exceeds this percentage
DEFAULT_MEMORY_THRESHOLD = 80.0   # Alert if memory exceeds this percentage
DEFAULT_INTERVAL         = 10     # Seconds between each poll
DEFAULT_LOG_FILE         = "logs/container_stats.csv"


# -----------------------------------------------------------------------------
# COLORS FOR TERMINAL OUTPUT
# -----------------------------------------------------------------------------
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def calculate_cpu_percent(stats: dict) -> float:
    """
    Calculate CPU usage percentage from raw Docker stats.
    Docker returns raw CPU ticks — we calculate the delta
    between current and previous reading to get percentage.
    """
    try:
        cpu_delta    = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                       stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                       stats["precpu_stats"]["system_cpu_usage"]
        num_cpus     = stats["cpu_stats"].get("online_cpus") or \
                       len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))

        if system_delta > 0 and cpu_delta > 0:
            return (cpu_delta / system_delta) * num_cpus * 100.0
        return 0.0
    except (KeyError, ZeroDivisionError):
        return 0.0


def calculate_memory_percent(stats: dict) -> tuple:
    """
    Calculate memory usage percentage and return usage/limit in MB.
    """
    try:
        usage = stats["memory_stats"]["usage"]
        limit = stats["memory_stats"]["limit"]

        # Subtract cache from usage for accurate reading
        cache = stats["memory_stats"].get("stats", {}).get("cache", 0)
        actual_usage = usage - cache

        percent      = (actual_usage / limit) * 100.0
        usage_mb     = actual_usage / (1024 * 1024)
        limit_mb     = limit / (1024 * 1024)

        return percent, usage_mb, limit_mb
    except (KeyError, ZeroDivisionError):
        return 0.0, 0.0, 0.0


def get_container_stats(container) -> dict:
    """
    Fetch and calculate stats for a single container.
    stream=False fetches a single snapshot.
    """
    try:
        raw_stats    = container.stats(stream=False)
        cpu_percent  = calculate_cpu_percent(raw_stats)
        mem_percent, mem_usage_mb, mem_limit_mb = calculate_memory_percent(raw_stats)

        return {
            "timestamp"    : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "container_id" : container.short_id,
            "name"         : container.name,
            "status"       : container.status,
            "cpu_percent"  : round(cpu_percent, 2),
            "mem_percent"  : round(mem_percent, 2),
            "mem_usage_mb" : round(mem_usage_mb, 2),
            "mem_limit_mb" : round(mem_limit_mb, 2),
        }
    except Exception as e:
        return {
            "timestamp"    : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "container_id" : container.short_id,
            "name"         : container.name,
            "status"       : "error",
            "cpu_percent"  : 0.0,
            "mem_percent"  : 0.0,
            "mem_usage_mb" : 0.0,
            "mem_limit_mb" : 0.0,
            "error"        : str(e),
        }


def log_to_csv(stats_list: list, log_file: str):
    """
    Append container stats to CSV file.
    Creates the file with headers if it does not exist.
    """
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_exists = os.path.isfile(log_file)

    with open(log_file, "a", newline="") as f:
        fieldnames = [
            "timestamp", "container_id", "name", "status",
            "cpu_percent", "mem_percent", "mem_usage_mb", "mem_limit_mb"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")

        if not file_exists:
            writer.writeheader()

        for stats in stats_list:
            writer.writerow(stats)


def print_stats_table(stats_list: list, cpu_threshold: float, mem_threshold: float):
    """
    Print a formatted table of container stats to the terminal.
    Highlights containers exceeding thresholds in red.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{BOLD}{CYAN}Docker Container Monitor{RESET} — {timestamp}")
    print(f"{'─' * 85}")
    print(f"{BOLD}{'CONTAINER':<25} {'STATUS':<12} {'CPU %':>8} {'MEM %':>8} {'MEM USAGE':>12} {'MEM LIMIT':>12}{RESET}")
    print(f"{'─' * 85}")

    alerts = []

    for s in stats_list:
        cpu_color = RED    if s["cpu_percent"] >= cpu_threshold    else GREEN
        mem_color = RED    if s["mem_percent"] >= mem_threshold    else GREEN

        # Truncate long container names
        name = s["name"][:24] if len(s["name"]) > 24 else s["name"]

        print(
            f"{name:<25} "
            f"{s['status']:<12} "
            f"{cpu_color}{s['cpu_percent']:>7.1f}%{RESET} "
            f"{mem_color}{s['mem_percent']:>7.1f}%{RESET} "
            f"{s['mem_usage_mb']:>10.1f}MB "
            f"{s['mem_limit_mb']:>10.1f}MB"
        )

        if s["cpu_percent"] >= cpu_threshold:
            alerts.append(
                f"{RED}ALERT{RESET} {s['name']} CPU at {s['cpu_percent']:.1f}% "
                f"(threshold: {cpu_threshold}%)"
            )
        if s["mem_percent"] >= mem_threshold:
            alerts.append(
                f"{RED}ALERT{RESET} {s['name']} Memory at {s['mem_percent']:.1f}% "
                f"(threshold: {mem_threshold}%)"
            )

    print(f"{'─' * 85}")
    print(f"  {len(stats_list)} container(s) running")

    if alerts:
        print(f"\n{BOLD}THRESHOLD ALERTS:{RESET}")
        for alert in alerts:
            print(f"  {alert}")


def run_monitor(
    cpu_threshold: float,
    mem_threshold: float,
    interval:      int,
    log_file:      str,
    once:          bool
):
    """
    Main monitoring loop.
    Polls all running containers, prints stats, logs to CSV.
    """
    try:
        client = docker.from_env()
    except docker.errors.DockerException as e:
        print(f"{RED}Error connecting to Docker:{RESET} {e}")
        print("Make sure Docker Desktop is running.")
        return

    print(f"{BOLD}Docker Container Resource Monitor{RESET}")
    print(f"CPU threshold  : {cpu_threshold}%")
    print(f"Memory threshold: {mem_threshold}%")
    print(f"Poll interval  : {interval}s")
    print(f"Log file       : {log_file}")
    print(f"Press Ctrl+C to stop.\n")

    try:
        while True:
            containers = client.containers.list()

            if not containers:
                print(f"{YELLOW}No running containers found.{RESET}")
                print("Start your Docker LEMP stack with: docker compose up -d")
            else:
                stats_list = []
                for container in containers:
                    stats = get_container_stats(container)
                    stats_list.append(stats)

                print_stats_table(stats_list, cpu_threshold, mem_threshold)
                log_to_csv(stats_list, log_file)

            if once:
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n{CYAN}Monitor stopped.{RESET}")
        print(f"Historical data saved to: {log_file}")


def generate_report(log_file: str):
    """
    Read the CSV log file and generate a summary report.
    Shows per-container averages, peaks, and threshold breach count.
    """
    if not os.path.isfile(log_file):
        print(f"{RED}Log file not found:{RESET} {log_file}")
        print("Run the monitor first to collect data.")
        return

    data = {}

    with open(log_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["name"]
            if name not in data:
                data[name] = {
                    "cpu_readings" : [],
                    "mem_readings" : [],
                    "samples"      : 0,
                }
            try:
                data[name]["cpu_readings"].append(float(row["cpu_percent"]))
                data[name]["mem_readings"].append(float(row["mem_percent"]))
                data[name]["samples"] += 1
            except ValueError:
                continue

    if not data:
        print(f"{YELLOW}No data found in log file.{RESET}")
        return

    print(f"\n{BOLD}{CYAN}Container Resource Report{RESET}")
    print(f"Log file: {log_file}")
    print(f"{'─' * 80}")
    print(f"{BOLD}{'CONTAINER':<25} {'SAMPLES':>8} {'AVG CPU':>9} {'PEAK CPU':>9} {'AVG MEM':>9} {'PEAK MEM':>9}{RESET}")
    print(f"{'─' * 80}")

    for name, d in sorted(data.items()):
        avg_cpu  = sum(d["cpu_readings"]) / len(d["cpu_readings"])
        peak_cpu = max(d["cpu_readings"])
        avg_mem  = sum(d["mem_readings"]) / len(d["mem_readings"])
        peak_mem = max(d["mem_readings"])

        print(
            f"{name:<25} "
            f"{d['samples']:>8} "
            f"{avg_cpu:>8.1f}% "
            f"{peak_cpu:>8.1f}% "
            f"{avg_mem:>8.1f}% "
            f"{peak_mem:>8.1f}%"
        )

    print(f"{'─' * 80}")


def main():
    parser = argparse.ArgumentParser(
        description="Docker Container Resource Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 monitor.py                          # Monitor with defaults
  python3 monitor.py --interval 5             # Poll every 5 seconds
  python3 monitor.py --cpu 70 --mem 75        # Custom thresholds
  python3 monitor.py --once                   # Single snapshot
  python3 monitor.py --report                 # Generate summary report
        """
    )

    parser.add_argument(
        "--cpu",
        type=float,
        default=DEFAULT_CPU_THRESHOLD,
        help=f"CPU alert threshold percentage (default: {DEFAULT_CPU_THRESHOLD})"
    )
    parser.add_argument(
        "--mem",
        type=float,
        default=DEFAULT_MEMORY_THRESHOLD,
        help=f"Memory alert threshold percentage (default: {DEFAULT_MEMORY_THRESHOLD})"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Seconds between polls (default: {DEFAULT_INTERVAL})"
    )
    parser.add_argument(
        "--log",
        type=str,
        default=DEFAULT_LOG_FILE,
        help=f"CSV log file path (default: {DEFAULT_LOG_FILE})"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single snapshot and exit"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate summary report from existing log file"
    )

    args = parser.parse_args()

    if args.report:
        generate_report(args.log)
    else:
        run_monitor(
            cpu_threshold=args.cpu,
            mem_threshold=args.mem,
            interval=args.interval,
            log_file=args.log,
            once=args.once,
        )


if __name__ == "__main__":
    main()
