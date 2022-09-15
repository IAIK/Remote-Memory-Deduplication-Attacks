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
    # df_mean = df.groupby('Offset').mean().sort_values(by=['TS Prev Frame'], ascending=False)
    # click.echo(df_mean.head(n=20))

    df_correct = df[df['Offset'] == 14]
    df_incorrect = df[df['Offset'] == 13]


    # d1 = df_correct['TS Prev Frame'].reset_index()['TS Prev Frame']
    # d2 = df_incorrect['TS Prev Frame'].reset_index()['TS Prev Frame']
    #
    # print(d1.max())
    # print(d2.max())
    #
    # df = pd.DataFrame({
    #     'Correct': d1,
    #     'Incorrect': d2
    # }, index=[x for x in range(len(d2))])
    #
    # df.to_csv(output)
    ax = sns.kdeplot(data=df_correct, x='TS Prev Frame', color='b')
    ax2 = sns.kdeplot(ax=ax, data=df_incorrect, x='TS Prev Frame', color='r')

    if output:
        x, y = ax2.lines[0].get_data()
        datac_x = x[x>0]
        datac_y = y[x>0]

        x, y = ax2.lines[1].get_data()
        dataic_x = x[x>0]
        dataic_y = y[x>0]

        df = pd.DataFrame.from_dict({
            'CorrectX': datac_x,
            'CorrectY': datac_y,
            'IncorrectX': dataic_x,
            'IncorrectY': dataic_y,
        }, orient='index').transpose()

        df.to_csv(output)
    else:
        plt.show()

if __name__ == "__main__":
    main()
