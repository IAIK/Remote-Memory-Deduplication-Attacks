#!/bin/bash
for i in {1..100}; 
do
  python3 evaluate.py results/$i.csv
done

