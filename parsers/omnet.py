# import jsonschema
import datetime
import json
import os
import random
import xml.etree.ElementTree as ET
import xml.dom.minidom as md
import time
from os import path
from typing import Dict, List, Tuple

import networkx

import classes.network
import math
from os import path

def to_omnetpp(network: classes.network.MPLS_Network, temporal_demands: Dict[Tuple[str, str], List[Tuple[float,str,str]]], conf, name='default', output_dir='./omnet_files/default', scaler=1, packet_size=64,
               zero_latency=False, package_name="inet.zoo_topology", algorithm="none", latency_scaler=1.0, essence_state=None):
    """
    Generates all files for OMNeT++.
    """

    if not path.exists(output_dir):
        os.makedirs(output_dir)

    export_flows = build_flows_for_export(network, conf)

    # Dictionary containing interfaces for connections
    interface_dict = {}
    for source, adjacent_nodes in network.topology.adj.items():
        interface_idx = 0
        if source not in interface_dict:
            interface_dict[source] = {}
        for target, edge_data in adjacent_nodes.items():
            interface_dict[source][target] = interface_idx
            interface_idx += 1

    with open(f'{output_dir}/{name}.ned', mode='w') as f:
        link_to_ppp_dict = to_omnetpp_ned(network, export_flows, conf=conf, interface_dict=interface_dict, name=name, file=f, bandwidth_divisor=scaler,
                                          zero_latency=zero_latency, package_name=package_name, algorithm=conf['algorithm_and_parameters'])

    """
    with open("confs/zoo_" + network.name + "/failure_chunks/0.yml", 'r') as f:
        failed_set_chunk = yaml.safe_load(f)
    
    if not path.exists(output_dir + "/failure_scenarios"):
        os.makedirs(output_dir + "/failure_scenarios")

    for scenario in range(1, len(failed_set_chunk)):
        with open(f'{output_dir}/failure_scenarios/scenario_{scenario}.xml', mode='w') as f:
            network.to_omnetpp_scenario(file=f, failure_scenario=failed_set_chunk[scenario],
                                        link_to_ppp=link_to_ppp_dict)
    """

    failure_scenarios = conf["failure_scenarios"]
    if failure_scenarios > 0:
        scenario_dir = os.path.join(output_dir, "failure_scenarios")
        os.makedirs(scenario_dir, exist_ok=True)
        if conf["short_experiment"]:
            generate_scenarios(failure_scenarios, 14400 * conf["time_scale"], scenario_dir, link_to_ppp_dict, conf,
                               network)
        else:
            generate_scenarios(failure_scenarios, 86400*conf["time_scale"], scenario_dir, link_to_ppp_dict, conf, network)


    with open(f'{output_dir}/omnetpp.ini', mode="w") as f:
        to_omnetpp_ini(conf=conf, network=network, export_flows=export_flows, temporal_demands=temporal_demands, name=name, file=f,
                               packet_size=packet_size, send_interval_multiplier=scaler, zero_latency=zero_latency,
                               algorithm=conf['algorithm_and_parameters'])

    if not path.exists(output_dir + "/lib_files"):
        os.makedirs(output_dir + "/lib_files")
    if not path.exists(output_dir + "/classification_files"):
        os.makedirs(output_dir + "/classification_files")

    to_omnetpp_lib(network, interface_dict, output_dir + "/lib_files")
    to_omnetpp_classification(network, export_flows, output_dir + "/classification_files", conf, essence_state)

    with open(f'{output_dir}/network_topology.json', mode='w') as f:
        to_omnetpp_network_topology_json(network, f)

    if conf['algorithm'] in ["essence_weight_setting", "essence_learn_paths_learn_weights"]:
        # Create XML root element
        root = ET.Element('dynamicWeights')
        for (src,tgt), weight in essence_state.link_weights.items():
            elem = create_xml_element("weight", attrib={"src": src, "tgt": tgt, "weight": str(weight)})
            root.append(elem)
        tree = ET.ElementTree(root)
        #print(os.path.join(conf["sync_dir"], "dynamic_weights-initial.xml"))
        tree.write(os.path.join(conf["sim_dir"], "dynamic_weights-initial-temp.xml"))
        os.rename(os.path.join(conf["sim_dir"], "dynamic_weights-initial-temp.xml"), os.path.join(conf["sim_dir"], "dynamic_weights-initial.xml"))

    if conf['algorithm'] == "essence_split_multiple_labels":
        # Create XML root element
        root = ET.Element('fectables')
        for router_name, tables in network.routers.items():
            fectable = ET.SubElement(root, 'fectable')
            fectable.set('router', router_name)
            for (src,tgt), weight in essence_state.path_weights.items():
                if src == router_name:
                    fecentry = ET.SubElement(fectable, 'fecentry')
                    current_weight, source_host, target_host, id = network.routers[router_name].classification_table[
                        src, tgt, network.demand_dict[src,tgt]['label']]
                    ET.SubElement(fecentry, 'id').text = str(id)
                    ET.SubElement(fecentry, 'destination').text = str(target_host)
                    ET.SubElement(fecentry, 'source').text = str(source_host)
                    zip_weights_paths_and_labels = list(zip(network.demand_dict[src,tgt]['label_backup_paths_zip'], weight))
                    for (label, fbr_path), updated_weight in zip_weights_paths_and_labels:
                        weighted_label = ET.SubElement(fecentry, 'weightedLabel')
                        ET.SubElement(weighted_label, 'label').text = str(label)
                        ET.SubElement(weighted_label, 'weight').text = str(updated_weight)
        tree = ET.ElementTree(root)

        #print(os.path.join(conf["sync_dir"], "dynamic_weights-initial.xml"))
        tree.write(os.path.join(conf["sim_dir"], "dynamic_weights-initial-temp.xml"))
        os.rename(os.path.join(conf["sim_dir"], "dynamic_weights-initial-temp.xml"),
                  os.path.join(conf["sim_dir"], "dynamic_weights-initial.xml"))

