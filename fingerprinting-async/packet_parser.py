import mmap
from pprint import pprint
import rdtsc
import click
import binascii
import numpy as np
import pandas as pd
import pyshark
import threading
import sys
import signal
import random
import matplotlib
import re
import time
import pprint
import requests
from datetime import datetime

matplotlib.use('Agg')
from addict import Dict



import aiohttp
import asyncio

from IPython import embed

STEP = (2*1024*1024)
SLEEP_TIME = 4000000
SLEEP_TIME = 10000000

ground_truth = []
page_content = None

usleep = lambda x: time.sleep(x/1000000.0)

#pd.set_option('display.max_rows', 50)
#pd.set_option('display.min_rows', None)

measurements = pd.DataFrame()
measurements_offsets = {}
measurements_offsets_h2time = {}
number_of_measurements = 0
capture_thread = None
is_single_mode = False
is_http1 = False

def store_logs():
    measurements.to_csv('log.csv')

def signal_handler(sig, frame):
    store_logs()

    sys.exit(0)

def print_update():
    global number_of_measurements
    global is_single_mode

    try:
        order_by_column = 'Timestamp' #if is_single_mode else 'Count'

        df = measurements
        print(df)
        # Uncomment to directly classify...
        #df = df.mask(df.sub(df.mean()).div(df.std()).abs().gt(2))
        #df = filter_outlier(df, 'Timestamp')

        #df_median = df.groupby('Offset')
        #groups = df_median.groups.keys()
        #df_median = df_median.median()
        
        #df_mean = df.groupby('Offset')
        #groups = df_mean.groups.keys()
        #df_mean = df_mean.mean() #.sort_values('TS First Frame')
        
        #df_median = df_median.sort_values(by=[order_by_column],ascending=False)
        #df_mean = df_mean.sort_values(by=[order_by_column], ascending=False)

        #print("\033c")
        bit_str = ""
        for i in ground_truth:
           if i:
               bit_str+="1"
           else:
               bit_str+="0"
        
        print(bit_str)

        #print(f"Number of measurements: {number_of_measurements}")
        #print("Median")
        #print(df_median.head(n=15))
        #print("Mean")
        #print(df_mean.head(n=15))
    except Exception as e:
        print(e)
        pass

@click.command()
@click.option('-i', '--infile', type=str, default='/tmp/captured.pcap')
@click.option('-h', '--host', type=str, default='0.0.0.0')
@click.option('-p', '--port', type=int, default=6666)
@click.option('-d', '--device', default="enp3s0")
def main(infile,host, port, device):
    global number_of_measurements
    global measurements
    global measurements_offsets
    global measurements_offsets_h2time
    global pages
    global page_offsets
    global kernel_offsets
    global is_http1
    global start_time
    global ground_truth

    signal.signal(signal.SIGINT, signal_handler)
    capture = pyshark.FileCapture(input_file=infile,
                                  display_filter=f'tcp.port == {port} and http',
                                  decode_as={f'tcp.port=={port}': 'http'}, # decode as http2
                                  use_json=True)

    parsing_tracker = {}
    for packet in capture:
            try:
                if 'http' in packet:
                    if packet.http.has_field('full_uri'):
                        all_fields = vars(packet.http)['_all_fields']
                        request_uri = list(all_fields.keys())[0] # mega ugly
                        
                        if 'update' in str(request_uri):
                            ack_raw = packet.tcp.ack_raw
                            current_offset = int(re.search(r'\d+', request_uri).group())
                            #begin = self.__to_timestamp(packet.sniff_timestamp)
                            split = packet.sniff_timestamp.split(".")
                            upper = int(split[0])*1e9
                            lower = int(split[1])
                            begin = upper + lower
                            parsing_tracker[ack_raw] = (int(current_offset), begin)

                            #print(f"Update: {current_offset},{ack_raw}")
                            continue

                flags = packet.tcp.get_field("flags_tree")
                #if int(flags.get_field('push')) == 1 and int(flags.get_field('ack')) == 1:
                if int(flags.get_field('push')) == 1 and int(flags.get_field('ack')) == 1:
                    #print(packet.tcp)
                    if packet.tcp.seq_raw in parsing_tracker:
                        offset, begin = parsing_tracker[packet.tcp.seq_raw]
                        #end = self.__to_timestamp(packet.sniff_timestamp)
                        #diff = self.__diff_to_ns(end - begin)
                        split = packet.sniff_timestamp.split(".")
                        upper = int(split[0])*1e9
                        lower = int(split[1])
                        end = upper + lower
                        diff = end - begin

                        #print(f"Ack:{packet.tcp.seq_raw}, Offset: {offset}")
                        m = {
                            'Offset': offset,
                            'Timestamp': diff
                            }

                        measurements = measurements.append(m, ignore_index=True)

                        del parsing_tracker[packet.tcp.seq_raw]
                continue
            except Exception as e:
                print(e)
                continue

    store_logs()
    print("Done.")

if __name__ == "__main__":
    main()