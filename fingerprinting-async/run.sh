#!/bin/bash
mkdir -p results_local
for i in {82..100} ;
do
    dd if=/dev/urandom of=random_memory bs=4096 count=32
    dd if=/dev/urandom of=random_memory3 bs=4096 count=32
    echo -n "$i;" >> results_local.txt
    python3 attacker.py -f random_memory -f libc-2.23.so.32 -f random_memory3 -f libc-2.19.so.32  -h 10.27.142.89 -p 7777 -d enp7s0 -n 20 >> results_local.txt
    python3 evaluate.py log.csv >> results_local.txt
    echo "done with $i";
    cp log.csv results_local/$i.csv
done
