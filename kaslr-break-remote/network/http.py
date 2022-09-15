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


class CapturePySharkThreadHttp(threading.Thread):
    def __init__(self, group=None, target=None, name=None, interface="enp7s0", tcp_port=6666, args=(), kwargs={}, backend=None):
        threading.Thread.__init__(self, group, target, name, args=args, kwargs=kwargs)
        self.backend = backend
        use_json = True
        if self.backend == 'requests':
            use_json = False

        self._capture = pyshark.LiveCapture(interface=interface,
                                            bpf_filter=f'tcp port {tcp_port}',
                                            decode_as={f'tcp.port=={tcp_port}': 'http'},
                                            use_json=use_json)
        self._return = None
        self._stopping = False
        self.measurements = Queue()

    def __to_timestamp(self, timestamp):
        if 'CEST' in timestamp:
            dt = pd.to_datetime(timestamp.replace(' CEST', ''), format="%b %d, %Y %H:%M:%S.%f")
        else:
            dt = pd.to_datetime(timestamp, format="%b %d, %Y %H:%M:%S.%f %Z")
        return dt

    def __diff_to_ns(self, diff):
        return (diff.total_seconds() + diff.nanoseconds * 1e-9) * 1000000000

    def run(self):
        if self.backend == 'requests':
            return self.run_backend_python_requests()
        else:
            return self.run_default()

    def run_default(self):
        self._stopping = False

        parsing_tracker = {}
        first_end = None

        for packet in self._capture.sniff_continuously():
            if self._stopping is True:
                break

            try:
                if 'http' in packet:
                    if packet.http.has_field('full_uri'):
                        all_fields = vars(packet.http)['_all_fields']
                        request_uri = list(all_fields.keys())[0] # mega ugly

                        if '/set-byte' in str(request_uri):
                            # print(str(request_uri))
                            ack_raw = packet.tcp.ack_raw

                            current_offset = int(re.search(r'\d+', request_uri).group())
                            try:
                                begin = float(packet.sniff_timestamp)
                                split = packet.sniff_timestamp.split(".")
                                upper = int(split[0])*1e9
                                lower = int(split[1])
                                begin = upper + lower
                            except Exception:
                                begin = self.__to_timestamp(packet.sniff_timestamp)

                            parsing_tracker[ack_raw] = (int(current_offset), begin)

                            continue

                flags = packet.tcp.get_field("flags_tree")
                if int(flags.get_field('push')) == 1 and int(flags.get_field('ack')) == 1:
                    if packet.tcp.seq_raw in parsing_tracker:
                        offset, begin = parsing_tracker[packet.tcp.seq_raw]
                        try:
                            end = float(packet.sniff_timestamp)
                            split = packet.sniff_timestamp.split(".")
                            upper = int(split[0])*1e9
                            lower = int(split[1])
                            end = upper + lower
                            diff = end - begin
                        except Exception:
                            end = self.__to_timestamp(packet.sniff_timestamp)
                            diff = self.__diff_to_ns(end - begin)

                        all_fields = vars(packet.tcp)['_all_fields']
                        if 'tcp.time_relative' in all_fields['Timestamps']:
                            time_since_first_frame = int(float(all_fields['Timestamps']['tcp.time_relative']) * 1000000000)
                        else:
                            time_since_first_frame = np.NaN

                        if 'tcp.time_delta' in all_fields['Timestamps']:
                            time_since_previous_frame = int(float(all_fields['Timestamps']['tcp.time_delta']) * 1000000000)
                        else:
                            time_since_previous_frame = np.NaN

                        m = {
                            'Offset': offset,
                            'Timestamp': diff,
                            'TS First Frame': time_since_first_frame,
                            'TS Prev Frame': time_since_previous_frame,
                            }

                        self.measurements.put(m)

                        del parsing_tracker[packet.tcp.seq_raw]
                continue
            except Exception as e:
                print(e)
                continue

    def run_backend_python_requests(self):
        self._stopping = False

        parsing_tracker = {}
        first_end = None

        for packet in self._capture.sniff_continuously():
            if self._stopping is True:
                break

            try:
                if 'http' in packet and packet.http.chat:
                    if 'POST /set-byte' in packet.http.chat:
                        parsed_begin = True
                        nextseq = packet.tcp.nxtseq

                        current_offset = int(re.search(r'\d+', packet.http.chat).group())
                        begin = packet.sniff_timestamp
                        begin = float(begin)

                        parsing_tracker[nextseq] = {
                                'offset': current_offset,
                                'begin': begin
                                }
                        continue
                    elif 'POST /random' in packet.http.chat:
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

                        m = {
                            'Offset': parsing_tracker[packet.tcp.ack]['offset'],
                            'Timestamp': diff,
                            'TS First Frame': time_since_first_frame,
                            'TS Prev Frame': time_since_previous_frame,
                            }

                        self.measurements.put(m)

                        del parsing_tracker[packet.tcp.ack]

                        # print update
                        #print_update()

                        continue

            except Exception as e:
                print(e)
                continue

    def stop(self):
        self._stopping = True

    def kill(self):
        # Kill everything
        processes = [x.pid for x in self._capture._running_processes]
        for pid in processes:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception as e:
                pass
