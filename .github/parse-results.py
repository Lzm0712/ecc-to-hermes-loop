#!/usr/bin/env python3
"""Parse loop results from output log. Called by GitHub Actions."""
import argparse, re

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log-file", required=True)
    p.add_argument("--status-file", required=True)
    p.add_argument("--iterations-file", required=True)
    args = p.parse_args()

    with open(args.log_file) as f:
        log = f.read()

    iter_count = log.count("--- Iteration")
    iter_count = max(1, iter_count)

    if "All gates passed" in log:
        status = "SUCCESS"
    elif "exhausted" in log:
        status = "ITERATION_EXHAUSTED"
    elif "FAILED" in log:
        status = "GATE_FAILED"
    else:
        status = "UNKNOWN"

    with open(args.status_file, "w") as f:
        f.write(status)
    with open(args.iterations_file, "w") as f:
        f.write(str(iter_count))

    print(f"status={status}, iterations={iter_count}", file=__import__("sys").stderr)

if __name__ == "__main__":
    main()
