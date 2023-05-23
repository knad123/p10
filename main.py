import argparse
import os
import random
import subprocess
import time
import threading
import multiprocessing
from copy import deepcopy

import networkx as nx
import yaml
import re
import math
import json

import parsers.communicator
from classes.network import MLPS_Network
from classes.essence_state import EssenceState
from classes.recorder import Recorder
from algorithms.essence import essence
from algorithms.essence_split import essence_split
from parsers.omnet import to_omnetpp
from parsers.parse_data import parse_results
import os
import shutil
import pickle

import pandas as pd

# Constants
ROOT = os.path.dirname(__file__)
def monitor_omnet(simulation_dir: str, mpls_network: MLPS_Network, essence_state: EssenceState, inet_stopped_event: threading.Event, monitor_stopped_event: threading.Event, conf):
    recorder = Recorder()
    try:
        os.remove("demands.json")
    except:
        pass
    try:
        os.remove("utilization.json")
    except:
        pass
    while not inet_stopped_event.is_set():
        if os.path.exists("demands_done.json") and os.path.exists("utilization_done.json"):
            if conf["algorithm"] in ["essence", "essence_precomputed", "essence_stateless", "fbr"]:
                mpls_network = parsers.communicator.fbr_update_demands_and_paths(simulation_dir, mpls_network, essence_state, recorder, conf)
            else:
                mpls_network = parsers.communicator.update_demands_and_paths(simulation_dir, mpls_network,
                                                                                 essence_state, recorder, conf)
            os.remove("demands.json")
            os.remove("utilization.json")
        time.sleep(1)
    os.chdir(ROOT)
    if not os.path.exists(conf["results_folder"]):
        os.mkdir(conf["results_folder"])
    with open(conf["results_folder"] + "/" + conf['algorithm'] + "_" + mpls_network.name + "_changes" + ".txt", "w") as results:
        results.write(str(recorder.changes))

    monitor_stopped_event.set()

def run_inet_simulation(simulation_directory, inet_stopped_event, ini_conf):
    os.chdir(simulation_directory)
    subprocess.run(['inet', '-u', 'Cmdenv', '-c', f'{ini_conf}'])
    inet_stopped_event.set()

# removes element from list
def filter_list(elem, list):
    new_list = deepcopy(list)
    new_list.remove(elem)
    return new_list

def generate_files(conf, network_name, topology_data, simulation_directory, pkl_dir):
    # Load demands
    with open(conf["demands"], "r") as file:
        demand_data = yaml.load(file, Loader=yaml.BaseLoader)
        temporal_demands = {(src, tgt): loads for src, tgt, loads in demand_data}
        # int(demand[2][0][0]) is just load for first timeslot
        initial_demands = {tuple(demand[:2]): int(demand[2][0][0]) for demand in demand_data}

    mpls_network = MLPS_Network(name=topology_data["network"]["name"], demands=initial_demands)
    # Create the network graph
    mpls_network.create_MPLS_network_topology(topology_data)

    if os.path.isdir(simulation_directory):
        shutil.rmtree(simulation_directory)
    # Create initial routing

    paths = {}
    essence_state = []
    if conf["algorithm"] in ["essence", "essence_precomputed", "essence_stateless"]:
        essence_state = EssenceState(mpls_network)
        paths = essence(mpls_network, essence_state, conf, time.time())
        paths_and_backup_paths = {}
        for (src, tgt), path_list in essence_state.pathdict.items():
            filtered_paths = filter_list(paths[src, tgt], path_list)
            paths_and_backup_paths[src, tgt] = [paths[src, tgt]] + filtered_paths
        for fbr_paths in paths_and_backup_paths.values():
            mpls_network.install_fbr(fbr_paths, algorithm="essence")
    elif conf["algorithm"] == "essence_split":
        essence_state = EssenceState(mpls_network)
        paths = essence_split(mpls_network, essence_state, conf, time.time())
    elif conf["algorithm"] == "shortest_path":
        for src, tgt in temporal_demands.keys():
            paths[src,tgt] = nx.shortest_path(mpls_network.topology, source=src, target=tgt, weight=None)
        for path in paths.values():
            mpls_network.install_lsp(path, 0)
    elif conf["algorithm"] == "fbr":
        essence_state = EssenceState(mpls_network)
        for fbr_paths in essence_state.pathdict.values():
            mpls_network.install_fbr(fbr_paths, algorithm="fbr")


    to_omnetpp(mpls_network, temporal_demands, name=mpls_network.name, conf=conf,
               output_dir=f"{conf['output_dir']}/{mpls_network.name}/{conf['algorithm']}", scaler=conf['scaler'],
               packet_size=conf["packet_size"], zero_latency=conf["zero_latency"], package_name=conf["package_name"],
               algorithm=conf["algorithm"], latency_scaler=conf["latency_scaler"])

    if conf["algorithm"] in ["essence", "essence_precomputed", "essence_stateless"]:
        # Save the essence state in a file
        os.makedirs(pkl_dir, exist_ok=True)
        with open(os.path.join(pkl_dir, "essence_state.pkl"), "wb") as outp:
            pickle.dump(essence_state, outp, pickle.HIGHEST_PROTOCOL)
        with open(os.path.join(pkl_dir, "mpls_network.pkl"), "wb") as outp:
            pickle.dump(mpls_network, outp, pickle.HIGHEST_PROTOCOL)

