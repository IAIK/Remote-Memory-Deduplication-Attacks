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
@click.argument('kallsyms_output', type=click.Path(exists=True), required=False)
@click.option('-o', '--output', type=click.Path())
def main(log, kallsyms_output, output):
    df = pd.read_csv(log)
    # pd.set_option('display.max_rows', None)

    # Overwrite with symbols file
    if kallsyms_output:
        symbols = load_kallsyms(kallsyms_output)
        df['Symbol'] = df['Address'].apply(lambda x: symbols[x] if x in symbols else np.NaN)
    # df.dropna(subset=['Symbol'], inplace=True)

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
    if output:
        df.to_csv(output)
    else:
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
        for candidate in candidates:
            print(candidate.iloc[0]['PFN'])
            print(candidate)

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
