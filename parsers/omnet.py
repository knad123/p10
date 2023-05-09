# import jsonschema
import datetime
import os
import xml.etree.ElementTree as ET
import time
from os import path
from typing import Dict, List, Tuple

import classes.network


def to_omnetpp(network: classes.network.MLPS_Network, temporal_demands: Dict[Tuple[str, str], List[Tuple[float,str,str]]], conf, name='default', output_dir='./omnet_files/default', scaler=1, packet_size=64,
               zero_latency=False, package_name="inet.zoo_topology", algorithm="none", latency_scaler=1.0):
    """
    Generates all files for OMNeT++.
    """

    if not path.exists(output_dir):
        os.makedirs(output_dir)

    export_flows = build_flows_for_export(network)

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
                                          zero_latency=zero_latency, package_name=package_name, algorithm=algorithm)

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

    with open(f'{output_dir}/omnetpp.ini', mode="w") as f:
        to_omnetpp_ini(conf=conf, network=network, export_flows=export_flows, temporal_demands=temporal_demands, name=name, file=f,
                               packet_size=packet_size, send_interval_multiplier=scaler, zero_latency=zero_latency,
                               algorithm=algorithm)

    if not path.exists(output_dir + "/lib_files"):
        os.makedirs(output_dir + "/lib_files")
    if not path.exists(output_dir + "/classification_files"):
        os.makedirs(output_dir + "/classification_files")

    to_omnetpp_lib(network, interface_dict, output_dir + "/lib_files")
    to_omnetpp_classification(network, export_flows, output_dir + "/classification_files")


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
    if conf["algorithm"] in ['essence', 'essence_stateless']:
        file.write(f"import inet.p10.TwoPhaseCommit;\n")
        file.write("import inet.p10.MeasureWriter;\n")
    file.write("\n")
    file.write(f"network {name}_{algorithm}{{\n")

    # Global statistic
    file.write("    parameters:\n")
    file.write("        int timeBetweenRecordings = 100;\n")
    file.write('        int recordingSampleDuration = 5000;\n')
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
    if conf["algorithm"] in ['essence', 'essence_stateless']:
        file.write(f"        twoPhaseCommit: TwoPhaseCommit{{updateInterval = {conf['update_interval']}s;}}\n")
        file.write("        measureWriter: MeasureWriter;\n")
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
        bandwidth = data['bandwidth'] * 8 if 'bandwidth' in data else DEFAULT_BANDWIDTH
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


def to_omnetpp_ini(conf, network, export_flows, temporal_demands: Dict[Tuple[str, str], List[Tuple[float,str,str]]], name, file, failure_scenarios_enum=0, packet_size=64,
                   send_interval_multiplier=1, zero_latency=False, algorithm="none"):
    UTILIZATION_SAMPLE_INTERVAL = 5  # seconds

    file.write("[General]\n")
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
    # Add classification files
    for router_name, router in network.routers.items():
        file.write \
            (f"**.{router_name}.classifier.config = xmldoc(\"classification_files/{router_name}_classification.xml\")\n")

    # file.write("\n[Config UDP]\n")
    # Create a dictionary to keep track of the app entries for each source host.
    source_apps = {}
    source_hosts = {}
    target_apps = {}
    flow_idx = 0
    longest_send_interval = 0 # Used to find the simulation time limit

    i = 1
    for flow in export_flows:
        target_apps[flow['egress']] = {'destAddresses': flow['target_host'], 'destPort': i}
        i += 1

    for flow in export_flows:
        for load, starttime, stoptime in temporal_demands[flow['ingress'],flow['egress']]:
            flow_idx += 1
            ingress = flow['ingress']
            egress = flow['egress']
            if int(load) != 0:
                send_interval = (send_interval_multiplier * (1 / (int(load) / packet_size)))
            else:
                send_interval = 3600
            longest_send_interval = send_interval if send_interval > longest_send_interval else longest_send_interval
            entry = {'typename': 'UdpBasicApp', 'localPort': flow_idx, 'destPort': target_apps[egress]['destPort'],
                                         'messageLength': f"{packet_size} bytes",
                                         'destAddresses': target_apps[egress]['destAddresses'], 'source_host': flow['source_host']}

            if ingress not in source_apps:
                source_apps[ingress] = entry
                source_hosts[ingress] = [(starttime, stoptime, send_interval, flow)]
            else:
                source_hosts[ingress].append((starttime, stoptime, send_interval, flow))



    warmup_time = 0
    sim_time = 86400 * conf["time_scale"]

    file.write(f"warmup-period = {warmup_time}s\n")
    file.write(f"sim-time-limit = {sim_time}s\n")

    host_port = 1
    for ingress, apps in source_apps.items():
        file.write(f'''**.{apps['source_host']}.numApps = {len(source_hosts[ingress])}\n''')
        for (i, (starttime, stoptime, send_interval, flow)) in enumerate(source_hosts[ingress]):
            x = time.strptime(starttime, '%H:%M')
            starttime = int(datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min).total_seconds()) * conf["time_scale"]
            stoptime = starttime + 3600 * conf["time_scale"] # Hack to just set starttime an hour later
            '''            
            if source_hosts[ingress][i] != source_hosts[ingress][len(source_hosts[ingress])-1]:
                y = time.strptime(source_hosts[ingress][i+1][0], '%H:%M')
                stoptime = int(datetime.timedelta(hours=y.tm_hour, minutes=y.tm_min).total_seconds())
            else:
                stoptime = starttime + 3600
            '''
            file.write(f'''**.{apps['source_host']}.app[{i}].typename = "{apps['typename']}"\n''')
            file.write(f'''**.{apps['source_host']}.app[{i}].localPort = {host_port}\n''')
            file.write(f'''**.{apps['source_host']}.app[{i}].destPort = {target_apps[flow['egress']]['destPort']}\n''')
            file.write(f'''**.{apps['source_host']}.app[{i}].messageLength = {apps['messageLength']}\n''')
            file.write(f'''**.{apps['source_host']}.app[{i}].sendInterval = {send_interval}s\n''')
            file.write(f'''**.{apps['source_host']}.app[{i}].destAddresses = "{flow['target_host']}"\n''')
            file.write(f'''**.{apps['source_host']}.app[{i}].startTime = {starttime}s\n''')
            file.write(f'''**.{apps['source_host']}.app[{i}].stopTime = {stoptime}s\n''')
            host_port += 1
        file.write("\n")

    # Group export flows by egress/target host
    flows_by_target = {}
    for source, apps in target_apps.items():
        target = apps['destAddresses']
        if target not in flows_by_target:
            flows_by_target[target] = []
        flows_by_target[target].append(apps)

    # Add applications at target nodes
    target_port = 1
    for target, items in target_apps.items():
        file.write(f'''**.{items['destAddresses']}.numApps = 1\n''')
        file.write(f'''**.{items['destAddresses']}.app[0].typename = "UdpSinkApp"\n''')
        file.write(f'''**.{items['destAddresses']}.app[0].io.localPort = {items['destPort']}\n''')
        file.write("\n")

    for scenario in range(failure_scenarios_enum):
        file.write(f'[Config Scenario_{scenario}]\n')
        file.write(f'**.scenarioManager.script = xmldoc("failure_scenarios/scenario_{scenario}.xml")\n')
        file.write("\n")


