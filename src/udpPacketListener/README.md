# UDP / OSC Listener

A simple utility to listen for OSC time messages and logging them to CSV for post-hoc analyses.

## Configuration

Edit `config.py`:

```json
{
    "host": "0.0.0.0", //Add your device's IP address here
    "port": 9005,
    "osc": true,
    "csv_filename": "udp_listener" //default filename
}
```

## Usage

Run the listener directly or from the demo.py script.

Output will be saved in: outputs/ directory as a csv file.


## OSC Mode

When `osc = true`, the listener expects OSC messages with:

* **Address**: `/time`
* **Arguments**: single timestamp value (nanoseconds)


## UDP Mode

When `osc = false`, the listener:

* Receives raw UDP packets
* Logs packet data, sender address, and receive timestamp
* Stores packets in memory until interrupted


## Use Cases

* Network latency measurement
* Synchronization with other devices/systems on the network