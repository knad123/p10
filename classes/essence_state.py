from typing import Tuple, List

import networkx
import networkx as nx
from networkx import shortest_path

from classes.network import MPLS_Network


class EssenceState:
    def __init__(self, network: MPLS_Network):
        self.pathdict = dict()
        self.stretchdict = dict()
        self.current_population = []
        self.congestion_weight = 1
        self.link_weights = {}
        self.path_weights = {}


    def create_stretchdict(self, network: MPLS_Network):
        shortest_paths_len = dict()
        stretch_dict = {}

        for src, tgt in network.demands.keys():
            shortest_paths_len[(src, tgt)] = len(shortest_path(network.topology, src, tgt))

        # Create stretch dictionary, so it does not have to be recomputed in the genetic algorithm
        for src, tgt in network.demands.keys():
            # Calculate the stretch value for each path between the source and destination
            for path in self.pathdict[src, tgt]:
                path_tuple = tuple(path)
                path_len = len(path)
                stretch_dict[path_tuple] = (path_len / shortest_paths_len[src, tgt])

        self.stretchdict = stretch_dict

    def create_pathdict(self, network: MPLS_Network):

        path_dict = dict()

        for (src, tgt), load in network.demands.items():
            for v1111, v2222 in network.topology.edges:
                network.topology[v1111][v2222]["weight"] = 0
            unique_paths = []
            num_paths = 0
            while num_paths < 20:
                path = nx.dijkstra_path(network.topology, src, tgt, weight="weight")
                for i in range(len(path) - 1):
                    v1 = path[i]
                    v2 = path[i + 1]
                    w = network.topology[v1][v2]["weight"]
                    w = w * 2 + 1
                    network.topology[v1][v2]["weight"] = w
                if path not in unique_paths:
                    unique_paths.append(path)
                    path_dict[src, tgt] = unique_paths
                num_paths += 1

        self.pathdict = path_dict

    def all_shortest_path_pathdict(self, network: MPLS_Network):
        for src,tgt in network.demands.keys():
            self.pathdict[src,tgt] = list(networkx.all_shortest_paths(network.topology, src, tgt, weight=None))
    def create_shortest_path_pathdict(self, network: MPLS_Network):
        for src,tgt in network.demands.keys():
            self.pathdict[src,tgt] = find_paths_within_percentage_increase(network.topology, src, tgt, 0.2)

    def create_bfs_pathdict(self, network: MPLS_Network, depth_limit = 2):
        for src,tgt in network.demands.keys():
            self.pathdict[src, tgt] = []
            shortest_path_len = nx.shortest_path_length(network.topology, src, tgt)

            for path in nx.all_simple_paths(network.topology, source=src, target=tgt, cutoff=depth_limit * shortest_path_len):
                if len(path) - 1 <= 2 * shortest_path_len:
                    self.pathdict[src,tgt].append(path)

def find_paths_within_percentage_increase(graph, source, target, percentage_increase):
    shortest_path_length = nx.shortest_path_length(graph, source, target)
    max_path_length = shortest_path_length * (1 + percentage_increase)

    paths = []
    for path in nx.all_simple_paths(graph, source, target):
        path_length = len(path) - 1

        if path_length <= max_path_length:
            paths.append(path)

    return paths