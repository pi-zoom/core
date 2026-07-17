#!/usr/bin/env python3

import jack
import time

client = jack.Client("port_watcher")


@client.set_graph_order_callback
def graph_changed():
    print("JACK graph changed")

    print("Current ports:")
    for port in client.get_ports():
        print(f"  {port.name}")

    return 0


@client.set_port_registration_callback
def port_changed(port, register):
    if register:
        print(f"Port added:   {port.name}")
    else:
        print(f"Port removed: {port.name}")


client.activate()

print("Listening for JACK port changes...")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping...")
finally:
    client.deactivate()
    client.close()