import argparse
import os
import random
import subprocess
import time
import threading
import multiprocessing

import yaml
import re
import math
import json

import parsers.communicator
from classes.network import MLPS_Network
from classes.essence_state import EssenceState
from classes.recorder import Recorder
from algorithms.essence import essence
from parsers.omnet import to_omnetpp
import os
import shutil

# Constants
ROOT = os.path.dirname(__file__)

def monitor_omnet(simulation_dir: str, mpls_network: MLPS_Network, essence_state: EssenceState, inet_stopped_event: threading.Event, conf):
    recorder = Recorder()
    while not inet_stopped_event.is_set():
        if os.path.exists("demands_done.json") and os.path.exists("utilization_done.json"):
            mpls_network = parsers.communicator.update_demands_and_paths(simulation_dir, mpls_network, essence_state, recorder, conf)
            os.remove("demands.json")
            os.remove("utilization.json")
            os.remove("demands_done.json")
            os.remove("utilization_done.json")
        time.sleep(1)
    os.chdir(ROOT)
    if not os.path.exists(conf["results_folder"]):
        os.mkdir(conf["results_folder"])
    with open(conf["results_folder"] + "/" + conf['algorithm'] + "_" + mpls_network.name + "_changes" + ".txt", "w") as results:
        results.write(str(recorder.changes))

def run_inet_simulation(simulation_directory, inet_stopped_event):
    os.chdir(simulation_directory)
    subprocess.run(['inet', '-u', 'Cmdenv'])
    #subprocess.run(['inet'])
    inet_stopped_event.set()
    
def main(confs):
    # Load topology
    with open(conf["topology"]) as f:
        topology_data = json.load(f)

    # Add package.ned
    if conf["generate_package"]:
        with open(f"{conf['output_dir']}/package.ned", "w") as f:
            f.write(f"package {conf['package_name']};")

    # Load demands
    with open(conf["demands"], "r") as file:
        demand_data = yaml.load(file, Loader=yaml.BaseLoader)
        temporal_demands = {(src, tgt): loads for src, tgt, loads in demand_data}
        # int(demand[2][0][0]) is just load for first timeslot
        initial_demands = {tuple(demand[:2]): int(demand[2][0][0]) for demand in demand_data}

    mpls_network = MLPS_Network(name=topology_data["network"]["name"], demands=initial_demands)
    # Create the network graph
    mpls_network.create_MPLS_network_topology(topology_data)

    simulation_directory = os.path.join(conf['output_dir'], mpls_network.name, conf['algorithm'])
    if os.path.isdir(simulation_directory):
        shutil.rmtree(simulation_directory)
    # Create initial routing

    paths = {}

    if conf["algorithm"] in ["essence", "essence_precomputed", "essence_stateless"]:
        essence_state = EssenceState(mpls_network)
        paths = essence(mpls_network, essence_state, conf)

    for path in paths.values():
        mpls_network.install_lsp(path)

    to_omnetpp(mpls_network, temporal_demands, name=mpls_network.name, conf=conf,
               output_dir=f"{conf['output_dir']}/{mpls_network.name}/{conf['algorithm']}", scaler=conf['scaler'],
               packet_size=conf["packet_size"], zero_latency=conf["zero_latency"], package_name=conf["package_name"],
               algorithm=conf["algorithm"], latency_scaler=conf["latency_scaler"])

    if conf['no_omnet']:
        return

    inet_stopped_event = threading.Event()

    inet_simulation_thread = threading.Thread(target=run_inet_simulation,
                                              args=(simulation_directory, inet_stopped_event,))
    inet_simulation_thread.start()

    if conf['algorithm'] in ['essence', 'essence_stateless']:
        monitor_output_thread = threading.Thread(target=monitor_omnet, args=(
        simulation_directory, mpls_network, essence_state, inet_stopped_event, conf))
        monitor_output_thread.start()

if __name__ == "__main__":
    # Arguments for framework
    p = argparse.ArgumentParser(description='Command line utility to generate MPLS forwarding rules.')
    p.add_argument("--topology", type=str, help="File with existing topology to be loaded.")
    p.add_argument("--demands", type=str, required=True)
    p.add_argument("--algorithm", type=str, required=True, choices=["essence", "essence_stateless", "essence_precomputed"])
    p.add_argument("--scaler", type=float, default=1,
                   help="Multiplies the send interval by the scaler value and divides the link bandwidth by the same value")
    p.add_argument("--packet_size", type=int, default=64, help="Size in bytes")
    p.add_argument("--zero_latency", action="store_true", help="Set latency to 0 for all links")
    p.add_argument("--output_dir", default="../inet/zoo")
    p.add_argument("--package_name", default="inet.zoo_topology")
    p.add_argument("--generate_package", action="store_true")
    p.add_argument("--method_name", type=str, default="", help="Name of the algorithm that is used")
    p.add_argument("--latency_scaler", type=float, default=1)
    p.add_argument("--omnet_path", type=str, default="../p10",
                   help="Path to omnet++, used for the demands and 2-phase-commit files")
    p.add_argument("--inet_path", type=str, default="", help="Path to inet")
    p.add_argument("--no_omnet", action="store_true")
    p.add_argument("--results_folder", type=str, default="results", help="folder for results")
    p.add_argument("--time_scale", type=float, default=1, help="the time scale of the experiments. Start and stop times of demands are multiplied by this value. ")
    p.add_argument("--update_interval", type=int, default=120, help="How often the routing is updated in seconds")

    conf = vars(p.parse_args())
    
    main(conf)
