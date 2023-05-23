import json
import time
from typing import Dict, List
import xml.etree.ElementTree as ET
import xml.dom.minidom as md

import pandas as pd

from classes.network import MLPS_Network
from algorithms.essence import essence
from classes.essence_state import EssenceState
import os
import time

def update_demands_and_paths(simulation_dir: str, network: MLPS_Network, essence_state: EssenceState, recorder, conf):
    if conf["algorithm"] == "essence_stateless":
        essence_state.current_population = []
    demands_loaded = False
    while not demands_loaded:
        try:
            with open("demands.json", "r") as file:
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
            with open("utilization.json", "r") as file:
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
    demands: Dict[(str,str), float] = import_demands(demands_data)
    network.demands.update(demands)

    # Update the demand dataframe
    for (src,tgt), load in demands.items():
        existing_row = network.demand_dataframe[(network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt)]

        if not existing_row.empty:
            network.demand_dataframe.loc[existing_row.index, 'load'] = load
        else:
            new_row = {'source': src, 'target': tgt, 'label': None, 'path': None, 'load': load}
            new_row = pd.DataFrame([new_row])
            network.demand_dataframe = pd.concat([network.demand_dataframe, new_row], ignore_index=True)

    # Calculate new paths
    paths = essence(network, essence_state, conf, start_time)

    # Create XML root element
    root = ET.Element('twoPhaseCommit')

    changes = []

    for path in paths.values():
        src, tgt = path[0], path[-1]
        existing_row = network.demand_dataframe[(network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt)]

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
                    out_label_elem.append(create_xml_element("op", attrib={"code": "swap", "value": str(out_label)}))
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
            network.install_lsp(path,0)

    # Write to xml file
    tree = ET.ElementTree(root)
    #tree.write(os.path.join(simulation_dir,'2-phase-commit.xml'))
    tree.write('2pc.xml')
    os.rename('2pc.xml', '2-phase-commit.xml')

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

def fbr_update_demands_and_paths(simulation_dir: str, network: MLPS_Network, essence_state: EssenceState, recorder, conf):
    if conf["algorithm"] == "essence_stateless":
        essence_state.current_population = []
    demands_loaded = False
    while not demands_loaded:
        try:
            with open("demands.json", "r") as file:
                content = file.read()
                demands_data = json.loads(content)
                demands_loaded = True
        except:
            print("Failed to load demands, retrying..")
            time.sleep(30)
    # Used to set the weight of congestion and stretch
    utilization_loaded = False

    while not utilization_loaded:
        try:
            with open("utilization.json", "r") as file:
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
            time.sleep(30)
    # Start timer
    start_time = time.time()
    demands: Dict[(str,str), float] = import_demands(demands_data)
    network.demands.update(demands)

    # Update the demand dataframe
    for (src,tgt), load in demands.items():
        existing_row = network.demand_dataframe[(network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt)]

        network.demand_dataframe.loc[existing_row.index, 'load'] = load

    # Calculate new paths
    paths = essence(network, essence_state, conf, start_time)

    # Create XML root element
    root = ET.Element('twoPhaseCommit')

    changes = []

    for path in paths.values():
        src, tgt = path[0], path[-1]
        existing_row = network.demand_dataframe[(network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt)]

        if list(existing_row['primary_path'].iloc[0]) != path:
            new_label = existing_row['label_backup_paths_dict'].iloc[0].get(tuple(path))
            network.demand_dataframe.loc[(network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt), 'label'] = new_label
            network.demand_dataframe.loc[(network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt), 'primary_path'] = network.demand_dataframe.loc[(network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt), 'primary_path'].apply(lambda x: path)
            changes.append(str(existing_row['source'].iloc[0]) + " -> " + str(existing_row['target'].iloc[0]))

            # initial router of the path
            reclassify_element = ET.SubElement(root, "reclassify")
            reclassify_element.set("router", src)

            label_element = ET.SubElement(reclassify_element, "label")
            label_element.text = str(new_label)

            destination_element = ET.SubElement(reclassify_element, "destination")
            destination_element.text = network.external_connections[tgt]["target"]

            source_element = ET.SubElement(reclassify_element, "source")
            source_element.text = network.external_connections[src]["source"]


            #network.(path)

    # Write to xml file
    tree = ET.ElementTree(root)
    #tree.write(os.path.join(simulation_dir,'2-phase-commit.xml'))
    tree.write('2pc.xml')
    os.rename('2pc.xml', '2-phase-commit.xml')

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
                new_demands[src,tgt] = sendinterval_to_load(demands[src][tgt])

    return new_demands

def sendinterval_to_load(send_interval):
    return int(64 / send_interval)