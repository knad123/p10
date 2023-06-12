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
from classes.essence_state import EssenceState


def essence_weight_setting(network: MPLS_Network, essence_state: EssenceState, conf, start_time):
    genetic_weights = genetic_algorithm(network=network, loads=network.demands,
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'),
                                      essence_state=essence_state, conf=conf, start_time=start_time,
                                      time_limit=conf["update_interval"], crossover_rate=conf['crossover'], mutation_rate=conf['mutation'], population_size=conf['population'])
    return genetic_weights


def genetic_algorithm(network, loads, capacities, essence_state, conf, start_time, generations=1000,
                      population_size=500,
                      crossover_rate=0.9,
                      mutation_rate=0.7, time_limit=118, weight_range=100):
    end_time = start_time + time_limit

    if not essence_state.current_population:
        population = create_population(network, population_size, weight_range)
    else:
        new_population = create_population(network, int(population_size * 0.8), weight_range)
        population = essence_state.current_population + new_population

    iterations = 0
    # Run the genetic algorithm
    #for generation in range(generations):
    while time.time() < end_time:
        iteration_start_time = time.time()
        # Select parents
        a_class, b_class, c_class = selection(population, capacities, loads, essence_state)
        # Generate the children
        # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
        children = a_class  # + random_solutions
        while len(children) < population_size:
            parent1 = random.choice(a_class)
            parent2 = random.choice(b_class + c_class)
            child1, child2 = two_point_crossover(parent1, parent2, crossover_rate)
            child1 = mutate(child1, mutation_rate, weight_range)
            child2 = mutate(child2, mutation_rate, weight_range)
            children.extend([child1, child2])

        # Replace the population with the children
        population = children
        print(str(iterations) + ": " + str(calculate_fitness(a_class[0], capacities, loads, essence_state)))
        print("iteration " + str(iterations) + " runtime: " + str(time.time() - iteration_start_time) + " seconds")
        iterations += 1
    # Sort the population by fitness
    a_class, b_class, c_class = selection(population, capacities, loads, essence_state)

    essence_state.current_population = population[:int(len(population) * 0.2)]
    # Return the fittest individual
    return a_class[0]

def create_population(network, population_size, weight_range):
    population = []
    for _ in range(population_size):
        individual = {}
        for src, tgt in network.topology.edges:
            individual[src,tgt] = random.randint(0,weight_range)
        population.append(individual)
    return population

def two_point_crossover(individual1, individual2, crossover_probability):
    # Check if crossover should happen
    if random.random() > crossover_probability:
        return individual1, individual2

    # Select two random points in the individuals
    point1 = random.randint(1, len(individual1) - 1)
    point2 = random.randint(point1 + 1, len(individual1))

    # Create the offspring by exchanging the elements between the two points
    offspring1 = {}
    offspring2 = {}
    i = 0
    for (src, tgt), path in individual1.items():
        if i < point1:
            offspring1[(src, tgt)] = path
            offspring2[(src, tgt)] = individual2[(src, tgt)]
        elif i < point2:
            offspring1[(src, tgt)] = individual2[(src, tgt)]
            offspring2[(src, tgt)] = path
        else:
            offspring1[(src, tgt)] = path
            offspring2[(src, tgt)] = individual2[(src, tgt)]
        i += 1

    return offspring1, offspring2

def selection(population, capacities, loads, essence_state):
    fitness_values = calculate_fitness_parallel(population, capacities, loads, essence_state)

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

def calculate_fitness_parallel(population, capacities, loads, essence_state):
    num_cores = multiprocessing.cpu_count() if 'SLURM_CPUS_PER_TASK' not in os.environ else int(
        os.environ['SLURM_CPUS_PER_TASK'])
    with multiprocessing.Pool(num_cores-2) as pool:
        result = pool.starmap(calculate_fitness, [(individual, capacities, loads, essence_state) for individual in population])

    return result

def calculate_fitness(individual, capacities, loads, essence_state):
    # Initialize the utilization of each link to 0
    link_loads = {link: 0 for link in capacities.keys()}

    # Calculate the utilization of each link
    for (source, destination), paths in essence_state.pathdict.items():
        load = loads[source, destination]
        longest_path_len = max([len(i) for i in paths]) - 1
        next_loads = {}
        for i in range(0, longest_path_len):

            # Find the number of splits and weights
            next_weights = {}
            next_hops = {}
            for path in paths:
                if i < len(path) - 1:
                    src,tgt = path[i], path[i + 1]
                    if src not in next_weights:
                        next_weights[src] = {}
                    if (src,tgt) not in next_hops:
                        next_hops[src,tgt] = 0
                    next_weights[src][tgt] = individual[src,tgt]
                    next_hops[src,tgt] += 1


            for path in paths:
                src, tgt = path[i], path[i + 1]
                total_next_hop_weights = sum(next_weights[src][tgt] for tgt in next_weights[src])

                if (total_next_hop_weights == 0) and (src in next_loads):
                    number_of_splits = len(next_weights[src])
                    split_load = ((1 / number_of_splits) * next_loads[src]) / next_hops[src, tgt]
                elif (total_next_hop_weights == 0) and (src not in next_loads):
                    number_of_splits = len(next_weights[src])
                    split_load = ((1 / number_of_splits) * load) / next_hops[src, tgt]
                elif src in next_loads:
                    split_load = ((individual[src, tgt] / total_next_hop_weights) * next_loads[src]) / next_hops[src,tgt]
                else:
                    split_load = ((individual[src, tgt] / total_next_hop_weights) * load) / next_hops[src,tgt]

                # Add load to next hops and remove load from previous nodes
                if tgt not in next_loads:
                    next_loads[tgt] = 0
                next_loads[tgt] += split_load
                if src in next_loads:
                    next_loads[src] -= split_load

                link_loads[src, tgt] += split_load

    # Calculate the congestion component of the fitness
    congestion = 0
    for link, capacity in capacities.items():
        utilization = link_loads[link] / capacity
        congestion += fortz_func(utilization)
    return congestion

    # return max(link_loads.values())


def mutate(individual, mutation_rate, weight_range):
    # Determine if the individual should be mutated
    if random.random() > mutation_rate:
        return individual

    # Choose a random source-destination pair to mutate
    src, tgt = random.choice(list(individual.keys()))

    # Choose a new path for the pair from the viable paths
    individual[src, tgt] = random.randint(0,weight_range)

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
