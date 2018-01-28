#!/usr/bin/env python3

import logging
import networkx as nx
import pydot

import utils

def add_node_attribute_to_graph(graph, attribute_name, dictionary):
    nx.set_node_attributes(graph, name=attribute_name, values=dictionary)
    
def get_node_attribute_from_dot_file(filepath, attribute_name, to_int=False, strip_quotes=False):
    dictionary = {}
    output_graph = pydot.graph_from_dot_file(filepath)[0]
    for node in output_graph.get_nodes():
        name = node.get_name().strip('"')
        if to_int:
            name = utils.to_int(name)
        if name != 'graph':
            dictionary[name] = node.get(attribute_name)
            if strip_quotes:
                dictionary[name] = dictionary[name].strip('"')
    return dictionary
    
def create_sub_graphs(graph, partitions, assignments):
    logging.info("Splitting graph by partition into %d sub-graphs", len(partitions))
    sub_graphs = []
    for partition in partitions:
        sub_graph_nodes = [i + 1 for i,p in enumerate(assignments) if p == partition] # Need to add 1 as nodes from METIS start at 1
        sub_graph = graph.subgraph(sub_graph_nodes)
        sub_graphs.append(sub_graph)
    return sub_graphs
    
def get_pos(node):
    return node[1]['pos'].split(',')
    
def get_x(node):
    return float(get_pos(node)[0])
    
def get_y(node):
    return float(get_pos(node)[1])
    
def offset_graphs_to_avoid_overlaps(graphs, spacing):
    logging.info("Offsetting %d graphs by %f horizontally to avoid overlaps", len(graphs), spacing)
    offset = 0.0
    for graph in graphs:
        node_positions = {}
        # extract x values for current graph
        x_values = [get_x(node) for node in graph.nodes(data=True)]
        # apply offset to current graph
        for node in graph.nodes(data=True):
            node_positions[node[0]] = ','.join([str(get_x(node) + offset), str(get_y(node))])
        add_node_attribute_to_graph(graph, '"pos"', node_positions)
        # increment offset value to offset next graph by 10
        if x_values:
            offset += max(x_values) - min(x_values) + spacing
        
def merge_graphs(graphs, output_dot_filepath):
    logging.info("Merging %d graphs together and exporting dot file %s", len(graphs), output_dot_filepath)
    merged_graph = nx.union_all(graphs)
    nx.nx_agraph.write_dot(merged_graph, output_dot_filepath)