def main(confs):
    with open(conf["topology"]) as f:
        topology_data = json.load(f)
    network_name = topology_data["network"]["name"]
    simulation_directory = os.path.join(conf['output_dir'], network_name, conf['algorithm'])
    pkl_dir = os.path.abspath(os.path.join(simulation_directory, "pkl_files"))
    # Add package.ned
    if conf["generate_package"]:
        with open(f"{conf['output_dir']}/package.ned", "w") as f:
            f.write(f"package {conf['package_name']};")
    essence_state = []
    mpls_network = []
    if not conf["only_execute"]:
        generate_files(conf, network_name, topology_data, simulation_directory, pkl_dir)

    if conf['no_execution']:
        return

    if conf["configuration"] == "all":
        failure_scenario_configs = []
        if os.path.exists(os.path.join(simulation_directory, "failure_scenarios")):
            failure_scenario_files = os.listdir(os.path.join(simulation_directory, "failure_scenarios"))
            failure_scenario_configs = [x.split(".xml")[0] for x in failure_scenario_files]
        configurations = ["General"] + failure_scenario_configs
    else:
        configurations = [conf["configuration"]]

    for ini_conf in configurations:
        os.chdir(ROOT)
        inet_stopped_event = threading.Event()

        inet_simulation_thread = threading.Thread(target=run_inet_simulation,
                                                  args=(simulation_directory, inet_stopped_event, ini_conf))
        inet_simulation_thread.start()

        if conf['algorithm'] in ['essence', 'essence_stateless']:
            with open(os.path.join(pkl_dir, "essence_state.pkl"), "rb") as inp:
                essence_state = pickle.load(inp)
            with open(os.path.join(pkl_dir, "mpls_network.pkl"), "rb") as inp:
                mpls_network = pickle.load(inp)
            monitor_stopped_event = threading.Event()
            monitor_output_thread = threading.Thread(target=monitor_omnet, args=(
            simulation_directory, mpls_network, essence_state, inet_stopped_event, monitor_stopped_event, conf))
            monitor_output_thread.start()

            while not monitor_stopped_event.is_set():
                time.sleep(1)
        else:
            while not inet_stopped_event.is_set():
                time.sleep(1)
        # Parse results
        os.chdir(ROOT)
        os.system(f"opp_scavetool export -F CSV-R -o {ini_conf}.csv {simulation_directory}/results/{ini_conf}-#0.sca {simulation_directory}/results/{ini_conf}-#0.vec")
        parse_results(f"{ini_conf}.csv", network_name, conf["algorithm"], conf["results_folder"], ini_conf)
        os.remove(f"{ini_conf}.csv")


if __name__ == "__main__":
    # Arguments for framework
    p = argparse.ArgumentParser(description='Command line utility to generate MPLS forwarding rules.')
    p.add_argument("--topology", type=str, help="File with existing topology to be loaded.")
    p.add_argument("--demands", type=str, required=True)
    p.add_argument("--algorithm", type=str, required=True, choices=["essence", "essence_stateless", "essence_precomputed", "shortest_path", "fbr", "essence_split"])
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
    p.add_argument("--no_execution", action="store_true", help="if set, only generate files, dont execute simulation")
    p.add_argument("--results_folder", type=str, default="results", help="folder for results")
    p.add_argument("--time_scale", type=float, default=1, help="the time scale of the experiments. Start and stop times of demands are multiplied by this value. ")
    p.add_argument("--update_interval", type=int, default=120, help="How often the routing is updated in seconds")
    p.add_argument("--utilization_recording_interval", type=int, default=2000, help="time in MS")
    p.add_argument("--recording_sample_duration", type=int, default=10000, help="How long to sample when calculating utilization. Time in MS")
    p.add_argument("--demand_scaler", type=float, default=1, help="Scale demands by this value")
    p.add_argument("--write_interval", type=int, default=5, help="Number of seconds between every time utilization and demands are written. Should be less than update_interval")
    p.add_argument("--disable_dynamic_demands", action="store_true", help="Use dynamically changing send intervals")
    p.add_argument("--jitter", type=float, default=0.02, help="Demand jitter as a percentage")
    p.add_argument("--failure_scenarios", type=int, default=0, help="Number of failure scenarios to generate")
    p.add_argument("--random_seed", type=int, default=1)
    p.add_argument("--only_execute", action="store_true", help="If set, assumes ned and ini files are already generated and will just execute the specified conf(s)")
    p.add_argument("--configuration", type=str, default="all", help="name of the configuration(s) to run")

    conf = vars(p.parse_args())

    assert conf["write_interval"] < conf["update_interval"]
    
    main(conf)
