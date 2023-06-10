import concurrent.futures
import itertools
import math
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
from classes.essence_state import EssenceState


def essence_learn_paths_learn_weights(network: MPLS_Network, essence_state: EssenceState, conf, start_time):
    genetic_paths = genetic_algorithm(network=network ,loads=network.demands,
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'),
                                      essence_state=essence_state, conf=conf, start_time=start_time, time_limit=conf["update_interval"], crossover_rate=conf['crossover'], mutation_rate=conf['mutation'], population_size=conf['population'])
    return genetic_paths

def genetic_algorithm(network, loads, capacities, essence_state, conf, start_time, generations=1000, population_size=500,
                      crossover_rate=0.9,
                      mutation_rate=0.8, time_limit=118, weight_range = 100):
    end_time = start_time + time_limit

    if not essence_state.current_population:
        population = create_population(network, loads, population_size, conf, essence_state, weight_range)
    else:
        new_population = create_population(network, loads, int(population_size * (1 - conf['keep_percentage'])), conf, essence_state, weight_range)
        population = essence_state.current_population + new_population

    a_class, b_class, c_class = selection(population, capacities, loads)
    # Run the genetic algorithm
    while time.time() < end_time:
    #for generation in range(generations):
        # Select parents
        # Generate the children
        # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
        children = a_class  # + random_solutions
        while len(children) < population_size:
            parent1 = random.choice(a_class)
            parent2 = random.choice(b_class + c_class)
            child1, child2 = two_point_crossover(parent1, parent2, crossover_rate)
            child1 = mutate(child1, mutation_rate, network, essence_state.pathdict, conf, weight_range)
            child2 = mutate(child2, mutation_rate, network, essence_state.pathdict, conf, weight_range)
            children.extend([child1, child2])

        # Replace the population with the children
        population = children
        # Sort the population by fitness
        a_class, b_class, c_class = selection(population, capacities, loads)
        #print(str(calculate_fitness(a_class[0], capacities, loads)))


    essence_state.current_population = population[:int(len(population) * conf['keep_percentage'])]
    # Return the fittest individual
    return a_class[0]['paths'], a_class[0]['weights']

# FIX numpaths
def create_population(network, demands, population_size, conf, essence_state, weight_range):
    population = []
    for _ in range(population_size):
        individual = {}
        individual['paths'] = {}
        individual['weights'] = {}
        for src, tgt in demands:
            random_numpaths = random.randint(1, conf['split_num'])
            population_size = len(essence_state.pathdict[src, tgt])
            num_samples = min(random_numpaths, population_size)
            individual['paths'][src, tgt] = random.sample(essence_state.pathdict[src, tgt], num_samples)

        for src, tgt in network.topology.edges:
            individual['weights'][src,tgt] = random.randint(0,weight_range)

        population.append(individual)

    return population

def selection(population, capacities, loads):
    congestion = [calculate_fitness(individual, capacities, loads) for individual in
                                population]

    # Zip the fitness values and the population together
    fitness_population = zip(congestion, population)

    # Sort the list of tuples by the fitness values
    sorted_fitness_population = sorted(fitness_population, key=lambda x: x[0])

    # Extract the individuals from the sorted list of tuples
    population = [individual for fitness, individual in sorted_fitness_population]

    # Select the top 50% of the population as parents
    # num_parents = int(len(population) * 0.5)
    # parents = population[:num_parents]

    a_class = population[:int(len(population) * 0.2)]
    b_class = population[int(len(population) * 0.2):int(len(population) * 0.9)]
    c_class = population[int(len(population) * 0.9):]

    return a_class, b_class, c_class


