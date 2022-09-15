### Run experiment

# Scan kernel pages (stored to log.csv)

    ./kernel-scan

# Dump kallsyms

    sudo cat /proc/kallsyms > kallsyms

# Evaluate

    python evaluate.py log.csv kallsyms output.csv

Result is stored in output.csv
