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

def prune_n_degree_nodes(graph, degree=2):
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



def prune_nodes(graph, name):
    pruned_nodes = {}

    remove_nodes = []
    nodes_to_remove = True
    while nodes_to_remove:
        nodes_to_remove = False
        for node in graph.nodes:
            neighbors = list(graph.neighbors(node))
            if graph.degree[node] == 2:
                neighbor = neighbors[0]
                nodes_to_remove = True
                if node in pruned_nodes:
                    if neighbor in pruned_nodes:
                        pruned_nodes[neighbor] = [node] + pruned_nodes[node] + pruned_nodes[neighbor]
                    else:
                        pruned_nodes[neighbor] = [node] + pruned_nodes[node]
                    del pruned_nodes[node]
                elif neighbor in pruned_nodes:
                    pruned_nodes[neighbor] = [node] + pruned_nodes[neighbor]
                else:
                    pruned_nodes[neighbor] = [node]
                remove_nodes.append(node)

        for node in remove_nodes:
            graph.remove_node(node)
        remove_nodes = []



    return pruned_nodes


def extract_graph_data(graph):
    routers = list(graph.nodes)
    links = list(graph.edges)
    return routers, links

# Example usage:
# routers, links = extract_graph_data(your_networkx_graph)

# Step 2: Create set of router names and link tuples
def create_filter_set(routers, links):
    router_set = set(routers)
    link_set = set((src, dst) for src, dst in links)
    return router_set, link_set

# Example usage:
# router_set, link_set = create_filter_set(routers, links)

# Step 3: Filter out routers and links not present in the graph
def filter_graph_data(graph_data, router_set, link_set):
    filtered_data = {'network': {'name': graph_data['network']['name']}}
    filtered_routers = [router for router in graph_data['network']['routers'] if router['name'] in router_set]
    filtered_links = [link for link in graph_data['network']['links'] if (link['from_router'], link['to_router']) in link_set]
    filtered_data['network']['routers'] = filtered_routers
    filtered_data['network']['links'] = filtered_links
    return filtered_data














interesting_topologies = []

if os.path.exists("../pruned_demands"):
    shutil.rmtree("../pruned_demands")
os.mkdir("../pruned_demands")

if os.path.exists("../pruned_scaled_topologies"):
    shutil.rmtree("../pruned_scaled_topologies")
os.mkdir("../pruned_scaled_topologies")

for topology in os.listdir("../scaled_topologies"):
    with open(os.path.join("../scaled_topologies", topology), "r") as f:
        topology_info = json.load(f)

    network = create_MPLS_network_topology(topology_info)

    test_interesting = prune_n_degree_nodes(network.copy(), 2)

    if (len(test_interesting.nodes) > 10) and (len(test_interesting.nodes) < 60):
        interesting_topologies.append(topology)

        topology_name = topology.split(".json")[0]
        topology_name = topology_name.split("_")[1]
        for demand in os.listdir("../demands"):
            demand_name = demand.split(".yml")[0]
            demand_name = demand.split("_")[0]
            if demand_name == topology_name:
                output = os.path.join("scaled_demands", demand)
                with open("/home/andreas/Documents/GitHub/p10/demands/" + demand, "r") as file:
                    flows_with_load = {}
                    flow_load = []
                    for (src,tgt,load) in yaml.load(file, Loader=yaml.BaseLoader):
                        flow_load.append([src,tgt,load])
                        if src not in flows_with_load:
                            flows_with_load[src] = {}
                        flows_with_load[src][tgt] = int(load)

                    removed_nodes = prune_nodes(network.copy(), topology_name)

                    total_removed = []
                    for node_lst in removed_nodes.values():
                        for node_removed in node_lst:
                            total_removed.append(node_removed)
                    for node, pruned in removed_nodes.items():
                        for removed_node in pruned:
                            for tgt, load in flows_with_load[removed_node].items():
                                if tgt in pruned:
                                    continue
                                elif (tgt not in total_removed) and (tgt != node):
                                    flows_with_load[node][tgt] += load
                                elif tgt in total_removed:
                                    for node2, pruned2 in removed_nodes.items():
                                        if (tgt in pruned2) and (node != node2):
                                            flows_with_load[node][node2] += load

                    flows_with_load = {
                        src: {tgt: load for tgt, load in flows_with_load[src].items() if tgt not in total_removed}
                        for src in flows_with_load if src not in total_removed}

                    file_list = []
                    for src, tgt_loads in flows_with_load.items():
                        for tgt, load in tgt_loads.items():
                            file_list.append([src,tgt,load])

                    with open("/home/andreas/Documents/GitHub/p10/pruned_demands/" + demand, "w") as file:
                        file.write(str(file_list))

        routers, links = extract_graph_data(test_interesting)
        router_set, link_set = create_filter_set(routers, links)
        filtered_topology = filter_graph_data(topology_info, router_set, link_set)

        with open("../pruned_scaled_topologies/" + topology, "w") as file:
            json.dump(filtered_topology, file)