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
from classes.network import MPLS_Network, prune_1_degree_nodes, find_high_impact_failures
from classes.essence_state import EssenceState
from classes.recorder import Recorder
from algorithms.essence import essence
from algorithms.essence_split import essence_split
from algorithms.essence_big_flows import essence_big_flows
from algorithms.essence_weight_setting import essence_weight_setting
from algorithms.essence_split_multiple_labels import essence_split_multiple_labels
from algorithms.essence_learn_paths_learn_weights import essence_learn_paths_learn_weights
from algorithms.GAOSPF import GAOSPF
from parsers.omnet import to_omnetpp
from parsers.parse_data import parse_results
import os
import shutil
import pickle

import pandas as pd

# Constants
ROOT = os.path.dirname(__file__)
def monitor_omnet(simulation_dir: str, mpls_network: MPLS_Network, essence_state: EssenceState, inet_stopped_event: threading.Event, monitor_stopped_event: threading.Event, conf):
    recorder = Recorder()
    while not inet_stopped_event.is_set():
        if os.path.exists(conf["demand_path"]) and os.path.exists(conf["utilization_path"]) and os.path.exists(conf["link_failures_path"]) and not os.path.exists(conf["2pc_path"]) and not os.path.exists(conf["dynamic_weights_path"]):
            start_time = time.time()
            mpls_network = parsers.communicator.update_demands_and_paths(simulation_dir, mpls_network,
                                                                             essence_state, recorder, conf)
            os.remove(conf["demand_path"])
            os.remove(conf["utilization_path"])
            os.remove(conf["link_failures_path"])
            print(f"Essence iteration time: {time.time() - start_time}")
        time.sleep(1)
    os.chdir(ROOT)
    if not os.path.exists(conf["results_folder"]):
        os.mkdir(conf["results_folder"])
    with open(os.path.join(conf["results_folder"], f"{conf['algorithm']}_{mpls_network.name}_{conf['configuration']}_changes.txt"), "w") as results:
        results.write(str(recorder.changes))

    monitor_stopped_event.set()

