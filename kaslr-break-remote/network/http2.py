import asyncio
import threading
import pyshark
import re
import os
import signal
import pandas as pd
import numpy as np
from queue import Queue
from pprint import pprint


class CapturePySharkThreadHttp2(threading.Thread):
    def __init__(self, group=None, target=None, name=None, interface="enp7s0", tcp_port=6666, args=(), kwargs={}, backend=None):
        threading.Thread.__init__(self, group, target, name, args=args, kwargs=kwargs)
        self._capture = pyshark.LiveCapture(interface=interface,
                                            bpf_filter=f'tcp port {tcp_port}',
                                            decode_as={f'tcp.port=={tcp_port}': 'http2'}, # decode as http2
                                            use_json=True)
        self._return = None
        self._stopping = False
        self.measurements = []

    def __to_timestamp(self, timestamp):
        if 'CEST' in timestamp:
            dt = pd.to_datetime(timestamp.replace(' CEST', ''), format="%b %d, %Y %H:%M:%S.%f")
        else:
            dt = pd.to_datetime(timestamp, format="%b %d, %Y %H:%M:%S.%f %Z")
        return dt

    def __diff_to_ns(self, diff):
        return (diff.total_seconds() + diff.nanoseconds * 1e-9) * 1000000000

    def run(self):
        self._stopping = False

        parsing_tracker = {}
        first_end = None

        for packet in self._capture.sniff_continuously():
            if self._stopping is True:
                break

            try:
                if 'http2' in packet:
                    if not packet.http2.has_field('stream'):
                        continue

                    streams = []
                    if isinstance(packet.http2.stream, list):
                        streams = packet.http2.stream
                    else:
                        streams = [packet.http2.stream]

                    for stream in streams:
                        if not stream.has_field('type'):
                            continue

                        stream_type = int(stream.type)

                        if stream_type == 1:
                            stream_id = int(stream.streamid)
                            for header in stream.header:
                                if header.has_field('path'):
                                    if 'set-byte' in str(header.path):
                                        # add new request to tracker
                                        current_offset = int(re.search(r'\d+', header.path).group())
                                        begin = self.__to_timestamp(packet.sniff_timestamp)
                                        parsing_tracker[stream_id] = (int(current_offset), begin)
                                else:
                                    if str(header.name) == ":status" and int(header.value) == 200:
                                        # check if we have already seen it
                                        if stream_id not in parsing_tracker:
                                            continue

                                        offset, begin = parsing_tracker[stream_id]
                                        end = self.__to_timestamp(packet.sniff_timestamp)

                                        time_since_first_frame = np.NaN
                                        try:
                                            time_since_first_frame = int(float(packet.tcp.get_field('Timestamps').get_field('time_relative')) * 1e9)
                                        except Exception:
                                            pass

                                        time_since_previous_frame = np.NaN
                                        try:
                                            time_since_previous_frame = int(float(packet.tcp.get_field('Timestamps').get_field('time_delta')) * 1e9)
                                        except Exception:
                                            pass

                                        del parsing_tracker[stream_id]

                                        diff = self.__diff_to_ns(end - begin)

                                        m = {
                                            'Offset': offset,
                                            'Timestamp': diff,
                                            'TS First Frame': time_since_first_frame,
                                            'TS Prev Frame': time_since_previous_frame,
                                            }

                                        self.measurements.append(m)

                                        if len(parsing_tracker) == 0: # last one
                                            if offset in measurements_offsets:
                                                measurements_offsets[offset] += 1
                                            else:
                                                measurements_offsets[offset] = 1
                        elif stream_type == 0:
                            continue
                            stream_id = int(stream.streamid)
                        elif stream_type == 7:
                            continue

                    continue
            except Exception as e:
                print(e)
                continue

    def stop(self):
        self._stopping = True

    def kill(self):
        # Kill everything
        for process in self._capture._running_processes:
            process.kill()
