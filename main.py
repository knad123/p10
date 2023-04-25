import argparse
import random
import time

import yaml
import re
import math
import json

import classes.network
import parsers.communicator
from classes.network import MLPS_Network
from algorithms.essence import essence
from parsers.omnet import to_omnetpp

def main(conf):
    # Load topology
    with open(conf["topology"]) as f:
        topology_data = json.load(f)

    # Add package.ned
    if conf["generate_package"]:
        with open(f"{conf['output_dir']}/package.ned", "w") as f:
            f.write(f"package {conf['package_name']};")

    # Load demands
    with open(conf["demands"], "r") as file:
        demands_list = yaml.load(file, Loader=yaml.BaseLoader)
        # Source, Target : Load
        demands = {tuple(demand[:2]): int(demand[2]) for demand in demands_list}

    mpls_network = MLPS_Network(name=topology_data["network"]["name"], demands=demands)
    # Create the network graph
    mpls_network.create_MPLS_network_topology(topology_data)

    paths = essence(mpls_network)

    for path in paths.values():
        mpls_network.install_lsp(path)

    to_omnetpp(mpls_network, name=mpls_network.name, output_dir=f"{conf['output_dir']}/{mpls_network.name}/{conf['algorithm']}", scaler=conf['scaler'], packet_size=conf["packet_size"], zero_latency=conf["zero_latency"], package_name=conf["package_name"], algorithm=conf["algorithm"], latency_scaler=conf["latency_scaler"])

    while True:
        mpls_network = parsers.communicator.update_demands_and_paths(conf['omnet_path'] + "/demands.json", conf['omnet_path'], mpls_network)
        break

if __name__ == "__main__":
    # Arguments for framework
    p = argparse.ArgumentParser(description='Command line utility to generate MPLS forwarding rules.')
    p.add_argument("--topology", type=str, help="File with existing topology to be loaded.")
    p.add_argument("--demands", type=str, required=True)
    p.add_argument("--algorithm", type=str, required=True)
    p.add_argument("--scaler", type=float, default=1, help="Multiplies the send interval by the scaler value and divides the link bandwidth by the same value")
    p.add_argument("--packet_size", type=int, default=64, help="Size in bytes")
    p.add_argument("--zero_latency", action="store_true", help="Set latency to 0 for all links")
    p.add_argument("--output_dir", default="../inet/zoo")
    p.add_argument("--package_name", default="inet.zoo_topology")
    p.add_argument("--generate_package", action="store_true")
    p.add_argument("--method_name", type=str, default="", help="Name of the algorithm that is used")
    p.add_argument("--latency_scaler", type=float, default=1)
    p.add_argument("--omnet_path", type=str, default="../p10", help="Path to omnet++, used for the demands and 2-phase-commit files")
    p.add_argument("--inet_path", type=str, default="", help="Path to inet")

    conf = vars(p.parse_args())

    main(conf)
