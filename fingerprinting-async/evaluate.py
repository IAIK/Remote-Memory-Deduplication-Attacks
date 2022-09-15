#!/usr/bin/python3

import numpy as np
import matplotlib.pyplot as plt
import sys
import os
import pandas as pd
import click

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
def main(path):
# len(sys.argv)ed_csv(path, index_col=0)
    df = pd.read_csv(path, index_col=0)
    df.Offset = df.Offset.astype(int)

    # Filter outliers
    #df = df.mask(df.sub(df.mean()).div(df.std()).abs().gt(3))
    filter_val = 'Prev TS Frame'
    df = filter_outlier(df, filter_val)
    
    x = df.groupby('Offset').mean()
    x = x.sort_values(filter_val,ascending=False)
    print(x)
    mean = df.groupby('Offset').mean().sort_values(by='Prev TS Frame',ascending=False).index[0]
    median = df.groupby('Offset').median().sort_values(by='Prev TS Frame',ascending=False).index[0]

    print(f"{mean};{median}")
    print(df.groupby('Offset').mean().sort_values(by='Prev TS Frame',ascending=False).iloc[0])

if __name__ == "__main__":
    main()

#  print("provide an argument")
#  os._exit(-1)
#
#x = np.loadtxt(sys.argv[1],delimiter=",",skiprows=1)
#
#zero = x[x[:,1] == 0][:,1]
#one  = x[x[:,1] == 1][:,1]
#two  = x[x[:,1] == 2][:,1]
#three = x[x[:,1] == 3][:,1]
#
#stacked = np.column_stack((zero,one,two,three))
#
#dict_values = {}
#
#for i in range(len(zero)):
#    arg = np.argmax(stacked[i,:],axis=0)
#    if arg in dict_values:
#        dict_values[arg] = dict_values[arg] + 1
#    else:
#        dict_values[arg] = 1
#
#print(dict_values)

# plt.plot(zero,label="0")
# plt.plot(one,label="1")
# plt.plot(two,label="2")
# plt.plot(three,label="3")
# plt.legend()
# #plt.scatter(x[:,0],x[:,1])
# plt.show()

