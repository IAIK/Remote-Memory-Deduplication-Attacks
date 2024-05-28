# Library Fingerprinting
This project is a showcase how to use remote-memory deduplication attacks to fingerprint libraries.

# Setup
Use the provided nginx configuration, setup a VM running KVM, also enable the PHP memcached plugin and nginx and host the files provided in `php_server` with memory deduplication enabled. 


# Running the proof-of-concept
This proof-of-concept fingerprints the libc version of the target VM by exploiting memory deduplication.
Use `./run.sh IP PORT INTERFACE` to start the attack once your target system setup is ready.
Based on the templates you are using you should see a clear difference if the correct libc version.

The proof-of-concept uses amplification to deal with the network latency.