def to_omnetpp_network_topology_json(network, file):
    topology = {}
    for (src,tgt) in network.topology.edges:
        if src not in topology:
            topology[src] = {}
        topology[src][tgt] = network.topology.edges[(src,tgt)]['capacity']
    json_object = json.dumps(topology, indent=2)
    file.write(json_object)




def to_omnetpp_ned(network, export_flows, conf, name, interface_dict, file, bandwidth_divisor=1, zero_latency=False,
                   package_name="inet.zoo_topology", algorithm="none"):
    # Values between the routers, if not included in the edge data
    DEFAULT_BANDWIDTH = 1048576  # kbps = 1 Gbps
    # Values from the hosts to the routers
    DEFAULT_HOST_BANDWIDTH = 600  # kbps
    DEFAULT_HOST_LATENCY = 10  # ms

    # Link -> pppgate dictionary
    link_to_ppp = dict()
    # from service import MPLS_Service
    file.write(f"package {package_name}.{name}.{algorithm};\n")
    file.write("import inet.common.scenario.ScenarioManager;\n")
    file.write("import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;\n")
    file.write("import inet.node.inet.StandardHost;\n")
    file.write("import inet.node.mpls.MplsRouter;\n")  # own, modified router class
    if conf["algorithm"] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "essence_weight_setting", "essence_split_multiple_labels", "GAOSPF", "essence_learn_paths_learn_weights"]:
        file.write("import inet.p10.MeasureWriter;\n")
    if conf["algorithm"] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "GAOSPF", "essence_learn_paths_learn_weights"]:
        file.write(f"import inet.p10.TwoPhaseCommit;\n")
    if conf["algorithm"] in ["essence_weight_setting", "essence_split_multiple_labels", "essence_learn_paths_learn_weights"]:
        file.write(f"import inet.p10.DynamicWeights;\n")
    file.write("\n")
    file.write(f"network {name}_{algorithm}{{\n")

    # Global statistic
    file.write("    parameters:\n")
    file.write(f"        int timeBetweenRecordings = {conf['utilization_recording_interval']};\n")
    file.write(f'        int recordingSampleDuration = {conf["recording_sample_duration"]};\n')
    file.write \
        ('        @statistic[packetsCreatedVector](source="emitsPerDuration(packetSentUDP)"; record=vector; interpolationmode="none");\n')
    file.write \
        ('        @statistic[packetsDeliveredVector](source="emitsPerDuration(packetReceivedUDP)"; record=vector; interpolationmode="none");\n')
    file.write \
        ('        @statistic[packetDropReasonIsQueueOverflowVector](source="emitsPerDuration(packetDropReasonIsQueueOverflow(packetDropped))"; record=vector; interpolationmode="none");\n')
    file.write \
        ('        @statistic[packetDropReasonIsNoRouteFoundVector](source="emitsPerDuration(packetDropReasonIsNoRouteFound(packetDropped))"; record=vector; interpolationmode="none");\n')
    file.write('        @statistic[packetsCreatedCount](source="packetSentUDP"; record=count;);\n')
    file.write('        @statistic[packetsDeliveredCount](source="packetReceivedUDP"; record=count;);\n')
    file.write \
        ('        @statistic[packetDropReasonIsQueueOverflowCount](source="packetDropReasonIsQueueOverflow(packetDropped)"; record=count;);\n')
    file.write \
        ('        @statistic[packetDropReasonIsNoRouteFoundCount](source="packetDropReasonIsNoRouteFound(packetDropped)"; record=count;);\n')
    file.write('\n')
    file.write("    submodules:\n")
    file.write('        configurator: Ipv4NetworkConfigurator;\n')
    if conf["algorithm"] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "essence_weight_setting", "essence_split_multiple_labels", "GAOSPF", "essence_learn_paths_learn_weights"]:
        file.write(f"        measureWriter: MeasureWriter{{writeInterval = {conf['write_interval']}s;}}\n")
    if conf["algorithm"] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "GAOSPF", "essence_learn_paths_learn_weights"]:
        file.write(f"        twoPhaseCommit: TwoPhaseCommit{{updateInterval = {conf['update_interval']}s;}}\n")
    if conf["algorithm"] in ["essence_weight_setting", "essence_split_multiple_labels", "essence_learn_paths_learn_weights"]:
        file.write(f"        dynamicWeights: DynamicWeights{{updateInterval = {conf['update_interval']}s;}}\n")
    for router_name, router in network.routers.items():

        # calculate number of flows at this router
        nr_flows_from_router = 1 if sum(entry['ingress'] == router_name for entry in export_flows) >= 1 else 0
        nr_flows_to_router = 1 if sum(entry['egress'] == router_name for entry in export_flows) >= 1 else 0

        # Create router in NED file.
        file.write(f"        {router_name}: MplsRouter " + "{\n")
        file.write("            parameters:\n")
        file.write("                peers = \"" + " ".join([f"ppp{i}" for i in range(len(interface_dict[router_name]))]) + "\";\n")

        # outside interfaces are added to the total list of ppp interfaces
        # TODO: Why?
        """
        for interface in router.get_interfaces(outside_interfaces = True):
            router.interface_ids[interface] = id
            id += 1
        """

        file.write("            gates:\n")
        # + connections to source and target nodes
        file.write(f"                pppg[{len(interface_dict[router_name]) + nr_flows_from_router + nr_flows_to_router}];\n")
        file.write("        }\n")

        ### TODO: What about this section? ###
        """
        host_id = 0
        service_client = router.get_client(MPLS_Service)
        if service_client:
            for vpn_name, vpn in service_client.services.items():
                for ce in vpn["ces"]:
                    pass
        from rsvpte import ProcRSVPTE
        rsvp_client = router.get_client(ProcRSVPTE)
        if rsvp_client:
            for host in rsvp_client.headended_lsps:
                pass
                file.write(f"        host{host_id}: StandardHost;\n")
                host_id += 1
        """
        ### TODO: End -- What about this section? ###

        # External edges (to hosts)
        # Assign interface ids
        host_interface_id = 0
        for flow in export_flows:
            if flow['ingress'] == router_name:
                flow['in_interface'] = f"{len(interface_dict[router_name]) + host_interface_id}"
                host_interface_id = host_interface_id + 1
            if flow['egress'] == router_name:
                flow['out_interface'] = f"{len(interface_dict[router_name]) + host_interface_id}"
                host_interface_id = host_interface_id + 1

    # Add StandardHosts for all flows
    added_hosts = []
    for flow in export_flows:
        if flow['source_host'] not in added_hosts:
            file.write(
                f"""        {flow['source_host']}: StandardHost {{
            gates:
                pppg[1];
        }}\n""")
            added_hosts.append(flow['source_host'])
        # Add target host
        if flow['target_host'] not in added_hosts:
            file.write(
                f"""        {flow['target_host']}: StandardHost {{
            gates:
                pppg[1];
        }}\n""")
            added_hosts.append(flow['target_host'])

    file.write("        scenarioManager: ScenarioManager;")

    file.write("\tconnections:\n")

    # Small hack :)
    undirected_graph = network.topology.to_undirected()

    # Internal edges (router to router)
    for edge in undirected_graph.edges:
        # Either use default values for bandwidth and latency or use the edge values if present
        data = network.topology.get_edge_data(edge[0], edge[1])
        # We multiply bandwidth by 8 to convert to bits
        bandwidth = data['capacity'] * 8 if 'capacity' in data else DEFAULT_BANDWIDTH
        latency = data['latency'] if ('latency' in data and not zero_latency) else 0

        # Added for scenario manager
        link_to_ppp[(edge[0], edge[1])] = interface_dict[edge[0]][edge[1]]
        link_to_ppp[(edge[1], edge[0])] = interface_dict[edge[1]][edge[0]]

        file.write(f"        {edge[0]}.pppg[" + str(interface_dict[edge[0]][edge[1]]) + "] <--> ")
        file.write(
            f'{edge[0]}___{edge[1]}: {{enableUtilization = true; delay = {latency}ms; datarate = {bandwidth / bandwidth_divisor}bps; @statistic[utilization](source="utilizationMovingAverage(channelBusy)"; record=max,vector,last; interpolationmode="none"); }} <--> ')
        file.write(f"{edge[1]}.pppg[" + str(interface_dict[edge[1]][edge[0]]) + "];\n")

    # Edges to source and target nodes.
    '''
    for flow in network.export_flows:
        # TODO: Eventually use other values ...
        file.write(
            f"""        {flow['ingress']}.pppg[{flow['in_interface']}] <--> {{ delay = {DEFAULT_HOST_LATENCY}ms; datarate = {DEFAULT_HOST_BANDWIDTH}kbps; }} <--> {flow['source_host']}.pppg[0];\n""")
        file.write(
            f"""        {flow['egress']}.pppg[{flow['out_interface']}] <--> {{ delay = {DEFAULT_HOST_LATENCY}ms; datarate = {DEFAULT_HOST_BANDWIDTH}kbps; }} <--> {flow['target_host']}.pppg[0];\n""")
    '''
    router_ids = {}
    for router_name, router in network.routers.items():
        router_ids[router_name] = len(interface_dict[router_name])

    added_connections = []
    for flow in export_flows:
        if flow['source_host'] not in added_connections:
            source_host_id = router_ids[flow['ingress']]
            router_ids[flow['ingress']] += 1
            file.write \
                (f"""        {flow['ingress']}.pppg[{source_host_id}] <--> {{ delay = 0ms; datarate = 100Gbps; }} <--> {flow['source_host']}.pppg[0];\n""")
            added_connections.append(flow['source_host'])
        if flow['target_host'] not in added_connections:
            target_host_id = router_ids[flow['egress']]
            router_ids[flow['egress']] += 1
            file.write \
                (f"""        {flow['egress']}.pppg[{target_host_id}] <--> {{ delay = 0ms; datarate = 100Gbps; }} <--> {flow['target_host']}.pppg[0];\n""")
            added_connections.append(flow['target_host'])

    file.write("}\n")
    return link_to_ppp


