# Attack Setup
```
sudo ethtool -K enp7s0 tso off gso off gro off tx-gso-partial off
```

Install the python dependencies in your virtualenv with
```
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```


# Victim Setup
On the victim device enable KSM - configure the memory deduplication (default is 100 pages_to_scan, with 200ms time interval). To get faster attacks and results tweak these parameters on a Linux machine.

On Ubuntu 20.04, we observed that when qemu-system-common with KVM support is installed on a host machine, KSM_ENABLED is set to AUTO in /etc/default/qemu-kvm, enabling KSM per default for non-virtualized instances. Same setting for Ubuntu server.

```
echo 200 > /sys/kernel/mm/ksm/sleep_millisecs
echo 0 > /sys/kernel/mm/ksm/merge_across_nodes
echo 100 > /sys/kernel/mm/ksm/pages_to_scan
echo 1 > /sys/kernel/mm/ksm/run
```

On Windows you can activate PageCombining with `Enable-MMAgent -PageCombining`.
Check the configuratoin with `Get-MMAgent`.