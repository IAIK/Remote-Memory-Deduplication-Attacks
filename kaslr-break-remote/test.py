#!/usr/bin/env python

import pandas as pd
import os
import click
import numpy as np
import math
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path


df = pd.read_csv("~/Downloads/1.csv", index_col=0)
#df = df.mask(df.sub(df.mean()).div(df.std()).abs().gt(3))
df.fillna(0)

means_ts = []
medians_ts = []
max_ts = []

server_time = []
server_time_med = []

for i in range(0,512):
  deep = df.copy()
  mask = deep["Offset"] ==  i
  data = deep[mask]
  filtered = deep.query(f"Offset=={i}").fillna(0)
  ts = filtered["Timestamp"].to_numpy()
  server = filtered["Server"].to_numpy()
  server_only = server[server > 0]
  timestamps_only = ts[ts > 0]

  perc = np.percentile(timestamps_only,75)
  #print(f"{i},{np.median(server_only)},{np.max(timestamps_only)}")

  timestamps_only = timestamps_only[timestamps_only <= perc]

  means_ts.append(np.mean(timestamps_only))
  medians_ts.append(np.median(timestamps_only))
  max_ts.append(np.median(timestamps_only))
  server_time.append(np.mean(server_only))
  server_time.append(np.mean(server_only))
  server_time_med.append(np.median(server_only))

print(np.argmax(server_time_med))
print(np.argmax(timestamps_only))
print(np.argmax(medians_ts))
print(np.argmax(max_ts))

# idx_arr = [x for x in range(0,512)]
# plt.plot(idx_arr,medians_ts)
# plt.show()


# Filter outliers
#df = df.mask(df.sub(df.mean()).div(df.std()).abs().gt(1))

# Plot