def to_omnetpp_ini(conf, network, export_flows, temporal_demands: Dict[Tuple[str, str], List[Tuple[float,str,str]]], name, file, packet_size=64,
                   send_interval_multiplier=1, zero_latency=False, algorithm="none"):
    UTILIZATION_SAMPLE_INTERVAL = 5  # seconds
    file.write("[General]\n")
    if conf["algorithm"] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "essence_weight_setting", "essence_split_multiple_labels", "GAOSPF", "essence_learn_paths_learn_weights"]:
        file.write(f'**.measureWriter.demandPath = "{os.path.join(conf["sync_dir"], "demands-General.json")}"\n')
        file.write(f'**.measureWriter.utilizationPath = "{os.path.join(conf["sync_dir"], "utilization-General.json")}"\n')
        file.write(f'**.measureWriter.linkFailuresPath = "{os.path.join(conf["sync_dir"], "link_failures-General.json")}"\n')
    if conf["algorithm"] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "GAOSPF", "essence_learn_paths_learn_weights"]:
        file.write(f'**.twoPhaseCommit.updatePath = "{os.path.join(conf["sync_dir"], "2-phase-commit-General.xml")}"\n')
    if conf["algorithm"] in ["essence_weight_setting", "essence_split_multiple_labels", "essence_learn_paths_learn_weights"]:
        file.write(f'**.dynamicWeights.updatePath = "{os.path.join(conf["sync_dir"], "dynamic_weights-General.xml")}"\n')
        file.write(f'**.dynamicWeights.initialPath = \"dynamic_weights-initial.xml\"\n')
    for router in network.routers.keys():
        if conf["algorithm"] in ["split_shortest_path", "essence_split"]:
            file.write(f'**.{router}.libTable.splittingProtocol = "capacity"\n')
        if conf["algorithm"] in ["essence_weight_setting", "essence_learn_paths_learn_weights"]:
            file.write(f'**.{router}.libTable.splittingProtocol = "dynamic"\n')
        if conf["algorithm"] in ["GAOSPF"]:
            file.write(f'**.{router}.libTable.splittingProtocol = "ecmp"\n')
    file.write(f"network = {name}_{algorithm}\n")
    file.write(f"**.cmdenv-log-level = OFF\n")
    file.write(f"**.utilization.statistic-recording = true\n")
    file.write(f"**.packetsCreatedCount.statistic-recording = true\n")
    file.write(f"**.packetsDeliveredCount.statistic-recording = true\n")
    file.write(f"**.packetDropReasonIsQueueOverflowCount.statistic-recording = true\n")
    file.write(f"**.packetDropReasonIsNoRouteFoundCount.statistic-recording = true\n")
    file.write(f"**.packetsCreatedVector.statistic-recording = true\n")
    file.write(f"**.packetsDeliveredVector.statistic-recording = true\n")
    file.write(f"**.packetDropReasonIsQueueOverflowVector.statistic-recording = true\n")
    file.write(f"**.packetDropReasonIsNoRouteFoundVector.statistic-recording = true\n")
    file.write(f"**.statistic-recording = false\n")
    for router_name, router in network.routers.items():
        # file.write(f"**.{router_name}.classifier.config = xmldoc(\"{router_name}_fec.xml\")\n")
        file.write(f"**.{router_name}.libTable.config = xmldoc(\"lib_files/{router_name}_lib.xml\")\n")
    file.write("**.rsvp.helloInterval = 0s\n")
    file.write("**.rsvp.helloTimeout = 0s\n")
    file.write("**.ppp[*].queue.typename = \"DropTailQueue\"\n")
    file.write("**.ppp[*].queue.packetCapacity = 10\n")  # This value is taken from example files in INET.
    # file.write("**.scenarioManager.script = xmldoc(\"scenario.xml\")\n")
    file.write("\n")
    file.write(f"warmup-period = 0s\n")
    if conf["short_experiment"]:
        file.write(f"sim-time-limit = {14400 * conf['time_scale']}s\n")
    else:
        file.write(f"sim-time-limit = {86400 * conf['time_scale']}s\n")
    # Add classification files
    for router_name, router in network.routers.items():
        file.write \
            (f"**.{router_name}.classifier.config = xmldoc(\"classification_files/{router_name}_classification.xml\")\n")

    send_intervals = {}
    send_interval_start_times = {}

    for (src, tgt), demands in temporal_demands.items():
        for d in demands:
            load = int(d[0]) * conf["demand_scaler"]
            if conf["short_experiment"]:
                send_interval = 14400
            else:
                send_interval = 86400
            if load > 0:
                send_interval = (send_interval_multiplier * (1 / (load / packet_size)))
            start_time_unformatted = d[1]
            x = time.strptime(start_time_unformatted, '%H:%M')
            send_interval_start_time = int(datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min).total_seconds()) * conf["time_scale"]
            if (src, tgt) not in send_intervals:
                send_intervals[(src, tgt)] = f"{send_interval}"
                send_interval_start_times[(src, tgt)] = f"{send_interval_start_time}"
            else:
                send_intervals[(src, tgt)] += f" {send_interval}"
                send_interval_start_times[(src, tgt)] += f" {send_interval_start_time}"

    source_apps = {}
    flow_idx = 0  # Used to find the simulation time limit
    flow_tracker = {}
    for flow in export_flows:
        if (flow['ingress'], flow['egress']) in flow_tracker:
            continue
        else:
            flow_tracker[flow['ingress'], flow['egress']] = None
        flow_idx += 1
        ingress = flow['ingress']
        egress = flow['egress']
        entry = {'typename': 'UdpBasicApp', 'localPort': flow_idx, 'destPort': flow_idx,
                 'messageLength': f"{packet_size} bytes",
                 'sendInterval': "1s",
                 'destAddresses': flow['target_host'],
                 'source_host': flow['source_host'],
                 'send_intervals': send_intervals[(ingress, egress)],
                 'send_interval_start_times': send_interval_start_times[(ingress, egress)]}
        if ingress not in source_apps:
            source_apps[ingress] = [entry]
        else:
            source_apps[ingress].append(entry)

    for ingress, apps in source_apps.items():
        file.write(f'''**.{apps[0]['source_host']}.numApps = {len(apps)}\n''')
        for i, app in enumerate(apps):
            file.write(f'''**.{app['source_host']}.app[{i}].typename = "{app['typename']}"\n''')
            file.write(f'''**.{app['source_host']}.app[{i}].localPort = {app['localPort']}\n''')
            file.write(f'''**.{app['source_host']}.app[{i}].destPort = {app['destPort']}\n''')
            file.write(f'''**.{app['source_host']}.app[{i}].messageLength = {app['messageLength']}\n''')
            file.write(f'''**.{app['source_host']}.app[{i}].sendInterval = {app['sendInterval']}\n''')
            file.write(f'''**.{app['source_host']}.app[{i}].destAddresses = "{app['destAddresses']}"\n''')
            file.write(f'''**.{app['source_host']}.app[{i}].sendIntervals = "{app['send_intervals']}"\n''')
            file.write(f'''**.{app['source_host']}.app[{i}].sendIntervalStartTimes = "{app['send_interval_start_times']}"\n''')
        file.write("\n")

    # Add applications at target nodes.
    # Group export flows by egress/target host
    flows_by_target = {}
    for source, apps in source_apps.items():
        for app in apps:
            target = app['destAddresses']
            if target not in flows_by_target:
                flows_by_target[target] = []
            flows_by_target[target].append(app)

    # Add applications at target nodes
    for target, apps in flows_by_target.items():
        file.write(f'''**.{target}.numApps = {len(apps)}\n''')
        for i, app in enumerate(apps):
            file.write(f'''**.{target}.app[{i}].typename = "UdpSinkApp"\n''')
            file.write(f'''**.{target}.app[{i}].io.localPort = {app['destPort']}\n''')
        file.write("\n")

    for scenario in range(conf["failure_scenarios"]):
        file.write(f'[Config scenario_{scenario}]\n')
        file.write(f'**.scenarioManager.script = xmldoc("failure_scenarios/scenario_{scenario}.xml")\n')
        if conf["algorithm"] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "essence_weight_setting", "essence_split_multiple_labels", "GAOSPF", "essence_learn_paths_learn_weights"]:
            file.write(f'**.measureWriter.demandPath = "{os.path.join(conf["sync_dir"], f"demands-scenario_{scenario}.json")}"\n')
            file.write(
                f'**.measureWriter.utilizationPath = "{os.path.join(conf["sync_dir"], f"utilization-scenario_{scenario}.json")}"\n')
            file.write(
                f'**.measureWriter.linkFailuresPath = "{os.path.join(conf["sync_dir"], f"link_failures-scenario_{scenario}.json")}"\n')
        if conf["algorithm"] in ['essence', 'essence_stateless', 'essence_split', 'essence_big_flows', "GAOSPF", "essence_learn_paths_learn_weights"]:
            file.write(f'**.twoPhaseCommit.updatePath = "{os.path.join(conf["sync_dir"], f"2-phase-commit-scenario_{scenario}.xml")}"\n')
        if conf["algorithm"] in ["essence_weight_setting", "essence_split_multiple_labels", "essence_learn_paths_learn_weights"]:
            file.write(f'**.dynamicWeights.updatePath = \"dynamic_weights-scenario_{scenario}.xml\"\n')
        file.write("\n")


