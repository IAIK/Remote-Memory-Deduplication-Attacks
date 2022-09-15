```
Usage: attacker.py [OPTIONS] COMMAND [ARGS]...

Options:
  --debug / --no-debug
  -c, --config PATH
  -b, --backend [requests|aiohttp|httpx|h2time]
  -t, --kernel-text-mapping TEXT
  -m, --http-version [http|http2]
  -t, --monitor-traffic BOOLEAN
  -h, --host TEXT
  -p, --port INTEGER
  -d, --device TEXT
  -f, --page-file PATH
  -o, --offset TEXT
  --help                          Show this message and exit.

Commands:
  attack-chunks        Perform KASLR break on chunks
  attack-league        Perform KASLR break league based on counts
  attack-league-http2  Perform KASLR break league based on counts
  attack-league2       Perform KASLR break league based on mean
  attack-range         Perform KASLR break on a range of offsets
  attack-range-http2   Perform KASLR break on a range of offsets
  attack-range3        Perform KASLR break on a range of offsets
  evaluate-raw         Evaluate strategy based on raw file
```
