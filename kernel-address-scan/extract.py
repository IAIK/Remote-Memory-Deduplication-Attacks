#/usr/bin/env python

import pandas as pd
import numpy as np
import click
import yaml
import tempfile
import subprocess
import binascii
import os
import tqdm as tqdm

def dump_page(address):
    output = None

    with tempfile.NamedTemporaryFile() as f:
        filepath = f.name
        process = subprocess.Popen(
                ['./dump-page', address, '-o', filepath],
                stdout=subprocess.STDOUT,
                stderr=subprocess.STDERR)
        stdout, stderr = process.communicate()
        print(stdout)

        #output = binascii.hexlify(content)

    return content

def extract_page(candidate):
    pfn = candidate.iloc[0]['PFN']
    offsets = [x for x in candidate['Offset']]
    data = dump_page(pfn)

    page = {
       'pfn': pfn,
       'offsets': offsets,
       'data': data
    }

    return page


@click.command()
@click.argument('logfile', type=click.Path(exists=True), required=False)
@click.option('-o', '--output-dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
def main(logfile, output_dir):
    df = pd.read_csv(logfile)
    # pd.set_option('display.max_rows', None)

    pfns = df.PFN.unique()
    print("%d pages" % len(pfns))

    # Statistics
    with_module = 0
    with_direct = 0
    with_no_symbols = 0
    with_partial_symbols = 0
    candidates = []
    candidates_with_no_symbols = []
    candidates_with_partial_symbols = []

    # save pfn
    for pfn, entries in tqdm.tqdm(df.groupby('PFN')):
        number_of_kernel = entries[entries.Type == 0].shape[0]
        number_of_module = entries[entries.Type == 1].shape[0]
        number_of_direct = entries[entries.Type == 2].shape[0]

        if number_of_module > 0:
            with_module += 1
            continue

        if number_of_direct > 0:
            with_direct += 1
            continue

        filtered = entries.dropna(subset=['Symbol'])
        if len(filtered) == 0: # haven't found a symbol, need to check manually?
            with_no_symbols += 1
            candidates_with_no_symbols += [entries]
            continue

        number_of_not_resolved = entries[entries.Symbol.isna()]
        if len(number_of_not_resolved) != 0:
            with_partial_symbols += 1
            candidates_with_partial_symbols += [entries]
            continue

        candidates += [entries]

    print("Total: %d" % len(candidates))
    print("Module pages: %d" % with_module)
    print("Direct pages: %d" % with_direct)
    print("No symbols: %d" % with_no_symbols)
    print("Partial symbols: %d" % with_partial_symbols)

    print("Candidates:")
    for candidate in tqdm.tqdm(candidates):
        pfn = candidate.iloc[0]['PFN']
        page = extract_page(candidate)

        filename = os.path.join(output_dir, pfn + ".yaml")
        with open(filename, "w") as f:
            yaml.dump(page, f)
    return

    print("Candidates with no symbols:")
    for candidate in candidates_with_no_symbols:
        addresses = candidate.Address.unique()
        print(candidate.iloc[0]['PFN'])
        # print(addresses)
        print(candidate)

    print("Candidates with partial symbols:")
    for candidate in candidates_with_partial_symbols:
        addresses = candidate.Address.unique()
        print(candidate.iloc[0]['PFN'])
        # print(addresses)
        # print(candidate)

if __name__ == "__main__":
    main()