def to_omnetpp_lib(network, interface_dict, export_dir):
    for router_name, router in network.routers.items():
        table_xml = to_omnetpp_lib_xml(router, interface_dict)
        ET.indent(table_xml)  # NOTE: Requires >= Python 3.9
        ET.ElementTree(table_xml).write(f"{export_dir}/{router_name}_lib.xml")

def build_flows_for_export(network, conf):
    """
    Returns an array with the data of all flows (as a dictionary).
    """
    flows = {}

    # Initialize external_connections dictionary in the network
    network.external_connections = {}

    for index, row in network.demand_dict.items():
        source = row['source']
        target = row['target']
        label = row['label']
        load = row['load']
        if conf["algorithm"] == "essence_split_multiple_labels":
            split_labels = row['label_backup_paths_zip']

        if source not in flows:
            flows[source] = {}
        if conf["algorithm"] == "essence_split_multiple_labels":
            for (label, path) in split_labels:
                flows[source][label] = ([source], [target], load)
        else:
            flows[source][label] = ([source], [target], load)

    export_flows = []
    i = 0
    j = 0
    source_nums = {}
    target_nums = {}
    for router_name, lbl_items in flows.items():
        if router_name not in source_nums:
            j += 1
            source_nums[router_name] = j
        for in_label, tup in lbl_items.items():
            good_sources, good_targets, load = tup
            # TODO: Ask whether to add new clients for every good_targets entry
            for target in good_targets:
                if target not in target_nums:
                    i = i + 1
                    target_nums[target] = i
                export_flows.append({
                    'in_label': in_label,
                    'ingress': router_name,
                    'egress': target,
                    'in_interface': None,
                    'out_interface': None,
                    'source_host': f"host{source_nums[router_name]}",
                    'target_host': f'target{target_nums[target]}',
                    'load': load,
                })

    # Add external_connections for the source and target
    for router in network.routers:
        if router in source_nums and router in target_nums:
            network.external_connections[router] = {
                "source": f"host{source_nums[router]}",
                "target": f"target{target_nums[router]}"
            }
        elif router in source_nums:
            network.external_connections[router] = {
                "source": f"host{source_nums[router]}"
            }
        elif router in target_nums:
            network.external_connections[router] = {
                "target": f"target{target_nums[router]}"
            }

    return export_flows


