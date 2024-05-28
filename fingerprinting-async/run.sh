#!/bin/bash

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <IP_ADDRESS> <PORT> <INTERFACE>"
    exit 1
fi

IP_ADDRESS=$1
PORT=$2
INTERFACE=$3

mkdir -p results_local

for i in {1..100}; do
    dd if=/dev/urandom of=random_memory bs=4096 count=32
    dd if=/dev/urandom of=random_memory3 bs=4096 count=32
    
    echo -n "$i;" >> results_local.txt
    
    python3 attacker.py -f random_memory -f libc-2.23.so.32 -f random_memory3 -f libc-2.19.so.32 -h $IP_ADDRESS -p $PORT -d $INTERFACE -n 20 >> results_local.txt
    
    python3 evaluate.py log.csv >> results_local.txt
    
    echo "done with $i"
    
    cp log.csv results_local/$i.csv
done
