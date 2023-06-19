import concurrent.futures
import itertools
import math
import multiprocessing
import timeit

import networkx.exception
from functools import *
from networkx import shortest_path, diameter, shortest_simple_paths
import networkx as nx
from collections import defaultdict
import os
import random
from itertools import islice, cycle
import itertools
from typing import Dict, Tuple, List, Callable

import time
from classes.network import MPLS_Network


def SPUNGEET(network: MPLS_Network, conf, start_time, essence_state, failed_network_links = [], first_run = False):
    if conf['big_flows'] and first_run == False:
        demands = get_big_flows(network.demands, 0.85)
    else:
        demands = network.demands
    genetic_weights = genetic_algorithm(network=network, loads=demands, population_size=conf['population'],
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'), conf=conf, start_time=start_time,
                                      time_limit=conf["update_interval"], essence_state=essence_state, weight_range=(len(demands.keys())*10), failed_network_links = failed_network_links, first_run=first_run)
    return genetic_weights

def get_big_flows(loads, threshold_percentage: float):
    sorted_flows = sorted(loads.items(), key=lambda x: x[1], reverse=True)

    # Calculate the cumulative sum of flows and find the index at which it exceeds the threshold
    cumulative_sum = 0
    threshold = sum(loads.values()) * threshold_percentage
    index = 0
    for i, (demand, flow_value) in enumerate(sorted_flows):
        cumulative_sum += flow_value
        if cumulative_sum > threshold:
            index = i
            break

    # Create a new loads dictionary with demands making up some percentage of the total flow
    valid_loads = {demand: load for demand, load in sorted_flows[:index + 1]}
    return valid_loads

def filter_individuals(population, demands, weight_range):
    filtered_population = []
    valid_demands = set(demands.keys())
    for individual in population:
        # Check if all demands in the individual are present in the valid demands
        if set(individual.keys()).issubset(valid_demands):
            filtered_individual = {}
            for demand in valid_demands:
                if demand in individual:
                    filtered_individual[demand] = individual[demand]
                else:
                    filtered_individual[demand] = random.randint(1,weight_range)
            filtered_population.append(filtered_individual)
        else:
            filtered_individual = {}
            for demand in valid_demands:
                filtered_individual[demand] = random.randint(1,weight_range)
            filtered_population.append(filtered_individual)
    return filtered_population

def genetic_algorithm(network, loads, capacities, conf, start_time, essence_state, generations=700,
                      population_size=200,
                      crossover_rate=0.9,
                      mutation_rate=0.7, time_limit=10, weight_range=1000, failed_network_links = [], first_run = False):
    end_time = start_time + time_limit
    if not essence_state.current_population:
        population = create_population(loads, population_size, weight_range)
    else:
        new_population = create_population(loads, int(population_size * (1 - conf['keep_percentage'])), weight_range)
        if conf['big_flows']:
            filtered_current_population = filter_individuals(essence_state.current_population, loads, weight_range)
            population = filtered_current_population + new_population
        else:
            population = essence_state.current_population + new_population

    iterations = 0
    # Run the genetic algorithm
    #for generation in range(generations):
    if True:
        selection_time = 0
        while time.time() < end_time:
            # Select parents
            selection_start = time.time()
            if failed_network_links != []:
                a_class, b_class, c_class = selection(population, capacities, loads, network.topology, essence_state, failed_network_links)
            else:
                a_class, b_class, c_class = selection(population, capacities, loads, network.topology, essence_state)
            selection_time += time.time() - selection_start
            #print(str(generation) + ": " + str(calculate_fitness(a_class[0], capacities, loads, network.topology)))
            # Generate the children
            # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
            children = a_class  # + random_solutions
            while len(children) < population_size:
                parent1 = random.choice(a_class)
                parent2 = random.choice(b_class + c_class)
                child = crossover(parent1, parent2)
                child = mutation(child, weight_range)
                children.extend([child])

            # Replace the population with the children
            population = children
            iterations += 1

        print("number of iteration: " + str(iterations))
        print(selection_time)
    else:
        for _ in range(20):
            iteration_start_time = time.time()
            # Select parents
            if failed_network_links != []:
                a_class, b_class, c_class = selection(population, capacities, loads, network.topology, essence_state,
                                                      failed_network_links)
            else:
                a_class, b_class, c_class = selection(population, capacities, loads, network.topology, essence_state)
            # print(str(generation) + ": " + str(calculate_fitness(a_class[0], capacities, loads, network.topology)))
            # Generate the children
            # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
            children = a_class  # + random_solutions
            while len(children) < population_size:
                parent1 = random.choice(a_class)
                parent2 = random.choice(b_class + c_class)
                child = crossover(parent1, parent2)
                child = mutation(child, weight_range)
                children.extend([child])

            # Replace the population with the children
            population = children
            iterations += 1
            print("iteration " + str(iterations) + " runtime: " + str(time.time() - iteration_start_time) + " seconds")
            print(str(iterations) + ": " + str(
                calculate_fitness(a_class[0], capacities, loads, network.topology, essence_state)))

    # Sort the population by fitness
    if failed_network_links != []:
        a_class, b_class, c_class = selection(population, capacities, loads, network.topology, essence_state, failed_network_links)
    else:
        a_class, b_class, c_class = selection(population, capacities, loads, network.topology, essence_state)
    essence_state.current_population = population[:int(len(population) * conf['keep_percentage'])]
    # Return the fittest individual

    demands_ordered = sorted(a_class[0], key=lambda weights: a_class[0][weights], reverse=True)

    inverse_graph = essence_state.inverse_capacity_graph.copy()

    pathdict = {}
    link_caps = capacities.copy()

    for (src,tgt) in demands_ordered:
        path = nx.dijkstra_path(inverse_graph, src, tgt)
        pathdict[src,tgt] = [path]
        # Apply load to each link in the path
        for i in range(len(path) - 1):
            v1, v2 = path[i], path[i+1]

            # Subtract load from capacity
            link_caps[v1,v2] -= loads[(src, tgt)]

            # Update inverse capacity
            inverse_graph[v1][v2]['weight'] = 1 / max(link_caps[v1,v2], 1)

    return pathdict

