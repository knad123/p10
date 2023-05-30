import json
import time
from typing import Dict, List
import xml.etree.ElementTree as ET
import xml.dom.minidom as md
import yaml

import pandas as pd

from classes.network import MPLS_Network
from algorithms.essence import essence
from algorithms.essence_split import essence_split
from algorithms.essence_big_flows import essence_big_flows
from algorithms.essence_weight_setting import essence_weight_setting
from classes.essence_state import EssenceState
import os
import time


def update_demands_and_paths(simulation_dir: str, network: MPLS_Network, essence_state: EssenceState, recorder, conf):
    if conf["algorithm"] == "essence_stateless":
        essence_state.current_population = []

    link_failures_loaded = False
    while not link_failures_loaded:
        try:
            with open(conf["link_failures_path"], "r") as file:
                link_failures_data = yaml.safe_load(file)
            if link_failures_data is None:
                link_failures_data = []
            #link_failures_data = json.load(content)
            link_failures_loaded = True
        except:
            print("Failed to load failed links, retrying..")
            time.sleep(5)
    demands_loaded = False
    while not demands_loaded:
        try:
            with open(conf["demand_path"], "r") as file:
                content = file.read()
            demands_data = json.loads(content)
            demands_loaded = True
        except:
            print("Failed to load demands, retrying..")
            time.sleep(5)
    # Used to set the weight of congestion and stretch
    utilization_loaded = False

    while not utilization_loaded:
        try:
            with open(conf["utilization_path"], "r") as file:
                utilizations_data = json.load(file)
            max_utilization = 0
            for key, value in utilizations_data.items():
                if key != 'timestamp':
                    for inner_key, inner_value in value.items():
                        if inner_value > max_utilization:
                            max_utilization = inner_value
            essence_state.congestion_weight = max_utilization
            utilization_loaded = True
        except:
            print("Failed to load utilization, retrying..")
            time.sleep(5)
    # Start timer
    start_time = time.time()
    demands: Dict[(str, str), float] = import_demands(demands_data)
    network.demands.update(demands)

    # Update the demand dataframe
    for (src, tgt), load in demands.items():
        network.demand_dict[src, tgt]['load'] = load

    # Fail links
    for (src,tgt) in link_failures_data:
        network.failed_links_capacity[src,tgt] = network.topology.edges[src,tgt]['capacity']
        network.topology.edges[src,tgt]['capacity'] = 1

    # Restore links
    for (src,tgt), capacity in network.failed_links_capacity.items():
        if (src,tgt) not in link_failures_data:
            network.topology.edges[src, tgt]['capacity'] = network.failed_links_capacity[src,tgt]



    changes = []

    if conf["algorithm"] in ["essence", "essence_precomputed", "essence_stateless", "essence_big_flows"]:
        # Create XML root element
        root = ET.Element('twoPhaseCommit')
        # Calculate new paths
        if conf["algorithm"] == "essence_big_flows":
            paths = essence_big_flows(network, essence_state, conf, start_time)
        else:
            paths = essence(network, essence_state, conf, start_time)
        for (src, tgt), path in paths.items():
            existing_row = network.demand_dict[src, tgt]

            if existing_row['primary_path'] != path:
                for path, label in network.demand_dict[src, tgt]['label_backup_paths_dict'].items():
                    # Remove old path
                    for router_index, router_name in enumerate(path):
                        for (priority, next_hop), rule in network.routers[router_name].forwarding_table[label].items():
                            operation = "remove"

                            # Create XML elements
                            elem = create_xml_element(operation, attrib={"router": router_name})
                            elem.append(create_xml_element("priority", str(rule['priority'])))
                            elem.append(create_xml_element("inLabel", str(label)))
                            elem.append(create_xml_element("inRouter", "any"))

                            root.append(elem)
                        network.routers[router_name].remove_rule(label)

                fbr_paths = [list(path)]
                for backup_path in existing_row['label_backup_paths_dict'].keys():
                    if backup_path != path:
                        fbr_paths.append(list(backup_path))
                root = network.install_fbr(fbr_paths, algorithm=conf['algorithm'], omnet_xml_root=root)
        # Write to xml file
        tree = ET.ElementTree(root)

        tree.write(conf["temp_2pc_path"])
        os.rename(conf["temp_2pc_path"], conf["2pc_path"])
    elif conf['algorithm'] == "essence_split":
        # Create XML root element
        root = ET.Element('twoPhaseCommit')
        # Calculate new paths
        split_paths = essence_split(network, essence_state, conf, start_time)
        for (src,tgt), paths in split_paths.items():

            if network.demand_dict[src, tgt]['split_path'] != paths:
                split_path_label = network.demand_dict[src, tgt]['label']
                for split_path in network.demand_dict[src, tgt]['split_path']:
                    for router_index, router_name in enumerate(split_path):
                        for (priority, next_hop), rule in network.routers[router_name].forwarding_table[split_path_label].items():
                            operation = "remove"

                            # Create XML elements
                            elem = create_xml_element(operation, attrib={"router": router_name})
                            elem.append(create_xml_element("priority", str(rule['priority'])))
                            elem.append(create_xml_element("inLabel", str(split_path_label)))
                            elem.append(create_xml_element("inRouter", "any"))

                            root.append(elem)

                for label, path in network.demand_dict[src, tgt]['label_backup_paths_dict'].items():
                    # Remove old path
                    for router_index, router_name in enumerate(path[:-1]):
                        for (priority, next_hop), rule in network.routers[router_name].forwarding_table[label].items():
                            operation = "remove"

                            # Create XML elements
                            elem = create_xml_element(operation, attrib={"router": router_name})
                            elem.append(create_xml_element("priority", str(rule['priority'])))
                            elem.append(create_xml_element("inLabel", str(label)))
                            elem.append(create_xml_element("inRouter", "any"))

                            root.append(elem)
                        network.routers[router_name].remove_rule(label)

            root = network.install_split_path_essence(paths, 1000, omnet_xml_root=root)
            # Write to xml file
            tree = ET.ElementTree(root)

            tree.write(conf["temp_2pc_path"])
            os.rename(conf["temp_2pc_path"], conf["2pc_path"])
    elif conf['algorithm'] == "essence_weight_setting":
        # Create XML root element
        root = ET.Element('dynamicWeights')
        weights = essence_weight_setting(network, essence_state, conf, start_time)
        for (src,tgt), weight in weights.items():
            elem = create_xml_element("weight", attrib={"src": src, "tgt": tgt, "weight": str(weight)})
            root.append(elem)

        # Write to xml file
        tree = ET.ElementTree(root)

        tree.write(os.path.join(conf["sync_dir"], "dynamic_weights-temp.xml"))
        os.rename(os.path.join(conf["sync_dir"], "dynamic_weights-temp.xml"), os.path.join(conf["sync_dir"], "dynamic_weights.xml"))
    elif 1000 == 22:
        for path in paths.values():
            src, tgt = path[0], path[-1]
            existing_row = network.demand_dataframe[
                (network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt)]

            if existing_row.empty or list(existing_row['path'].iloc[0]) != path:
                changes.append(str(existing_row['source'].iloc[0]) + " -> " + str(existing_row['target'].iloc[0]))
                old_label = existing_row['label'].iloc[0] if not existing_row.empty else None
                new_label = network.label_generator.get_new_label()

                # Add new path
                for router_index, router_name in enumerate(path):
                    operation = "add"
                    in_label = new_label
                    out_label = new_label

                    # Create XML elements
                    elem = create_xml_element(operation, attrib={"router": router_name})
                    elem.append(create_xml_element("priority", str(0)))
                    elem.append(create_xml_element("inLabel", str(in_label)))
                    elem.append(create_xml_element("inRouter", "any"))

                    if router_name == src:  # initial router of the path
                        reclassify_element = ET.SubElement(root, "reclassify")
                        reclassify_element.set("router", router_name)

                        label_element = ET.SubElement(reclassify_element, "label")
                        label_element.text = str(new_label)

                        destination_element = ET.SubElement(reclassify_element, "destination")
                        destination_element.text = network.external_connections[tgt]["target"]

                        source_element = ET.SubElement(reclassify_element, "source")
                        source_element.text = network.external_connections[src]["source"]

                    if router_index != (len(path) - 1):
                        out_router_elem = create_xml_element("outRouter", path[router_index + 1])
                        elem.append(out_router_elem)
                    else:
                        out_router_elem = create_xml_element("outRouter", router_name)
                        elem.append(out_router_elem)

                    out_label_elem = ET.Element("outLabel")
                    if router_index != (len(path) - 1):
                        out_label_elem.append(
                            create_xml_element("op", attrib={"code": "swap", "value": str(out_label)}))
                    else:
                        out_label_elem.append(create_xml_element("op", attrib={"code": "pop"}))
                    elem.append(out_label_elem)

                    root.append(elem)

                # Remove old path
                for router_index, router_name in enumerate(list(existing_row['path'].iloc[0])):
                    operation = "remove"

                    # Create XML elements
                    elem = create_xml_element(operation, attrib={"router": router_name})
                    elem.append(create_xml_element("priority", str(0)))
                    elem.append(create_xml_element("inLabel", str(old_label)))
                    elem.append(create_xml_element("inRouter", "any"))

                    root.append(elem)

                network.remove_lsp(list(existing_row['path'].iloc[0]), old_label)
                network.install_lsp(path, 0)

    '''
    # Print 2 phase commit file
    xml_string = ET.tostring(tree.getroot(), encoding='utf-8', method='xml')
    doc = md.parseString(xml_string)
    pretty_xml = doc.toprettyxml(indent='  ')
    print(pretty_xml)
    '''
    # Add the number of changes to the recorder
    recorder.changes.append((len(changes)))

    return network


def create_xml_element(name, text=None, attrib=None):
    elem = ET.Element(name)
    if text:
        elem.text = str(text)
    if attrib:
        for key, value in attrib.items():
            elem.set(key, value)
    return elem


def import_demands(demands: Dict[str, Dict[str, float]]):
    new_demands = {}
    for src in demands.keys():
        if src != "timestamp":
            for tgt in demands[src]:
                new_demands[src, tgt] = sendinterval_to_load(demands[src][tgt])

    return new_demands


def sendinterval_to_load(send_interval):
    return int(64 / send_interval)
