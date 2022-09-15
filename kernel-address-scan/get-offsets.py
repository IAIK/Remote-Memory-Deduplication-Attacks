#/usr/bin/env python

import pandas as pd
import numpy as np
import click
import tqdm as tqdm

def load_kallsyms(kallsyms_output):
    symbols = {}
    with open(kallsyms_output, "r") as f:
        for line in f.readlines():
            entry = line.split(" ")
            symbols["0x" + entry[0]] = entry[2].strip()

    return symbols

@click.command()
@click.argument('log', type=click.Path(exists=True))
@click.argument('pfn', type=str)
def main(log, pfn):
    df = pd.read_csv(log)

    entries = df[df.PFN == pfn]
    print(entries)

    print(",".join([str(x) for x in list(entries['Offset'])]))

if __name__ == "__main__":
    main()
