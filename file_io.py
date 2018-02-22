#!/usr/bin/env python3

import os
import logging
import networkx as nx
from collections import defaultdict

import utils

def read_metis(file):
    logging.info("Reading METIS file %s", file)

    G = nx.Graph() # create undirected graph

    # add node weights from METIS file
    with open(file, "r") as metis:

        n = 0
        first_line = None
        has_edge_weights = False
        has_node_weights = False
        n_vertex_weights = 1
        for i, line in enumerate(metis):
            if line[0] == '%':
                # ignore comments
                continue

            if not first_line:
                # read meta data from first line
                first_line = line.split()
                m_nodes = int(first_line[0])
                m_edges = int(first_line[1])
                if len(first_line) > 2:
                    # FMT has the following meanings:
                    #  0  the graph has no weights (in this case, you can omit FMT)
                    #  1  the graph has edge weights
                    # 10  the graph has node weights
                    # 11  the graph has both edge and node weights
                    file_format = first_line[2]
                    if int(file_format) == 0:
                        pass
                    elif int(file_format) == 1:
                        has_edge_weights = True
                    elif int(file_format) == 10:
                        has_node_weights = True
                    elif int(file_format) == 11:
                        has_edge_weights = True
                        has_node_weights = True
                    else:
                        assert False, "File format not supported"
                if len(first_line) > 3:
                    #  NCON, it appears, is the number of vertex weights.  Normally,
                    #  if vertex weights are used, there is only one weight per vertex,
                    #  and it is not even necessary to list NCON in the input.  But if
                    #  multiple values are associated with a vertex, NCON must be listed.
                    n_vertex_weights = int(first_line[3])
                continue

            # METIS starts node count from 1, here we start from 0 by
            # subtracting 1 in the edge list and incrementing 'n' after
            # processing the line.
            if line.strip():
                e = line.split()
                if has_edge_weights and has_node_weights:
                    node_weights = e[0:n_vertex_weights]
                    if len(e) > n_vertex_weights:
                        # create weighted edge list:
                        #  [(1, 2, {'weight':'2'}), (1, 3, {'weight':'8'})]
                        edges = e[n_vertex_weights:]
                        edges_split = list(zip(*[iter(edges)] * 2))
                        edge_list = [(n, int(v[0]) - 1, {'weight': int(v[1])}) for v in edges_split]

                        G.add_edges_from(edge_list)
                        G.node[n]['weight'] = int(node_weights[0]) # use 1st node weight
                    else:
                        # no edges
                        G.add_nodes_from([n], weight=int(node_weights[0])) # use 1st node weight

                elif has_edge_weights and not has_node_weights:
                    n_vertex_weights = 0
                    if len(e) > 0:
                        # create weighted edge list:
                        #  [(1, 2, {'weight':'2'}), (1, 3, {'weight':'8'})]
                        edges = e[n_vertex_weights:]
                        edges_split = list(zip(*[iter(edges)] * 2))
                        edge_list = [(n, int(v[0]) - 1, {'weight': int(v[1])}) for v in edges_split]

                        G.add_edges_from(edge_list)
                        G.node[n]['weight'] = 1.0
                    else:
                        # no edges
                        G.node[n]['weight'] = 1.0
                elif not has_edge_weights and has_node_weights:
                    node_weights = e[0:n_vertex_weights]
                    if len(e) > n_vertex_weights:
                        edges = e[n_vertex_weights:]
                        edge_list = [(n, int(v) - 1, {'weight':1.0}) for v in edges]
                        G.add_edges_from(edge_list)
                        G.node[n]['weight'] = int(node_weights[0]) # use 1st node weight
                    else:
                        # no edges
                        G.add_nodes_from([n], weight=int(node_weights[0]))
                    pass
                else:
                    edge_list = [(n, int(v) - 1, {'weight':1.0}) for v in e]
                    G.add_edges_from(edge_list)
                    G.node[n]['weight'] = 1.0
            else:
                # blank line indicates no node weight
                G.add_nodes_from([n], weight=1.0)
            n += 1

    # sanity check
    assert (m_nodes == G.number_of_nodes()), "Expected {} nodes, networkx graph contains {} nodes".format(m_nodes, G.number_of_nodes())
    assert (m_edges == G.number_of_edges()), "Expected {} edges, networkx graph contains {} edges".format(m_edges, G.number_of_edges())

    return G

def read_edgelist(file):
    logging.info("Reading edgelist file %s", file)
    return nx.read_edgelist(file)

def read_graph_from_file(file, format):
    graph = None
    if format == 'metis':
        graph = read_metis(file)
    elif format == 'edgelist':
        graph = read_edgelist(file)
        graph = nx.relabel_nodes(graph, {node:utils.to_int(node) for node in graph.nodes()})# relabel nodes as integers
    return graph

def read_assignments_file(file):
    logging.info("Reading assignments file %s", file)
    with open(file, 'r') as f:
        return {i:int(l.strip()) for i,l in enumerate(f.readlines())}

def read_order_file(file):
    logging.info("Reading order file %s", file)
    with open(file, 'r') as f:
        return [int(l.strip()) for l in f.readlines()]

