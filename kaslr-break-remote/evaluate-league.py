import os
import binascii
import time
import click
import yaml
import signal
import sys
import random
import asyncio
import queue
import itertools
import dateutil
import re
from datetime import datetime
import pandas as pd
from addict import Dict
from timeit import default_timer as timer

@click.command()
@click.option('-i', '--input', 'input_path', type=click.Path(exists=True))
@click.option('-d', '--delay', 'delay', type=int, default=3)
@click.option('-r', '--real-delay', 'real_delay', type=float, default=34.57)
@click.option('-g', '--ground-truth', 'ground_truth', type=int, default=None)
def cli(input_path, ground_truth, delay, real_delay):
    """Evaluate KASLR break"""

    results = []
    durations = []
    subrounds = []

    # Parse all log files
    for (dirpath, dirnames, filenames) in os.walk(input_path):
        for filename in filenames:
            found = False
            full_path = os.path.join(dirpath, filename)
            subround_count = 0

            with open(full_path) as f:
                content = f.read().splitlines()

                for idx, line in enumerate(content):
                    if 'Subround' in line:
                        subround_count += 1
                    if 'Winning offset' in line:
                        found = True
                        parts = content[idx:idx+5]
                        winner = re.search(r'\d+', parts[1]).group()
                        duration = pd.Timedelta(parts[4])

                        results.append(winner)
                        durations.append(duration)

                subrounds.append(subround_count)

            if found is False:
                print(f"No log file for: {full_path}")

    # Evaluate
    results = pd.Series(results)
    durations = pd.Series(durations)
    subrounds = pd.Series(subrounds)

    if ground_truth is None: # assume max is ground truth
        ground_truth = results.mode()[0]

    success_rate = 0
    summary = results.value_counts()
    top_count = summary[ground_truth]
    success_rate = top_count / len(results) * 100.

    wait_time = pd.Timedelta(value=subrounds.mean() * delay, unit='s')
    measure_time = durations.median() - wait_time
    new_time = pd.Timedelta(value=subrounds.mean() * real_delay, unit='s') + measure_time

    print(f"Samples: {len(results)}")
    print(f"Success Rate: {success_rate:.2f}%")
    print(f"Runtime (mean): {durations.mean()}")
    print(f"Runtime (median): {durations.median()}")
    print(f"Runtime (min): {durations.min()}")
    print(f"Runtime (max): {durations.max()}")
    print(f"Subrounds (mean): {subrounds.mean()}")
    print(f"----")
    print(f"Wait time: {wait_time}")
    print(f"Measure time: {measure_time}")
    print(f"New time: {new_time}")


if __name__ == "__main__":
    cli()
