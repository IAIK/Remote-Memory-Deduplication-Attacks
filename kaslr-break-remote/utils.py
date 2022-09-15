import os
import click
import binascii
import yaml
import mmap


STEP = (2*1024*1024)


def address_to_int_str(value):
    return int(value[2:], 16)

def address_to_int(ctx, param, value):
    return address_to_int_str(value)

def load_page_from_config(page_file, kernel_text_mapping):
    click.echo(f'Loading page file {page_file}')

    with open(page_file, 'r') as f:
        page_meta = yaml.safe_load(f)
        page_content = page_meta['data']
        page_offsets = page_meta['offsets']

        page = mmap.mmap(-1, 4096, flags=mmap.MAP_PRIVATE, prot=mmap.PROT_READ | mmap.PROT_WRITE)
        page[0:4096] = page_content[0:4096]

        if page_offsets == -1:
            page_offsets = [x for x in range(0, 4096, 8)]

        kernel_offsets = len(page_offsets) * [0]

        for offset_idx, offset in enumerate(page_offsets):
            ptr = page_content[offset:offset+8]
            ptr = int.from_bytes(ptr, byteorder='little', signed=False)
            kernel_offsets[offset_idx] = ptr - kernel_text_mapping

    return page, page_offsets, kernel_offsets

def load_binary_page_from_config(page_file, page_offsets, kernel_text_mapping):
    click.echo(f'Loading binary page file {page_file}')

    with open(page_file, "rb") as f:
        page_content = f.read()

        page = mmap.mmap(-1, 4096, flags=mmap.MAP_PRIVATE, prot=mmap.PROT_READ | mmap.PROT_WRITE)
        page[0:4096] = page_content[0:4096]

        if page_offsets == -1:
            page_offsets = [x for x in range(0, 4096, 8)]

        kernel_offsets = len(page_offsets) * [0]

        for offset_idx, offset in enumerate(page_offsets):
            ptr = page_content[offset:offset+8]
            ptr = int.from_bytes(ptr, byteorder='little', signed=False)
            kernel_offsets[offset_idx] = ptr - kernel_text_mapping

    return page, page_offsets, kernel_offsets


def prepare_pages(pages, kernel_text_mapping, kaslr_offset):
    kaslr_address = kernel_text_mapping + kaslr_offset * STEP
    page_hex = bytes()

    for page in pages:
        for offset_idx, offset in enumerate(page.offsets):
            new_address = kaslr_address + page.kernel_offsets[offset_idx]
            ptr = new_address.to_bytes(8, byteorder='little', signed=False)
            page.page[offset:offset+8] = ptr

        page_hex += binascii.hexlify(page.page[0:4096])

    return page_hex


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]
