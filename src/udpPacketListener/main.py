import socket
import time
import csv, os
from config import config

def udp_listener(host: str, port: int, OSC: bool, csv_fname: str):

    if OSC:
        from pythonosc import dispatcher, osc_server
        
        def time_handler(unused_addr, args, timest):

            dev_time = time.time_ns()
            print(f"Received time: {timest}")
            print(f"Time on device: {dev_time}")
            print(f"Time diff: {dev_time - timest} ns")

            with open(csv_fname, mode="a", newline="") as csvfile:
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow([timest, dev_time])

        dispatcher = dispatcher.Dispatcher()
        dispatcher.map("/time", time_handler, "Time")

        server = osc_server.ThreadingOSCUDPServer((host, port), dispatcher)
        print(f"Serving on {server.server_address}. Interrupt with Ctrl+C")   

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nListener stopped.")
        

    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        print(f"Listening for UDP packets on {host}:{port}")
        
        packets = []
        
        try:
            while True:
                data, addr = sock.recvfrom(1024)  
                timestamp = time.time()
                packets.append({"timestamp": timestamp, "data": data, "address": addr})
                print(f"Received packet from {addr} at {timestamp}: {data}")
        except KeyboardInterrupt:
            print("\nListener stopped.")
        finally:
            sock.close()
            print("Socket closed.")
        
        return packets  

if __name__ == "__main__":
    csv_fname = f"outputs/{os.path.splitext(config['csv_filename'])[0]}_{int(time.time())}.csv"
    os.makedirs("outputs", exist_ok=True)

    with open(csv_fname, mode="w", newline="") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["Received Time", "Device Time"])
    
    udp_listener(config["host"], config["port"], config["osc"], csv_fname=csv_fname)