def create_population(demands, population_size, weight_range):
    population = []
    for _ in range(population_size):
        individual = {}
        for src, tgt in demands:
            individual[src,tgt] = random.randint(1,weight_range)
        population.append(individual)
    return population

def crossover(p1, p2, crossover_probability = 0.7):
    child = {}
    for demand in p1.keys():
        if random.random() < 0.7:
            child[demand] = p1[demand]
        else:
            child[demand] = p2[demand]
    return child

def mutation(c, weight_range):
    if random.random() < 0.01:
        for src, tgt in c:
            c[src, tgt] = random.randint(1, weight_range)
        return c
    else:
        return c

def selection(population, capacities, loads, topology, essence_state, failed_network_links=[]):
    if failed_network_links:
        fitness_values = calculate_fitness_parallel(population, capacities, loads, topology, essence_state, failed_network_links)
    else:
        fitness_values = calculate_fitness_parallel(population, capacities, loads, topology, essence_state)

    # Zip the fitness values and the population together
    fitness_population = zip(fitness_values, population)

    # Sort the list of tuples by the fitness values
    sorted_fitness_population = sorted(fitness_population, key=lambda x: x[0])

    # Extract the individuals from the sorted list of tuples
    population = [individual for fitness, individual in sorted_fitness_population]

    a_class = population[:int(len(population) * 0.2)]
    b_class = population[int(len(population) * 0.2):int(len(population) * 0.9)]
    c_class = population[int(len(population) * 0.9):]

    return a_class, b_class, c_class

def calculate_fitness_parallel(population, capacities, loads, topology, essence_state, failed_network_links=[]):
    num_cores = multiprocessing.cpu_count() if 'SLURM_CPUS_PER_TASK' not in os.environ else int(
        os.environ['SLURM_CPUS_PER_TASK'])
    before_time = time.time()
    network = essence_state.inverse_capacity_graph.to_directed()
    src_tgt_pairs = itertools.product(network.nodes, network.nodes)
    estimate = {}
    for src, tgt in src_tgt_pairs:
        estimate[(src,tgt)] = len(nx.shortest_path(network, src, tgt, weight="weight"))

    print(f"Time to make heuristic function: {time.time() - before_time}")
    with multiprocessing.Pool(len(population)) as pool:
        if failed_network_links:
            result = pool.starmap(calculate_fitness, [(individual, capacities.copy(), loads, topology, essence_state, failed_network_links) for individual in population])
        else:
            result = pool.starmap(calculate_fitness, [(individual, capacities.copy(), loads, topology, essence_state, estimate) for individual in population])

    return result


def calculate_fitness(individual, capacities, loads, topology, essence_state, estimate = None, failed_network_links = []):
    # Initialize the utilization of each link to 0

    if estimate:
        h = lambda a,b: estimate[(a,b)]
    else:
        h = lambda a,b: 0
    link_loads = {link: 0 for link in capacities.keys()}

    demands_ordered = sorted(individual, key=lambda weights: individual[weights], reverse=True)

    link_caps = capacities.copy()
    inverse_graph = essence_state.inverse_capacity_graph.to_directed().copy()

    if failed_network_links:
        for (fail_v1, fail_v2) in failed_network_links:
            if inverse_graph.has_edge(fail_v1, fail_v2):
                inverse_graph.remove_edge(fail_v1, fail_v2)
            if inverse_graph.has_edge(fail_v2, fail_v1):  # Remove the inverse edge as well
                inverse_graph.remove_edge(fail_v2, fail_v1)

    pathdict = {}
    for (src,tgt) in demands_ordered:
        try:
            path = nx.astar_path(inverse_graph, src, tgt, heuristic=h, weight='weight')
        except:
            continue
        pathdict[src,tgt] = path
        # Apply load to each link in the path
        for i in range(len(path) - 1):
            v1, v2 = path[i], path[i+1]
            # Subtract load from capacity
            link_caps[v1,v2] -= loads[(src, tgt)]

            # Update inverse capacity
            inverse_graph[v1][v2]['weight'] = 1 / max(link_caps[v1,v2], 1)

            link_loads[(v1,v2)] += loads[(src, tgt)]



    # Calculate the congestion component of the fitness
    congestion = 0
    for link, capacity in capacities.items():
        utilization = link_loads[link] / capacity
        congestion += fortz_func(utilization) * capacity
    return congestion

def fortz_func(u):
    if u <= 1 / 20:
        return u * 0.1
    if u <= 1 / 10:
        return u * 0.3 - 0.01
    if u <= 1 / 6:
        return u * 1 - 0.08
    if u <= 1 / 3:
        return u * 2 - 0.24666
    if u <= 1 / 2:
        return u * 5 - 1.24666
    if u <= 2 / 3:
        return u * 10 - 3.74666
    if u <= 9 / 10:
        return u * 20 - 10.41333
    if u <= 1:
        return u * 70 - 55.41333
    if u <= 11 / 10:
        return u * 500 - 485.41333
    else:
        return u * 5000 - 5435.41333