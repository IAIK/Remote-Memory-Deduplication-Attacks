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
                           inclusive='both')

    return df.loc[m]

@click.command()
@click.argument('path1', type=click.Path(exists=True))
@click.option('--output', type=click.Path(), required=False)
def main(path1, output):
    # Load files
    df = pd.read_csv(path1, index_col='Index')

    df = filter_outlier(df, 'TS Prev Frame')
    df_mean = df.groupby('Offset').mean().sort_values(by=['TS Prev Frame'], ascending=False)
    click.echo(df_mean.head(n=20))

    if output:
        df_mean['Value'] = df_mean['TS Prev Frame']
        df_mean = df_mean.drop(columns=['TS Prev Frame', 'TS First Frame', 'Timestamp'])
        df_mean = df_mean.sort_index()

        df_mean.to_csv(output)
    else:
        sns.lineplot(data=df_mean, x='Offset', y='TS Prev Frame', color='r')
        plt.show()

if __name__ == "__main__":
    main()