def to_omnetpp_classification(network, export_flows, export_dir, conf, essence_state):
    for router_name in network.routers.keys():
        if conf["algorithm"] == "essence_split_multiple_labels":
            network.routers[router_name].classification_table = {}

        flows_at_router = list(filter(lambda entry: entry['ingress'] == router_name, export_flows))

        id = 0
        table_xml = ET.Element("fectable")
        id_dict = {}
        fecs = []
        for entry in flows_at_router:
            source_target_pair = (entry['ingress'], entry['egress'])


            # Check if the source-target pair already has an assigned ID
            if source_target_pair in id_dict:
                assigned_id = id_dict[source_target_pair]
            else:
                assigned_id = id
                id_dict[source_target_pair] = id
                id += 1



            if conf["algorithm"] == "essence_split_multiple_labels":
                network.routers[router_name].add_classification_rule_for_weight_split_essence(source=entry['ingress'], target=entry['egress'], id=assigned_id, source_host=entry['source_host'], target_host=entry['target_host'], incoming_label=entry['in_label'])

            if source_target_pair in fecs:
                continue

            fecs.append(source_target_pair)

            entry_xml = ET.SubElement(table_xml, "fecentry")
            ET.SubElement(entry_xml, "id").text = str(assigned_id)
            ET.SubElement(entry_xml, "label").text = str(entry['in_label'])
            ET.SubElement(entry_xml, "destination").text = entry['target_host']
            ET.SubElement(entry_xml, "source").text = entry['source_host']

        ET.indent(table_xml)  # NOTE: Requires >= Python 3.9
        ET.ElementTree(table_xml).write(f"{export_dir}/{router_name}_classification.xml")