def to_omnetpp_lib(network, interface_dict, export_dir):
    for router_name, router in network.routers.items():
        table_xml = to_omnetpp_lib_xml(router, interface_dict)
        ET.indent(table_xml)  # NOTE: Requires >= Python 3.9
        ET.ElementTree(table_xml).write(f"{export_dir}/{router_name}_lib.xml")


def to_omnetpp_scenario(network, file, failure_scenario, link_to_ppp):
    file.write('<?xml version="1.0"?>\n')
    file.write("<scenario>\n")
    file.write('<at t="20s">\n')
    for fail in failure_scenario:
        file.write(f'	<disconnect src-module="{fail[0]}" src-gate="pppg[{link_to_ppp[tuple(fail)]}]" />\n')
    file.write("</at>\n")
    file.write("</scenario>\n")


def build_flows_for_export(network):
    """
    Returns an array with the data of all flows (as a dictionary).
    """
    flows = {}

    # Initialize external_connections dictionary in the network
    network.external_connections = {}

    for index, row in network.demand_dataframe.iterrows():
        source = row['source']
        target = row['target']
        label = row['label']
        load = row['load']

        if source not in flows:
            flows[source] = {}

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
        network.external_connections[router] = {"source": f"host{source_nums[router]}", "target": f'target{target_nums[router]}'}

    return export_flows


def to_omnetpp_classification(network, export_flows, export_dir):
    for router_name in network.routers.keys():
        flows_at_router = list(filter(lambda entry: entry['ingress'] == router_name, export_flows))

        id = 0
        table_xml = ET.Element("fectable")
        for entry in flows_at_router:
            id = id + 1
            entry_xml = ET.SubElement(table_xml, "fecentry")
            ET.SubElement(entry_xml, "id").text = str(id)
            ET.SubElement(entry_xml, "label").text = str(entry['in_label'])
            ET.SubElement(entry_xml, "destination").text = entry['target_host']
            ET.SubElement(entry_xml, "source").text = entry['source_host']

        ET.indent(table_xml)  # NOTE: Requires >= Python 3.9
        ET.ElementTree(table_xml).write(f"{export_dir}/{router_name}_classification.xml")

def to_omnetpp_lib_xml(router, interface_dict):
    table_xml = ET.Element("libtable")
    for label, entry in router.forwarding_table.items():
        entry_xml = ET.SubElement(table_xml, "libentry")
        ET.SubElement(entry_xml, "priority").text = str(0)
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
