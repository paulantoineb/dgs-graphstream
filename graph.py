#!/usr/bin/env python3

import logging
import networkx as nx
import pydot
import itertools
from scipy import interpolate

import utils

def add_node_attribute_to_graph(graph, attribute_name, dictionary):
    nx.set_node_attributes(graph, name=attribute_name, values=dictionary)

def add_node_attribute_to_subgraphs(sub_graphs, attribute_name, dictionary):
    for sub_graph in sub_graphs:
        for node in sub_graph.nodes():
            if node in dictionary:
                sub_graph.nodes[node][attribute_name] = dictionary[node]

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
        sub_graph_nodes = [n for n,p in assignments.items() if p == partition]
        sub_graph = graph.subgraph(sub_graph_nodes).copy() # make deep copy so that the graph is editable
        sub_graph.graph['partition'] = partition
        for node in sub_graph.nodes():
            sub_graph.nodes[node]['partition'] = partition
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
    nx.drawing.nx_pydot.write_dot(merged_graph, output_dot_filepath)

def add_cut_edges_to_subgraphs(input_graph, sub_graphs, assignments, cut_edge_node_size):
    # Get cut edges
    cut_edges = get_cut_edges(input_graph, sub_graphs)
    # Add cut edges and hidden nodes to partition graphs
    logging.info("Adding %d cut edges to the partition graphs", len(cut_edges))
    available_node_id = max(input_graph.nodes()) + 1 # next available node id
    for sub_graph in sub_graphs:
        sub_graph_cut_edges = [edge for edge in cut_edges if is_edge_connected_to_graph(edge, sub_graph)]
        for edge in sub_graph_cut_edges:
            internal_node, external_node = get_internal_external_nodes(edge, sub_graph)
            new_node = available_node_id
            sub_graph.add_node(new_node, hidden=1)
            available_node_id += 1
            # add hidden_node attribute to link existing node to hidden node
            if 'hidden_nodes' in sub_graph.nodes[internal_node]:
                sub_graph.nodes[internal_node]['hidden_nodes'].append(new_node) # append node to hidden_nodes attribute
            else:
                sub_graph.nodes[internal_node]['hidden_nodes'] = [new_node]
            # add node size attribute
            sub_graph.nodes[new_node]['size'] = cut_edge_node_size
            # add partition and connect attributes
            sub_graph.nodes[new_node]['partition'] = sub_graph.nodes[internal_node]['partition']
            sub_graph.nodes[new_node]['connect'] = [internal_node, external_node] # add attribute with the 2 nodes from different partitions that the hidden edge is connecting
            # add edge between existing and new nodes
            sub_graph.add_edge(internal_node, new_node)
            # insert node into assignments
            assignments[new_node] = assignments[internal_node]

def is_edge_connected_to_graph(edge, graph):
    return edge[0] in graph.nodes() or edge[1] in graph.nodes()

def get_internal_external_nodes(edge, graph):
    if edge[0] not in graph.nodes():
        external_node = edge[0] # node from another partition
        internal_node = edge[1] # node from current partition
    elif edge[1] not in graph.nodes():
        external_node = edge[1]
        internal_node = edge[0]
    else:
        external_node = -1
        internal_node = -1
    return internal_node, external_node

def get_cut_edges(input_graph, sub_graphs):
    sub_graph_edges = list(itertools.chain.from_iterable([sub_graph.edges() for sub_graph in sub_graphs]))
    sub_graph_nodes = list(itertools.chain.from_iterable([sub_graph.nodes() for sub_graph in sub_graphs]))
    cut_edges = [edge for edge in input_graph.edges()
                    if edge[0] in sub_graph_nodes
                    and edge[1] in sub_graph_nodes
                    and not is_edge_in_list(edge, sub_graph_edges)]
    return cut_edges

def is_edge_in_list(edge, edge_list):
    return edge in edge_list or (edge[1], edge[0]) in edge_list # try both permutations

def filter_visible_graph(graph):
    visibe_nodes = [node for node in graph.nodes() if not 'hidden' in graph.nodes[node]]
    return graph.subgraph(visibe_nodes)

def add_node_size_to_subgraphs(graph, sub_graphs, node_size_mode, node_size, min_node_size, max_node_size):
    if node_size_mode == 'centrality':
        centrality_per_node = nx.degree_centrality(graph)
        min_centrality = min(centrality_per_node.values())
        max_centrality = max(centrality_per_node.values())
        interpolator = interpolate.interp1d([min_centrality, max_centrality],[min_node_size, max_node_size], kind='linear')
        size_per_node = {k:int(interpolator(v)) for k,v in centrality_per_node.items()}
    elif node_size_mode == 'highlight-new':
        size_per_node = {node:min_node_size for node in graph.nodes()}
    else: # fixed
        size_per_node = {node:node_size for node in graph.nodes()}

    # Add size as node attribute
    add_node_attribute_to_subgraphs(sub_graphs, 'size', size_per_node)

def get_hidden_nodes(sub_graphs):
    hidden_nodes = []
    for sub_graph in sub_graphs:
        for node in sub_graph.nodes():
            if 'hidden' in sub_graph.nodes[node]:
                hidden_nodes.append((node, sub_graph.nodes[node]['connect']))
    return hidden_nodes

def add_node_order_to_subgraphs(sub_graphs, node_order):
    ''' Add node order to subgraphs '''
    # Get hidden nodes
    hidden_nodes = get_hidden_nodes(sub_graphs)

    # Add hidden nodes to node_order list
    for hidden_node, connected_nodes in hidden_nodes:
        hidden_node_index = max(node_order.index(connected_nodes[0]), node_order.index(connected_nodes[1])) + 1 # hidden node get added after the last of the 2 nodes from the edge it represents
        node_order.insert(hidden_node_index, hidden_node)

    # Add order as node attribute
    for sub_graph in sub_graphs:
        for node in sub_graph.nodes():
            sub_graph.nodes[node]['order'] = node_order.index(node) + 1 # order starts at 1