def run_inet_simulation(simulation_directory, inet_stopped_event, ini_conf):
    os.chdir(simulation_directory)
    subprocess.run(['inet', '-u', 'Cmdenv', '-c', f'{ini_conf}'])
    #subprocess.run(['inet', '-c', f'{ini_conf}'])
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

    mpls_network = MPLS_Network(name=topology_data["network"]["name"], demands=initial_demands)
    # Create the network graph
    mpls_network.create_MPLS_network_topology(topology_data)
    #mpls_network.pruned_topology = prune_1_degree_nodes(mpls_network.topology)
    #mpls_network.fail_graph_dict = find_high_impact_failures(mpls_network.topology, mpls_network.pruned_topology, mpls_network.demands)

    if os.path.isdir(simulation_directory):
        shutil.rmtree(simulation_directory)
    
    # Create initial routing
    paths = {}
    essence_state = []
    if conf["algorithm"] in ["essence", "essence_precomputed", "essence_stateless", 'essence_big_flows', "essence_shortest_paths"]:
        essence_state = EssenceState(mpls_network)
        if conf["algorithm"] == "essence_shortest_paths":
            essence_state.create_shortest_path_pathdict(mpls_network)
        else:
            essence_state.create_pathdict(mpls_network)
        essence_state.create_stretchdict(mpls_network)
        paths = essence(mpls_network, essence_state, conf, time.time())
        paths_and_backup_paths = {}
        for (src, tgt), path_list in essence_state.pathdict.items():
            filtered_paths = filter_list(paths[src, tgt], path_list)
            paths_and_backup_paths[src, tgt] = [paths[src, tgt]] + filtered_paths
        for fbr_paths in paths_and_backup_paths.values():
            mpls_network.install_fbr(fbr_paths, algorithm="essence")
    elif conf["algorithm"] == "essence_split":
        essence_state = EssenceState(mpls_network)
        essence_state.create_bfs_pathdict(mpls_network, conf['stretch_amount'])
        paths = essence_split(mpls_network, essence_state, conf, time.time())
        for path in paths.values():
            mpls_network.install_split_path_essence(path, labels_per_flow=conf['labels_per_flow'])
    elif conf["algorithm"] == "essence_weight_setting":
        essence_state = EssenceState(mpls_network)
        essence_state.all_shortest_path_pathdict(mpls_network)
        essence_state.link_weights = essence_weight_setting(mpls_network, essence_state, conf, time.time())
        for path in essence_state.pathdict.values():
            mpls_network.install_split_paths_for_essence_weight_setting(path)
    elif conf["algorithm"] == "essence_split_multiple_labels":
        essence_state = EssenceState(mpls_network)
        essence_state.create_pathdict(mpls_network)
        essence_state.path_weights = essence_split_multiple_labels(mpls_network, essence_state, conf, time.time())
        for fbr_paths in essence_state.pathdict.values():
            mpls_network.install_fbr(fbr_paths, algorithm="fbr")
    elif conf['algorithm'] == "essence_learn_paths_learn_weights":
        essence_state = EssenceState(mpls_network)
        essence_state.create_bfs_pathdict(mpls_network, conf['stretch_amount'])
        paths, essence_state.link_weights = essence_learn_paths_learn_weights(mpls_network, essence_state, conf, time.time())
        for path_for_flow in paths.values():
            mpls_network.install_essence_learn_paths_learn_weights(path_for_flow)
    elif conf["algorithm"] == "shortest_path":
        for src, tgt in temporal_demands.keys():
            paths[src,tgt] = nx.shortest_path(mpls_network.topology, source=src, target=tgt, weight=None)
        for path in paths.values():
            mpls_network.install_lsp(path, 0)
    elif conf["algorithm"] == "split_shortest_path":
        for src, tgt in temporal_demands.keys():
            paths[src,tgt] = list(nx.all_shortest_paths(mpls_network.topology, src, tgt, weight=None))
        for p in paths.values():
            mpls_network.install_split_path_essence(p)
    elif conf["algorithm"] == "fbr":
        essence_state = EssenceState(mpls_network)
        essence_state.create_pathdict(mpls_network)
        essence_state.create_stretchdict(mpls_network)
        for fbr_paths in essence_state.pathdict.values():
            mpls_network.install_fbr(fbr_paths, algorithm="fbr")
    elif conf["algorithm"] == "GAOSPF":
        essence_state = EssenceState(mpls_network)
        pathdict = GAOSPF(mpls_network, conf, time.time())
        mpls_network.install_GAOSPF(pathdict)


    to_omnetpp(mpls_network, temporal_demands, name=mpls_network.name, conf=conf,
               output_dir=f'{conf["sim_dir"]}', scaler=conf['scaler'],
               packet_size=conf["packet_size"], zero_latency=conf["zero_latency"], package_name=conf["package_name"],
               algorithm=conf["algorithm"], latency_scaler=conf["latency_scaler"], essence_state=essence_state)

    if conf["algorithm"] in ["essence", "essence_precomputed", "essence_stateless", "essence_split", 'essence_big_flows', "essence_weight_setting", "essence_split_multiple_labels", "GAOSPF", "essence_learn_paths_learn_weights"]:
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
    if conf['algorithm'] in ["essence_split", "essence_learn_paths_learn_weights"]:
        conf['algorithm_and_parameters'] = conf['algorithm'] + "_p" + str(conf['population']).replace(".","_") + "_c" + str(conf['crossover']).replace(".","_") + "_m" + str(conf['mutation']).replace(".","_") + "_numpaths" + str(conf['split_num']).replace(".","_") + "_pathstretch" + str(conf['stretch_amount']).replace(".","_")
    elif conf['algorithm'] not in ["fbr", "shortest_path", "split_shortest_path", "GAOSPF"]:
        conf['algorithm_and_parameters'] = conf['algorithm'] + "_p" + str(conf['population']).replace(".","_") + "_c" + str(conf['crossover']).replace(".","_") + "_m" + str(conf['mutation']).replace(".","_")
    else:
        conf['algorithm_and_parameters'] = conf['algorithm']
    simulation_directory = os.path.join(conf['output_dir'], network_name, conf['algorithm_and_parameters'])
    conf["sim_dir"] = simulation_directory
    if conf["sync_dir"] == "":
        conf["sync_dir"] = os.path.abspath(simulation_directory)
    os.makedirs(conf["sync_dir"], exist_ok=True)
    os.makedirs(os.path.join(conf["results_folder"], network_name, conf['algorithm_and_parameters']), exist_ok=True)
    pkl_dir = os.path.abspath(os.path.join(simulation_directory, "pkl_files"))
    # Add package.ned
    if conf["generate_package"]:
        packet_path = os.path.join(conf["output_dir"], "package.ned")
        if not os.path.exists(packet_path):
            with open(packet_path, "w") as f:
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
        configurations = conf["configuration"].split(" ")

    for ini_conf in configurations:
        conf["configuration"] = ini_conf
        conf["demand_path"] = os.path.join(conf["sync_dir"], f"demands-{ini_conf}.json")
        conf["utilization_path"] = os.path.join(conf["sync_dir"], f"utilization-{ini_conf}.json")
        conf["link_failures_path"] = os.path.join(conf["sync_dir"], f"link_failures-{ini_conf}.json")
        conf["2pc_path"] = os.path.join(conf["sync_dir"], f'2-phase-commit-{ini_conf}.xml')
        conf["temp_2pc_path"] = os.path.join(conf["sync_dir"], f'temp-2-phase-commit-{ini_conf}.xml')
        conf["dynamic_weights_path"] = os.path.join(conf["sync_dir"], f'dynamic_weights-{ini_conf}.xml')
        conf["temp_dynamic_weights_path"] = os.path.join(conf["sync_dir"], f'temp-dynamic_weights-{ini_conf}.xml')
        try:
            os.remove(conf["demand_path"])
        except:
            pass
        try:
            os.remove(conf["utilization_path"])
        except:
            pass
        try:
            os.remove(conf["link_failures_path"])
        except:
            pass
        try:
            os.remove(conf["2pc_path"])
        except:
            pass
        try:
            os.remove(conf["dynamic_weights_path"])
        except:
            pass
        os.chdir(ROOT)
        inet_stopped_event = threading.Event()

        inet_simulation_thread = threading.Thread(target=run_inet_simulation,
                                                  args=(simulation_directory, inet_stopped_event, ini_conf))
        inet_simulation_thread.start()

        if conf['algorithm'] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "essence_weight_setting", "essence_split_multiple_labels", "GAOSPF", "essence_learn_paths_learn_weights"]:
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
        csv_path = os.path.join(os.path.abspath(simulation_directory), f"{ini_conf}.csv")
        os.system(f"opp_scavetool export -F CSV-R -o {csv_path} {simulation_directory}/results/{ini_conf}-#0.sca {simulation_directory}/results/{ini_conf}-#0.vec")
        parse_results(csv_path, network_name, conf["algorithm"], os.path.join(conf["results_folder"], network_name, conf['algorithm_and_parameters']), ini_conf)
        os.remove(csv_path)
        os.remove(f"{simulation_directory}/results/{ini_conf}-#0.sca")
        os.remove(f"{simulation_directory}/results/{ini_conf}-#0.vec")