def read_oslom2_tp_file(filepath):
    node_dict = defaultdict(list) # initialize modules per node dictionary
    with open(filepath, 'r') as file:
        line = next(file)
        while line:
            if line.startswith('#'): # module header line
                module_id = int(line.split()[1]) + 1 # 1-based (needed by gvmap) module id
            else: # nodes in the module
                nodes = line.split()
                for node_id in nodes:
                    node_dict[utils.to_int(node_id)].append(module_id) # add current module to node dictionary

            line = next(file, None)

    return node_dict

def read_infomap_tree_file(filepath, level):
    node_dict = defaultdict(list) # initialize modules per node dictionary
    module_ids = []
    with open(filepath, 'r') as file:
        line = next(file)
        while line:
            if not line.startswith('#'):
                values = line.split()
                module_id = ''.join(values[0].split(":")[0:level]) # concatenated module id at given level (1 to 3). 2:4:3 becomes 2 at level 1, 24 at level 2 and 243 at level 3
                if not module_id in module_ids:
                    module_ids.append(module_id)
                node_id = utils.to_int(values[2].strip('"')) # node id without quotes
                one_based_module_id = module_ids.index(module_id) + 1 # current 1-based (needed by gvmap) module id
                if not one_based_module_id in node_dict[node_id]:
                    node_dict[node_id].append(one_based_module_id) # add current module id to node dictionary

            line = next(file, None)

    return node_dict

def get_frame_start_and_count(full_graph, partition, trailing_frame_count):
    ''' Global frame start and count per node '''
    sorted_nodes = sorted(full_graph.nodes(data=True), key=lambda node: node[1]['order'])
    ordered_assignments = [node[1]['partition'] for node in sorted_nodes]
    partition_frame_start = [i for i, a in enumerate(ordered_assignments) if a == partition] # assignment start indexes for given partition
    partition_frame_start_extended = partition_frame_start + [len(sorted_nodes) + trailing_frame_count] # add last frame id with extra trailing frames to give highlighted nodes time to settle
    partition_frame_count = [v2 - v1 for v1, v2 in zip(partition_frame_start_extended, partition_frame_start_extended[1:])] # subtract consecutive frame start values
    return partition_frame_start, partition_frame_count

def write_dgs_file(output, graph, full_graph, label_type, colour_attr, trailing_frame_count):
    partition = graph.graph['partition']
    filename = os.path.join(output, 'partition_{}.dgs'.format(partition))
    logging.info("Writing DGS file %s (partition %d)", filename, partition)
    with open(filename, 'w') as outf:
        outf.write("DGS004\n")
        outf.write("partition_{} 0 0\n".format(partition))

        # get partition start and count per node
        partition_frame_start, partition_frame_count = get_frame_start_and_count(full_graph, partition, trailing_frame_count)
        # sort nodes according to node_order
        sorted_nodes = sorted(graph.nodes(data=True), key=lambda node: node[1]['order'])

        i = 0
        st = 1
        nodes_added = []
        edges_added = []
        for index, n in enumerate(sorted_nodes):
            node_id = n[0]

            # Hidden
            hidden = 1 if 'hidden' in n[1] else 0

            # Color
            color = 'black'
            if colour_attr in n[1]:
                color = n[1][colour_attr] # get color(s) from attributes

            # Label
            label = ''
            if hidden:
                label = '' # hide label for hidden nodes
            elif label_type == 'id':
                label = node_id
            elif label_type == 'order':
                label = n[1]['order']

            # Size
            node_size = n[1]['size']

            outf.write("an {} c='{}' l='{}' s='{}' fs='{}' fc='{}' hidden='{}'\n".format(node_id, color, label, node_size, partition_frame_start[index], partition_frame_count[index], hidden))
            nodes_added += [node_id]

            for e in graph.edges(node_id):
                edge1_id = e[1]
                edge2_id = e[0]
                if edge1_id in nodes_added and edge2_id in nodes_added and (edge1_id, edge2_id) not in edges_added:
                    outf.write("ae {} {} {}\n".format(i, edge1_id, edge2_id))
                    edges_added += [(edge1_id, edge2_id)]
                    i += 1

            outf.write("st {}\n".format(st))
            st += 1

    return filename

def write_oslom_edge_file(output_path, data_filename, graph):
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    if not os.path.exists(os.path.join(output_path, 'oslom')):
        os.makedirs(os.path.join(output_path, 'oslom'))

    # write edge list in a format for OSLOM, tab delimited
    edges_oslom_filename = os.path.join(output_path, 'oslom', data_filename + "-edges-oslom.txt")
    with open(edges_oslom_filename, "w") as outf:
        for e in graph.edges(data=True):
            edge_weight = e[2]["weight"] if 'weight' in e[2] else 1.0
            outf.write("{}\t{}\t{}\n".format(e[0], e[1], edge_weight))

    return edges_oslom_filename

def write_pajek_file(output_path, data_filename, graph):
    pajek_filepath = os.path.join(output_path, data_filename + ".net")
    # write_pajek requires string attributes
    weights = nx.get_node_attributes(graph, 'weight')
    new_weights = {k:utils.to_str(v) for k,v in weights.items()}
    nx.set_node_attributes(graph, name='weight', values=new_weights)
    nx.write_pajek(graph, pajek_filepath)
    return pajek_filepath