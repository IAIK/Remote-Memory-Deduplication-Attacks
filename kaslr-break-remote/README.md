# Similar setup to the fingerprinting attack
The attack was evaluated using a pistache HTTP server. 
You can run the provided program in `../pistache_server_app` on your virtual machine.


# Example run
Based on pre-defined YAML configurations (see profiles folder) you can start the attack on your target host with one of the available (use the options to exploit an http or http2 server) strategies:

`python attacker.py -c profiles/packet3/http.yaml attack-league -b 0 -e 511`

A successful run should reveal the correct kernel text mapping.

The results `results` folder contains successful runs to compare your results with.

Check out the other available options:
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
