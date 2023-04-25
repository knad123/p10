import networkx as nx
import pandas as pd
from typing import Any, Dict, List, Union

from classes.label_generator import MPLS_Label_Generator
from classes.router import MPLS_Router

class MLPS_Network:
    def __init__(self, name: str = None, demands: Dict[str, str] = None):
        self.name = name
        self.topology = nx.DiGraph()
        self.routers = {}
        self.label_generator = MPLS_Label_Generator()
        self.demand_dataframe = pd.DataFrame()
        self.demands = demands
        self.external_connections = {}

    def add_router(self, name: str):
        router = MPLS_Router(name=name)
        self.routers[name] = router

    def install_lsp(self, path: List[str]):
        label = self.label_generator.get_new_label()

        for router_index in range(len(path)):
            current_router = path[router_index]

            # First router, classify and push label
            if router_index == 0:
                self.routers[current_router].add_classification_rule(path[-1], label)
                next_hop = path[router_index + 1]
                self.routers[current_router].add_rule(incoming_label=label, outgoing_label=label, next_hop=next_hop)
            # Last router, pop label
            elif router_index == len(path) - 1:
                self.routers[current_router].add_rule(incoming_label=label, outgoing_label=None, next_hop=next_hop)
            # Intermediate routers, swap label
            else:
                next_hop = path[router_index + 1]
                self.routers[current_router].add_rule(incoming_label=label, outgoing_label=label, next_hop=next_hop)

        # Add demand information for the LSP to the DataFrame
        load = self.demands[(path[0], path[-1])]
        new_row = {'source': path[0], 'target': path[-1], 'label': label, 'path': path, 'load': load}
        new_row = pd.DataFrame([new_row])
        self.demand_dataframe = pd.concat([self.demand_dataframe, new_row], ignore_index=True)

    def remove_lsp(self, path: List[str], label: int):
        for router_index in range(len(path)):
            current_router = path[router_index]

            # First router, remove classification rule and forwarding rule
            if router_index == 0:
                self.routers[current_router].remove_classification_rule(path[-1])
                self.routers[current_router].remove_rule(incoming_label=label)
            # Last router, remove forwarding rule
            elif router_index == len(path) - 1:
                self.routers[current_router].remove_rule(incoming_label=label)
            # Intermediate routers, remove forwarding rule
            else:
                self.routers[current_router].remove_rule(incoming_label=label)

        # Remove path information for the LSP from the DataFrame
        self.demand_dataframe = self.demand_dataframe[self.demand_dataframe['label'] != label]

    def create_MPLS_network_topology(self, topology_data: Dict):

        # Add routers to the network
        for router_data in topology_data["network"]["routers"]:
            router_name = router_data["name"]
            self.add_router(router_name)

        # Add links between routers
        for link_data in topology_data["network"]["links"]:
            source_router = link_data["from_router"]
            target_router = link_data["to_router"]
            latency = link_data["latency"]
            capacity = link_data["bandwidth"]

            # Add edges to the graph with capacity attribute
            self.topology.add_edge(source_router, target_router, cost=latency, capacity=capacity)

            # Assume all links are bidirectional
            self.topology.add_edge(target_router, source_router, cost=latency, capacity=capacity)