def to_omnetpp_lib_xml(router, interface_dict):
    table_xml = ET.Element("libtable")
    for label, row in router.forwarding_table.items():
        for (priority, next_hop), entry in row.items():
            entry_xml = ET.SubElement(table_xml, "libentry")
            ET.SubElement(entry_xml, "priority").text = str(entry['priority'])
            ET.SubElement(entry_xml, "inLabel").text = str(label)
            ET.SubElement(entry_xml, "inInterface").text = "any"
            if (entry["next_hop"] == router.name):
                ET.SubElement(entry_xml, "outInterface").text = "mlo0"  # custom loopback interface
            else:
                ET.SubElement(entry_xml, "outInterface").text = "ppp" + str(interface_dict[router.name][entry["next_hop"]])
            ops = ET.SubElement(entry_xml, "outLabel")
            op_code = entry["operation"]
            op_label = entry["outgoing_label"]
            if op_code == 'pop':
                # pop should not contain a value attribute (violates an assertion in DEBUG mode)
                ET.SubElement(ops, "op", code=op_code)
            else:
                ET.SubElement(ops, "op", code=op_code, value=str(op_label))
    return table_xml

def to_omnetpp_scenario(file, link_to_ppp, conf, network_topology, failed_links):
    # failed_links is a list of tuples in the form of (timestamp, [(src,tgt)]), eg (10, [(copenhagen, berlin), (paris, milano)]) denoting two links that disconnect at 10 seconds
    file.write('<?xml version="1.0"?>\n')
    file.write("<scenario>\n")

    # If using link failues
    if failed_links != []:
        for (timestamp, link_list, downtime) in failed_links:
            file.write(f'<at t="{timestamp}s">\n')
            for (src, tgt) in link_list:
                file.write(f'	<disconnect src-module="{src}" dest-module="{tgt}" />\n')
            file.write("</at>\n")
            file.write(f'<at t="{timestamp + downtime}s">\n')
            for (src, tgt) in link_list:
                capacity = network_topology.edges[src,tgt]['capacity'] * 8
                latency = network_topology.edges[src,tgt]["latency"]
                file.write(f'	<connect src-module="{src}" src-gate="pppg[{link_to_ppp[(src,tgt)]}]" dest-module="{tgt}" dest-gate="pppg[{link_to_ppp[(tgt,src)]}]" channel-type="ned.DatarateChannel">\n')
                file.write(f'       <param name="datarate" value="{capacity}bps" />\n')
                file.write(f'       <param name="delay" value="{latency}ms" />\n')
                file.write(f'</connect>\n')
            file.write("</at>\n")

    file.write("</scenario>\n")

