#!/usr/bin/env python

import pandas as pd
import os
import click
import numpy as np
import math
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path

def filter_outlier(df, column):
    groups = df.groupby('Offset')[column]
    groups_mean = groups.transform('mean')
    groups_std = groups.transform('std')
    m = df[column].between(groups_mean.sub(groups_std.mul(2)),
                          groups_mean.add(groups_std.mul(2)),
                          inclusive=False)

    return df.loc[m]

@click.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--output', type=click.Path(), required=False)
def main(path, output):
    # Load files
    df = pd.read_csv(path, index_col=0)
    df.Offset = df.Offset.astype(int)

    # Filter outliers
    #df = df.mask(df.sub(df.mean()).div(df.std()).abs().gt(2))
    df = filter_outlier(df, 'Timestamp')

    # Plot
    fig, ax = plt.subplots(3, 1)

    x = df.groupby('Offset').median()
    x = x.sort_values('Timestamp',ascending=False) # long
    x.to_csv('out_median.csv')
    print(x)

    x = df.groupby('Offset').mean()
    x = x.sort_values('Timestamp',ascending=False) # long
    x.to_csv('out_mean.csv')


    return
if __name__ == "__main__":
    main()
