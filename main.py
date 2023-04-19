import argparse
import yaml
import re
import math
import json

import classes.network
from classes.network import MLPS_Network
from algorithms.essence import essence
from parsers.omnet import to_omnetpp

def main(conf):
    # Load topology
    with open(conf["topology"]) as f:
        topology_data = json.load(f)

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

    to_omnetpp(mpls_network, name=mpls_network.name, algorithm="essence")

    print("done")


if __name__ == "__main__":
    # Arguments for framework
    p = argparse.ArgumentParser(description='Command line utility to generate MPLS forwarding rules.')
    p.add_argument("--topology", type=str, help="File with existing topology to be loaded.")
    p.add_argument("--demands", type=str, required=True)

    conf = vars(p.parse_args())

    main(conf)
