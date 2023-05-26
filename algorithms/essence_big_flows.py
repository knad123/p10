import concurrent.futures
import itertools
import math

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


def essence_big_flows(network: MPLS_Network, essence_state: EssenceState, conf, start_time):
    # Modify viable_paths dictionary to include only 90% of flows
    viable_paths, loads = get_viable_paths(essence_state.pathdict, network.demands, 0.9)

    genetic_paths = genetic_algorithm(viable_paths=viable_paths, loads=loads,
                                      capacities=nx.get_edge_attributes(network.topology, 'capacity'),
                                      essence_state=essence_state, conf=conf, start_time=start_time,
                                      time_limit=conf["update_interval"])
    return genetic_paths


def get_viable_paths(pathdict: Dict[Tuple[str, str], List[List[str]]], loads: Dict[Tuple[str, str], int],
                     threshold_percentage: float) -> Tuple[Dict[Tuple[str, str], List[List[str]]], Dict[Tuple[str, str], int]]:
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

    valid_demands = set(valid_loads.keys())
    viable_paths = {demand: paths for demand, paths in pathdict.items() if demand in valid_demands}

    return viable_paths, valid_loads

def filter_individuals(population, viable_paths):
    filtered_population = []
    valid_demands = set(viable_paths.keys())
    for individual in population:
        # Check if all demands in the individual are present in the valid demands
        if set(individual.keys()).issubset(valid_demands):
            filtered_individual = {demand: paths for demand, paths in individual.items() if demand in valid_demands}
            filtered_population.append(filtered_individual)
    return filtered_population

def genetic_algorithm(viable_paths: dict[tuple[str,str], list[list[str]]], loads: dict[tuple[str,str],int], capacities: dict[tuple[str,str],int], essence_state, conf, start_time, generations=1000, population_size=100,
                      crossover_rate=0.9,
                      mutation_rate=0.7, time_limit=118):
    end_time = start_time + time_limit
    if not essence_state.current_population:
        population = [{k: random.choice(v) for k, v in viable_paths.items()} for i in range(population_size)]
    else:
        new_population = [{k: random.choice(v) for k, v in viable_paths.items()} for i in
                          range(int(population_size * 0.8))]
        filtered_current_population = filter_individuals(essence_state.current_population, viable_paths)
        population = filtered_current_population + new_population

    # Run the genetic algorithm
    # for generation in range(generations):

    # Select parents
    a_class, b_class, c_class = selection(population, capacities, loads, essence_state.stretchdict,
                                          essence_state.congestion_weight)

    while time.time() < end_time:
        # print(str(generation) + ": " + str(calculate_fitness(a_class[0], capacities, loads)))
        # Generate the children
        # random_solutions = [{k: random.choice(v) for k, v in viable_paths.items()} for _ in range(int(population_size * 0.1))]
        children = a_class  # + random_solutions
        while len(children) < population_size:
            parent1 = random.choice(a_class)
            parent2 = random.choice(b_class + c_class)
            child1, child2 = two_point_crossover(parent1, parent2, crossover_rate)
            child1 = mutate(child1, mutation_rate, viable_paths)
            child2 = mutate(child2, mutation_rate, viable_paths)
            children.extend([child1, child2])

        # Replace the population with the children
        population = children

        # Select parents
        a_class, b_class, c_class = selection(population, capacities, loads, essence_state.stretchdict,
                                              essence_state.congestion_weight)

    essence_state.current_population = population[:int(len(population) * 0.2)]
    # Return the fittest individual
    return a_class[0]


# For parallelization
def generate_child(a_class, b_class, c_class, crossover_rate, mutation_rate, viable_paths):
    parent1 = random.choice(a_class)
    parent2 = random.choice(b_class + c_class)
    child1, child2 = two_point_crossover(parent1, parent2, crossover_rate)
    child1 = mutate(child1, mutation_rate, viable_paths)
    child2 = mutate(child2, mutation_rate, viable_paths)
    return child1, child2


def selection(population, capacities, loads, stretch_dict, congestion_weight):
    congestion, stretch = zip(*[calculate_fitness(individual, capacities, loads, stretch_dict) for individual in
                                population])

    normalized_congestion, normalized_stretch = normalize_values(congestion, stretch)

    stretch_weight = 1 - congestion_weight

    fitness_values = [normalized_congestion[i] * congestion_weight + normalized_stretch[i] * stretch_weight for i in
                      range(len(population))]

    # Zip the fitness values and the population together
    fitness_population = zip(fitness_values, population)

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


def calculate_fitness(individual, capacities, loads, stretch_dict):
    # Initialize the utilization of each link to 0
    utilization = {link: 0 for link in capacities.keys()}

    # Calculate the utilization of each link
    for (source, destination), path in individual.items():
        load = loads[source, destination]
        for i in range(len(path) - 1):
            link = (path[i], path[i + 1])
            utilization[link] += load

    # Calculate the congestion component of the fitness
    congestion = 0
    for link, capacity in capacities.items():
        u = utilization[link] / capacity
        congestion += fortz_func(u)

    # Calculate the stretch component of the fitness
    stretch = 0
    for (source, destination), paths in individual.items():
        stretch += stretch_dict[tuple(paths)]

    return congestion, stretch


def mutate(individual, mutation_rate, viable_paths):
    # Determine if the individual should be mutated
    if random.random() > mutation_rate:
        return individual

    # Choose a random source-destination pair to mutate
    source, destination = random.choice(list(individual.keys()))

    # Choose a new path for the pair from the viable paths
    new_path = random.choice(viable_paths[(source, destination)])

    # Mutate the individual
    individual[(source, destination)] = new_path

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
