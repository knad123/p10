import networkx as nx
import pandas as pd
from typing import Any, Dict, List, Union, Tuple

from classes.label_generator import MPLS_Label_Generator
from classes.router import MPLS_Router

import xml.etree.ElementTree as ET


class MPLS_Network:
    def __init__(self, name: str = None, demands: Dict[str, str] = None):
        self.name = name
        self.topology = nx.DiGraph()
        self.routers = {}
        self.label_generator = MPLS_Label_Generator()
        self.demand_dict = {}
        self.demands = demands
        self.external_connections = {}
        self.failed_links_capacity = {}

    def add_router(self, name: str):
        router = MPLS_Router(name=name)
        self.routers[name] = router

    def install_lsp(self, path: List[str], priority: int, label = None):
        if label is None:
            label = self.label_generator.get_new_label()

        for router_index in range(len(path)):
            current_router = path[router_index]

            # First router, classify and push label
            if router_index == 0:
                self.routers[current_router].add_classification_rule(path[-1], label)
                next_hop = path[router_index + 1]
                self.routers[current_router].add_rule(incoming_label=label, outgoing_label=label, next_hop=next_hop,
                                                      priority=priority)
            # Last router, pop label
            elif router_index == len(path) - 1:
                self.routers[current_router].add_rule(incoming_label=label, outgoing_label=None, next_hop=next_hop,
                                                      priority=priority)
            # Intermediate routers, swap label
            else:
                next_hop = path[router_index + 1]
                self.routers[current_router].add_rule(incoming_label=label, outgoing_label=label, next_hop=next_hop,
                                                      priority=priority)

        # Add demand information for the LSP to the demand_dict
        load = self.demands[(path[0], path[-1])]
        new_row = {'source': path[0], 'target': path[-1], 'label': label, 'path': path, 'load': load,
                   'priority': priority}
        self.demand_dict[path[0], path[-1]] = new_row

    def install_fbr(self, paths_for_flow, algorithm="fbr", omnet_xml_root=None):
        labels = []
        src, tgt = paths_for_flow[0][0], paths_for_flow[0][-1]
        for i, path in enumerate(paths_for_flow):
            is_last_path = i == (len(paths_for_flow) - 1)
            label = self.label_generator.get_new_label()
            labels.append(label)
            if i == 0:
                first_label = label
                self.routers[path[0]].add_classification_rule(path[-1], label)

                # Omnet++ two phase commit details
                if omnet_xml_root is not None:
                    reclassify_element = ET.SubElement(omnet_xml_root, "reclassify")
                    reclassify_element.set("router", src)

                    label_element = ET.SubElement(reclassify_element, "label")
                    label_element.text = str(first_label)

                    destination_element = ET.SubElement(reclassify_element, "destination")
                    destination_element.text = self.external_connections[tgt]["target"]

                    source_element = ET.SubElement(reclassify_element, "source")
                    source_element.text = self.external_connections[src]["source"]
            for router_index, router_name in enumerate(path):
                # last router in path
                if router_index == len(path) - 1:
                    self.routers[router_name].add_rule(incoming_label=label, outgoing_label=None,
                                                          next_hop=router_name, priority=1)
                    # Omnet++ two phase commit details
                    if omnet_xml_root is not None:
                        omnet_xml_root.append(
                            router_rule_to_xml(router_name=router_name, priority=1, in_label=label,
                                               out_label=None, out_router=router_name))
                # intermediate router
                else:
                    next_hop = path[router_index + 1]
                    # add rule to forward by normal route
                    self.routers[router_name].add_rule(incoming_label=label, outgoing_label=label,
                                                          next_hop=next_hop,
                                                          priority=1)
                    # Omnet++ two phase commit details
                    if omnet_xml_root is not None:
                        omnet_xml_root.append(
                            router_rule_to_xml(router_name=router_name, priority=1, in_label=label,
                                               out_label=label, out_router=path[router_index + 1]))
                    if not is_last_path:
                        # add rule to swap to a higher label for backtracking
                        self.routers[router_name].add_rule(incoming_label=label, outgoing_label=label + 1,
                                                              next_hop=router_name,
                                                              priority=2)
                        # Omnet++ two phase commit details
                        if omnet_xml_root is not None:
                            omnet_xml_root.append(
                                router_rule_to_xml(router_name=router_name, priority=2, in_label=label,
                                                   out_label=label + 1, out_router=path[router_index + 1]))
                        if router_name not in paths_for_flow[i + 1]:
                            # add rule for backtracking with higher priority label
                            previous_router = path[router_index - 1]
                            self.routers[router_name].add_rule(incoming_label=label + 1, outgoing_label=label + 1,
                                                                  next_hop=previous_router,
                                                                  priority=1)
                            if omnet_xml_root is not None:
                                omnet_xml_root.append(router_rule_to_xml(router_name=router_name, priority=1, in_label=label+1, out_label=label+1, out_router=previous_router))
        path = paths_for_flow[0]
        # Add demand information for the LSP to the DataFrame
        load = self.demands[(path[0], path[-1])]
        label_backup_paths_zip = list(zip(labels, paths_for_flow))
        label_backup_paths_dict = {}
        for label, fbr_path in label_backup_paths_zip:
            label_backup_paths_dict[tuple(fbr_path)] = label
        new_row = {'source': path[0], 'target': path[-1], 'label': first_label, 'primary_path': paths_for_flow[0], 'load': load, 'label_backup_paths_dict': label_backup_paths_dict}
        self.demand_dict[path[0], path[-1]] = new_row
        # Omnet++ two phase commit details
        if omnet_xml_root is not None:
            return omnet_xml_root
    def install_split_path_essence(self, paths_for_flow, labels_per_flow=4, omnet_xml_root=None):
        split_label = self.label_generator.get_new_label()
        self.routers[paths_for_flow[0][0]].add_classification_rule(paths_for_flow[0][-1], split_label)
        src, tgt = paths_for_flow[0][0], paths_for_flow[0][-1]
        labels = []
        # Omnet++ two phase commit details
        if omnet_xml_root is not None:
            reclassify_element = ET.SubElement(omnet_xml_root, "reclassify")
            reclassify_element.set("router", src)

            label_element = ET.SubElement(reclassify_element, "label")
            label_element.text = str(split_label)

            destination_element = ET.SubElement(reclassify_element, "destination")
            destination_element.text = self.external_connections[tgt]["target"]

            source_element = ET.SubElement(reclassify_element, "source")
            source_element.text = self.external_connections[src]["source"]

        for path_idx, path in enumerate(paths_for_flow):
            is_last_path = path_idx == (len(paths_for_flow) - 1)
            if not is_last_path and path_idx < labels_per_flow:
                backtrack_label = self.label_generator.get_new_label()
                labels.append(backtrack_label)
            for router_index, router_name in enumerate(path):
                # last router in path
                if router_index == len(path) - 1:
                    self.routers[router_name].add_rule(incoming_label=split_label, outgoing_label=None,
                                                          next_hop=router_name, priority=1)
                    # Omnet++ two phase commit details
                    if omnet_xml_root is not None:
                        omnet_xml_root.append(
                            router_rule_to_xml(router_name=router_name, priority=1, in_label=split_label,
                                               out_label=None, out_router=router_name))
                # intermediate router in path
                else:
                    next_hop = path[router_index + 1]
                    # add rule to forward by normal route
                    self.routers[router_name].add_rule(incoming_label=split_label, outgoing_label=split_label,
                                                          next_hop=next_hop,
                                                          priority=1)
                    # Omnet++ two phase commit details
                    if omnet_xml_root is not None:
                        omnet_xml_root.append(
                            router_rule_to_xml(router_name=router_name, priority=1, in_label=split_label,
                                               out_label=split_label, out_router=next_hop))
                    if not is_last_path and path_idx < labels_per_flow:
                        # add rule to swap to a higher label for backtracking
                        self.routers[router_name].add_rule(incoming_label=split_label, outgoing_label=backtrack_label,
                                                              next_hop=router_name,
                                                              priority=2)
                        # Omnet++ two phase commit details
                        if omnet_xml_root is not None:
                            omnet_xml_root.append(
                                router_rule_to_xml(router_name=router_name, priority=2, in_label=split_label,
                                                   out_label=backtrack_label, out_router=router_name))
                        if router_name not in paths_for_flow[path_idx + 1]:
                            previous_router = path[router_index - 1]
                            self.routers[router_name].add_rule(incoming_label=backtrack_label, outgoing_label=backtrack_label,
                                                               next_hop=previous_router,
                                                               priority=1)
                            # Omnet++ two phase commit details
                            if omnet_xml_root is not None:
                                omnet_xml_root.append(
                                    router_rule_to_xml(router_name=router_name, priority=1, in_label=backtrack_label,
                                                       out_label=backtrack_label, out_router=previous_router))
                        elif router_name in paths_for_flow[path_idx + 1]:
                            # finds the next path and the next hop for that path
                            next_hop_index = paths_for_flow[path_idx + 1].index(router_name) + 1
                            next_hop = paths_for_flow[path_idx + 1][next_hop_index]
                            self.routers[router_name].add_rule(incoming_label=backtrack_label, outgoing_label=split_label,
                                                               next_hop=next_hop,
                                                               priority=1)
                            # Omnet++ two phase commit details
                            if omnet_xml_root is not None:
                                omnet_xml_root.append(
                                    router_rule_to_xml(router_name=router_name, priority=1, in_label=backtrack_label,
                                                       out_label=split_label, out_router=next_hop))

        path = paths_for_flow[0]
        # Add demand information for the LSP to the DataFrame
        load = self.demands[(path[0], path[-1])]
        label_backup_paths_zip = list(zip(labels, paths_for_flow))
        label_backup_paths_dict = {}
        for label, fbr_path in label_backup_paths_zip:
            label_backup_paths_dict[label] = fbr_path
        new_row = {'source': path[0], 'target': path[-1], 'label': split_label, 'split_path': paths_for_flow, 'load': load, 'label_backup_paths_dict': label_backup_paths_dict}
        self.demand_dict[path[0], path[-1]] = new_row

        # Omnet++ two phase commit details
        if omnet_xml_root is not None:
            return omnet_xml_root

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
        #self.demand_dataframe = self.demand_dataframe[self.demand_dataframe['label'] != label]

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
            self.topology.add_edge(source_router, target_router, latency=latency, capacity=capacity)

            # Assume all links are bidirectional
            self.topology.add_edge(target_router, source_router, latency=latency, capacity=capacity)

def create_xml_element(name, text=None, attrib=None):
    elem = ET.Element(name)
    if text:
        elem.text = str(text)
    if attrib:
        for key, value in attrib.items():
            elem.set(key, value)
    return elem

def router_rule_to_xml(router_name, priority, in_label, out_label, out_router):
    elem = create_xml_element("add", attrib={"router": router_name})
    elem.append(create_xml_element("priority", str(priority)))
    elem.append(create_xml_element("inLabel", str(in_label)))
    elem.append(create_xml_element("inRouter", "any"))
    out_router_elem = create_xml_element("outRouter", out_router)
    elem.append(out_router_elem)
    out_label_elem = ET.Element("outLabel")
    if router_name == out_router:
        out_label_elem.append(
            create_xml_element("op", attrib={"code": "swap", "value": str(out_label)}))
    else:
        out_label_elem.append(create_xml_element("op", attrib={"code": "pop"}))
    elem.append(out_label_elem)

    return elem