def generate_scenarios(num_scenarios, sim_duration, dir, link_to_ppp, conf, network):
    network_undirected = network.topology.to_undirected()
    random.seed(100)

    node_failure_probability, edge_failure_probability = compute_failure_probabilities(network_undirected)

    for i in range(num_scenarios):
        failed_links = []
        failure_occured = False
        time_stamped_failures = []
        for node in network_undirected:
            if random.random() < node_failure_probability[node]:
                failed_nodes = []

                # Check if links are already failed
                for (src,tgt) in network_undirected.edges(node):
                    if ((src, tgt) in failed_links) or ((tgt, src) in failed_links):
                        continue
                    else:
                        failed_nodes.append((src,tgt))
                        failed_links.append((src,tgt))
                        failed_links.append((tgt,src))

                downtime = random.randint(20, 10800) * conf["time_scale"]
                time_stamp = conf["time_scale"] * 3600 * random.randint(1, 23)
                time_stamped_failures.append((time_stamp, failed_nodes, downtime))
                failure_occured = True

        for (src,tgt) in network_undirected.edges:
            if (src, tgt) in failed_links:
                continue
            if random.random() < edge_failure_probability[(src,tgt)]:
                failed_edges = [(src, tgt)]
                downtime = random.randint(20, 10800) * conf["time_scale"]
                time_stamp = conf["time_scale"] * 3600 * random.randint(1, 23)
                time_stamped_failures.append((time_stamp, failed_edges, downtime))
                failure_occured = True

        if failure_occured == False:
            fail_type = random.choice(["link", "node"])
            if fail_type == "node":
                node = random.choice(list(network_undirected.nodes))
                failed_nodes = []
                failed_nodes.extend(network_undirected.edges(node))
                downtime = random.randint(20, 10800) * conf["time_scale"]
                time_stamp = conf["time_scale"] * 3600 * random.randint(1, 23)
                time_stamped_failures.append((time_stamp, failed_nodes, downtime))
            else:
                (src,tgt) = random.choice(list(network_undirected.edges))
                failed_edges = [(src, tgt)]
                downtime = random.randint(20, 10800) * conf["time_scale"]
                time_stamp = conf["time_scale"] * 3600 * random.randint(1, 23)
                time_stamped_failures.append((time_stamp, failed_edges, downtime))

        file_path = os.path.join(dir, f"scenario_{i}.xml")
        with open(file_path, "w") as f:
            to_omnetpp_scenario(f, link_to_ppp, conf, network_undirected, failed_links=time_stamped_failures)

