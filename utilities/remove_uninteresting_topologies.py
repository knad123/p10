import json
import os
import shutil
import time

import networkx
import yaml

def create_MPLS_network_topology(topology_data):
    network = networkx.DiGraph()

    # Add links between routers
    for link_data in topology_data["network"]["links"]:
        source_router = link_data["from_router"]
        target_router = link_data["to_router"]
        latency = link_data["latency"]
        capacity = link_data["bandwidth"]

        # Add edges to the graph with capacity attribute
        network.add_edge(source_router, target_router, latency=latency, capacity=capacity)

        # Assume all links are bidirectional
        network.add_edge(target_router, source_router, latency=latency, capacity=capacity)

    return network

def prune_n_degree_nodes(graph, degree=1):
    # Create a copy of the original graph
    pruned_graph = graph.copy()

    # Get a list of all nodes with degree 1
    nodes_to_remove = [node for node in pruned_graph.nodes if pruned_graph.degree[node] == degree]

    # Base case: if no 1 degree nodes found, return the pruned graph
    if not nodes_to_remove:
        return pruned_graph

    # Prune all 1 degree nodes
    for node in nodes_to_remove:
        pruned_graph.remove_node(node)

    # Recursively prune more 1 degree nodes
    return prune_n_degree_nodes(pruned_graph)

interesting_topologies = []

for topology in os.listdir("../topologies"):
    with open(os.path.join("../topologies", topology), "r") as f:
        topology_info = json.load(f)

    network = create_MPLS_network_topology(topology_info)
    network = network.to_undirected()

    network = prune_n_degree_nodes(network, 1)

    if len(network.nodes) >= 15:
        interesting_topologies.append(topology)

print(len(interesting_topologies))
for topo in interesting_topologies:
    print(topo)

if os.path.exists("../interesting_scaled_topologies"):
    os.rmdir("../interesting_scaled_topologies")
os.mkdir("../interesting_scaled_topologies")

for topology in os.listdir("../scaled_topologies"):
    if topology in interesting_topologies:
        source_path = os.path.join("../scaled_topologies", topology)
        destination_path = os.path.join("../interesting_scaled_topologies", topology)
        shutil.copy(source_path, destination_path)