if __name__ == "__main__":
    # Arguments for framework
    p = argparse.ArgumentParser(description='Command line utility to generate MPLS forwarding rules.')
    p.add_argument("--topology", type=str, help="File with existing topology to be loaded.")
    p.add_argument("--demands", type=str, required=True)
    p.add_argument("--algorithm", type=str, required=True, choices=["essence", "essence_stateless", "essence_precomputed", "shortest_path", "fbr", "essence_split", "essence_big_flows", "essence_shortest_paths", "split_shortest_path", "essence_weight_setting", "essence_split_multiple_labels", "GAOSPF", "essence_learn_paths_learn_weights"])
    p.add_argument("--scaler", type=float, default=1,
                   help="Multiplies the send interval by the scaler value and divides the link bandwidth by the same value")
    p.add_argument("--packet_size", type=int, default=64, help="Size in bytes")
    p.add_argument("--zero_latency", action="store_true", help="Set latency to 0 for all links")
    p.add_argument("--output_dir", default="../inet/zoo")
    p.add_argument("--package_name", default="inet.zoo_topology")
    p.add_argument("--generate_package", action="store_true")
    p.add_argument("--sync_dir", type=str, default="", help="Directory where the synchronization files will be")
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
    p.add_argument("--labels_per_flow", type=int, default=4)
    p.add_argument("--crossover", type=float, default=0.7)
    p.add_argument("--mutation", type=float, default=0.2)
    p.add_argument("--population", type=int, default=250)
    p.add_argument("--split_num", type=int, default=6, help="number of paths for split_essence")
    p.add_argument("--stretch_amount", type=float, default=2, help="how much longer paths can be than the shortest path")


    conf = vars(p.parse_args())

    assert conf["write_interval"] < conf["update_interval"]
    
    main(conf)