def prune_1_degree_nodes(graph):
    # Create a copy of the original graph
    pruned_graph = graph.copy()

    # Get a list of all nodes with degree 1
    nodes_to_remove = [node for node in pruned_graph.nodes if pruned_graph.degree[node] == 1]

    # Base case: if no 1 degree nodes found, return the pruned graph
    if not nodes_to_remove:
        return pruned_graph

    # Prune all 1 degree nodes
    for node in nodes_to_remove:
        pruned_graph.remove_node(node)

    # Recursively prune more 1 degree nodes
    return prune_1_degree_nodes(pruned_graph)

def compute_failure_probabilities(graph: networkx.Graph, node_failure_probability=0.1, edge_failure_probability=0.05):
    node_probabilities = {}
    edge_probabilities = {}

    summed_capacity = {}

    # Compute node probabilities weighted by summed capacity of connected edges
    for node in graph.nodes:
        summed_capacity[node] = sum(graph[node][neighbor]['capacity'] for neighbor in graph.neighbors(node))

    normalize_capacities = normalize_dictionary(summed_capacity)

    for node in graph.nodes:
        node_probabilities[node] = node_failure_probability * normalize_capacities[node]

    edge_capacities = {}

    # Compute edge probabilities weighted by their capacity
    for edge in graph.edges:
        edge_capacities[edge] = graph[edge[0]][edge[1]]['capacity']

    normalize_edge_capacities = normalize_dictionary(edge_capacities)

    for edge in graph.edges:
        edge_probabilities[edge] = edge_failure_probability * normalize_edge_capacities[edge]


    return node_probabilities, edge_probabilities

def normalize_dictionary(dictionary):
    max_val = max(dictionary.values())

    # Normalize the values by dividing each value by the total sum
    normalized_dictionary = {key: value / max_val for key, value in dictionary.items()}

    return normalized_dictionary

def create_xml_element(name, text=None, attrib=None):
    elem = ET.Element(name)
    if text:
        elem.text = str(text)
    if attrib:
        for key, value in attrib.items():
            elem.set(key, value)
    return elem