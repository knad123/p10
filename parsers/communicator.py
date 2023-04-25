import json
from typing import Dict, List
import xml.etree.ElementTree as ET

import pandas as pd

import classes.network
from algorithms.essence import essence


def update_demands_and_paths(demands_path: str, output_dir: str, network: classes.network.MLPS_Network):
    with open(demands_path, "r") as file:
        demands_data = json.load(file)

    demands: Dict[(str,str), float]  = import_demands(demands_data)
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
    paths = essence(network)

    # Create XML root element
    root = ET.Element('twoPhaseCommit')

    for path in paths.values():
        src, tgt = path[0], path[-1]
        existing_row = network.demand_dataframe[(network.demand_dataframe['source'] == src) & (network.demand_dataframe['target'] == tgt)]

        if existing_row.empty or list(existing_row['path'].iloc[0]) != path or True:
            old_label = existing_row['label'].iloc[0] if not existing_row.empty else None
            network.remove_lsp(list(existing_row['path'].iloc[0]), old_label)
            network.install_lsp(path)

            for router_index, router_name in enumerate(path):
                if router_index == 0:
                    operation = "add"
                    in_label = old_label
                    out_label = network.label_generator.get_new_label()
                else:
                    operation = "remove"
                    in_label = old_label

                # Create XML elements
                elem = create_xml_element(operation, attrib={"router": router_name})
                elem.append(create_xml_element("priority", str(0)))
                elem.append(create_xml_element("inLabel", str(in_label)))
                elem.append(create_xml_element("inRouter", "any" if router_index == 0 else path[router_index - 1]))

                if router_name == src:  # initial router of the path
                    reclassify_element = ET.SubElement(root, "reclassify")
                    reclassify_element.set("router", router_name)

                    label_element = ET.SubElement(reclassify_element, "label")
                    label_element.text = str(out_label)

                    destination_element = ET.SubElement(reclassify_element, "destination")
                    destination_element.text = network.external_connections[tgt]["target"]

                    source_element = ET.SubElement(reclassify_element, "source")
                    source_element.text = network.external_connections[src]["source"]

                if router_index != len(path) - 1 and operation != "remove":
                    out_router_elem = create_xml_element("outRouter", path[router_index + 1])
                    elem.append(out_router_elem)

                if operation == "add":
                    out_label_elem = ET.Element("outLabel")
                    out_label_elem.append(create_xml_element("op", attrib={"code": "pop"}))
                    out_label_elem.append(create_xml_element("op", attrib={"code": "swap", "value": str(out_label)}))
                    elem.append(out_label_elem)

                root.append(elem)

    # Write to xml file
    tree = ET.ElementTree(root)
    tree.write(f'{output_dir}/2-phase-commit.xml')

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
        for tgt in demands[src]:
            new_demands[src,tgt] = sendinterval_to_load(demands[src][tgt])

    return new_demands

def sendinterval_to_load(send_interval):
    return int(64 / send_interval)