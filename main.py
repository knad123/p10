import argparse
import yaml
import re
import math
import json

import classes.network
from classes.network import MLPS_Network

def main(conf):
    # Load topology
    with open(conf["topology"]) as f:
        topology_data = json.load(f)

    mpls_network = instantiate_MPLS_Network(topology_data)

    path = ['a0_SRI', 'a1_USCB', 'a2_UCLA']

    mpls_network.install_lsp(path)

def instantiate_MPLS_Network(topology_data):
    # Create mpls_network
    mpls_network = MLPS_Network()

    # Add routers to the network
    for router_data in topology_data["network"]["routers"]:
        router_name = router_data["name"]
        mpls_network.add_router(router_name)

    # Add links between routers
    for link_data in topology_data["network"]["links"]:
        source_router = link_data["from_router"]
        target_router = link_data["to_router"]
        latency = link_data["latency"]
        capacity = link_data["bandwidth"]

        # Add edges to the graph with capacity attribute
        mpls_network.topology.add_edge(source_router, target_router, cost=latency, capacity=capacity)

        # Assume all links are bidirectional
        mpls_network.topology.add_edge(target_router, source_router, cost=latency, capacity=capacity)

    return mpls_network


if __name__ == "__main__":
    # Arguments for framework
    p = argparse.ArgumentParser(description='Command line utility to generate MPLS forwarding rules.')
    p.add_argument("--topology", type=str, help="File with existing topology to be loaded.")
    p.add_argument("--demand_file", type=str, required=True)

    conf = vars(p.parse_args())

    main(conf)
