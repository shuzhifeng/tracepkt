#!/usr/bin/env python
# coding: utf-8

import sys
from socket import inet_ntop, AF_INET, AF_INET6
from bcc import BPF
import ctypes as ct
import subprocess
from struct import pack

IFNAMSIZ = 16 # uapi/linux/if.h

class TestEvt(ct.Structure):
    _fields_ = [
        # Routing information
        ("ifname",  ct.c_char * IFNAMSIZ),
        ("netns",   ct.c_ulonglong),

        # Packet type (IPv4 or IPv6) and address
        ("ip_version",  ct.c_ulonglong),
        ("icmptype",    ct.c_ulonglong),
        ("icmpid",      ct.c_ulonglong),
        ("icmpseq",     ct.c_ulonglong),
        ("saddr",       ct.c_ulonglong * 2),
        ("daddr",       ct.c_ulonglong * 2),
    ]

PING_PID="-1"

def event_printer(cpu, data, size):
    # Decode event
    event = ct.cast(data, ct.POINTER(TestEvt)).contents

    # Make sure it is OUR ping process
    if event.icmpid != PING_PID:
        return

    # Decode address
    if event.ip_version == 4:
        saddr = inet_ntop(AF_INET, pack("=I", event.saddr[0]))
        daddr = inet_ntop(AF_INET, pack("=I", event.daddr[0]))
    elif event.ip_version == 6:
        saddr = inet_ntop(AF_INET6, event.saddr)
        daddr = inet_ntop(AF_INET6, event.daddr)
    else:
        return

    # Decode direction
    if event.icmptype in [8, 128]:
        direction = "request"
    elif event.icmptype in [0, 129]:
        direction = "reply"
    else:
        return

    # Print event
    print "[%12s] %16s %7s %s -> %s" % (event.netns, event.ifname, direction, saddr, daddr)

if __name__ == "__main__":
    # Get arguments
    if len(sys.argv) == 1:
        TARGET = '127.0.0.1'
    elif len(sys.argv) == 2:
        TARGET = sys.argv[1]
    else:
        print "Usage: %s [TARGET_IP]" % (sys.argv[0])
        sys.exit(1)

    # Build probe and open event buffer
    b = BPF(src_file='tracepkt.c')
    b["route_evt"].open_perf_buffer(event_printer)

    # Launch a background ping process
    with open('/dev/null', 'r') as devnull:
        ping = subprocess.Popen([
                '/bin/ping',
                '-c1',
                TARGET,
            ],
            stdout=devnull,
            stderr=devnull,
            close_fds=True,
        )
    PING_PID = ping.pid

    print "%14s %16s %7s %s" % ('NETWORK NS', 'INTERFACE', 'TYPE', 'ADDRESSES')

    # Listen for event until the ping process has exited
    while ping.poll() is None:
        b.kprobe_poll(10)

    # Forward ping's exit code
    sys.exit(ping.poll())