def two_point_crossover(individual1, individual2, crossover_probability):
    # Check if crossover should happen
    if random.random() > crossover_probability:
        return individual1, individual2

    # Select two random points in the individuals
    point1 = random.randint(1, len(individual1['paths']) - 1)
    point2 = random.randint(point1 + 1, len(individual1['paths']))

    # Create the offspring by exchanging the elements between the two points
    offspring1 = {'paths': {}, 'weights': {}}
    offspring2 = {'paths': {}, 'weights': {}}
    i = 0
    for (src, tgt), paths in individual1['paths'].items():
        if i < point1:
            offspring1['paths'][(src, tgt)] = paths
            offspring2['paths'][(src, tgt)] = individual2['paths'][(src, tgt)]
        elif i < point2:
            offspring1['paths'][(src, tgt)] = individual2['paths'][(src, tgt)]
            offspring2['paths'][(src, tgt)] = paths
        else:
            offspring1['paths'][(src, tgt)] = paths
            offspring2['paths'][(src, tgt)] = individual2['paths'][(src, tgt)]
        i += 1

    # Select two random points in the individuals
    point1 = random.randint(1, len(individual1['weights']) - 1)
    point2 = random.randint(point1 + 1, len(individual1['weights']))
    i = 0
    for (src, tgt), weight in individual1['weights'].items():
        if i < point1:
            offspring1['weights'][(src, tgt)] = weight
            offspring2['weights'][(src, tgt)] = individual2['weights'][(src, tgt)]
        elif i < point2:
            offspring1['weights'][(src, tgt)] = individual2['weights'][(src, tgt)]
            offspring2['weights'][(src, tgt)] = weight
        else:
            offspring1['weights'][(src, tgt)] = weight
            offspring2['weights'][(src, tgt)] = individual2['weights'][(src, tgt)]
        i += 1

    return offspring1, offspring2


def calculate_fitness(individual, capacities, loads):
    # Initialize the utilization of each link to 0
    link_loads = {link: 0 for link in capacities.keys()}

    # Calculate the utilization of each link
    for (source, destination), paths in individual['paths'].items():
        load = loads[source, destination]
        longest_path_len = max([len(i) for i in paths]) - 1
        next_loads = {}
        for i in range(longest_path_len):

            # Find the number of splits and weights
            next_weights = {}
            next_hops = {}
            for path in paths:
                if i < len(path) - 1:
                    v1,v2 = path[i], path[i + 1]
                    if v1 not in next_weights:
                        next_weights[v1] = {}
                    if (v1,v2) not in next_hops:
                        next_hops[v1,v2] = 0
                    next_weights[v1][v2] = individual['weights'][v1,v2]
                    next_hops[v1,v2] += 1

            # Apply load to links
            for path in paths:
                if i < len(path) - 1:
                    v1,v2 = path[i], path[i+1]
                    weight = individual['weights'][v1,v2]
                    total_next_hop_weight = sum(next_weights[v1][v2] for v2 in next_weights[v1])
                    if (total_next_hop_weight == 0) and (v1 in next_loads):
                        number_of_splits = len(next_weights[v1])
                        split_load = ((1/number_of_splits) * next_loads[v1]) / next_hops[v1,v2]
                    elif (total_next_hop_weight == 0) and (v1 not in next_loads):
                        number_of_splits = len(next_weights[v1])
                        split_load = ((1/number_of_splits) * load) / next_hops[v1,v2]
                    elif v1 in next_loads:
                        split_load = ((weight / total_next_hop_weight) * next_loads[v1]) / next_hops[v1,v2]
                    else:
                        split_load = ((weight / total_next_hop_weight) * load) / next_hops[v1,v2]

                    # Add load to next hops and remove load from previous nodes
                    if v2 not in next_loads:
                        next_loads[v2] = 0
                    next_loads[v2] += split_load
                    if v1 in next_loads:
                        next_loads[v1] -= split_load

                    # Apply link loads
                    link_loads[v1,v2] += split_load

    # Calculate the congestion component of the fitness
    congestion = 0
    for link, capacity in capacities.items():
        utilization = link_loads[link] / capacity
        congestion += fortz_func(utilization) * capacity
    return congestion

    #return max(link_loads.values())

def mutate(individual, mutation_rate, network, pathdict, conf, weight_range):
    # Determine if the individual should be mutated
    if random.random() > mutation_rate:
        return individual

    # Choose a random source-destination pair to mutate
    src, tgt = random.choice(list(individual['paths'].keys()))

    # Choose a new path for the pair from the viable paths
    individual['paths'][src, tgt] = []

    random_numpaths = random.randint(1, conf['split_num'])
    population_size = len(pathdict[src, tgt])
    num_samples = min(random_numpaths, population_size)
    individual['paths'][src, tgt] = random.sample(pathdict[src, tgt], num_samples)

    src, tgt = random.choice(list(individual['weights'].keys()))
    individual['weights'][src,tgt] = random.randint(0,weight_range)


    return individual


def normalize(value):
    min_value = min(value)
    range_value = max(value) - min_value
    if range_value == 0:
        return value
    else:
        normalized_values = [(x - min_value) / range_value for x in value]
        return normalized_values


def normalize_values(congestion, stretch):
    normalized_congestion = normalize(congestion)
    normalized_stretch = normalize(stretch)
    return normalized_congestion, normalized_stretch


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
