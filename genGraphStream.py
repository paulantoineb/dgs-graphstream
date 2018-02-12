#!/usr/bin/env python3

import os
import sys
import glob
import logging
import argparse
import configparser
import subprocess
import itertools
import random
import math
import fpdf
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from svgutils.compose import *
import networkx as nx
from scipy import interpolate

import file_io
import graph
import color
import cluster
import utils

DGSGS_JAR = 'dgs-graphstream/dist/dgs-graphstream.jar'

def parse_arguments():
    parent_parser = argparse.ArgumentParser(add_help=False, description=
        '''Create animation of network partition assignments. First processes
        network file and assignments into DGS file format, then uses
        GraphStream to animate each frame, finally frames are stitched together.'''
    )
 
    # Required arguments
    required_group = parent_parser.add_argument_group('required arguments')
    required_group.add_argument('-g', '--graph', required=True,
                        help='input graph file')
    required_group.add_argument('-f', '--format', choices=['metis', 'edgelist'], required=True,
                        help='format of the input graph file')
    required_group.add_argument('-o', '--output_dir', required=True,
                        help='output directory')
    # Input/output files
    io_group = parent_parser.add_argument_group('input/outputs options')
    io_group.add_argument('-a', '--assignments',
                        help='partition assignments list')
    io_group.add_argument('--show-partitions', nargs='+', type=int,
                        help='partitions to be displayed (based on partition values in assignments list)')
    order_group = io_group.add_mutually_exclusive_group()
    order_group.add_argument('-n', '--order',
                        help='node order list')
    order_group.add_argument('--order-seed',
                        help='seed for ordering nodes')

    # Layout
    layout_group = parent_parser.add_argument_group('layout options')
    layout_group.add_argument('--layout', '-l', choices=['springbox','linlog'], default='springbox',
                        help='graph layout')
    layout_group.add_argument('--layout-seed', type=int, default=utils.get_random_seed(), metavar='S',
                        help='seed for graph layout')
    layout_group.add_argument('--force', type=float, metavar='F',
                        help='force for linlog graph layout (default=3.0)')
    layout_group.add_argument('--attraction', type=float, metavar='A',
                        help='attraction factor for linlog graph layout (default=0)')
    layout_group.add_argument('--repulsion', type=float, metavar='R',
                        help='repulsion factor for linlog graph layout (default=-1.2)')
    # Coloring
    coloring_group = parent_parser.add_argument_group('coloring options')
    color_mode_group = coloring_group.add_mutually_exclusive_group()
    color_mode_group.add_argument('--color-scheme', choices=['primary-colors','pastel'], default='primary-colors',
                        help='color scheme used by gvmap (default=primary-colors)')
    color_mode_group.add_argument('--node-color', metavar='C',
                        help='single color to use for all nodes')
    coloring_group.add_argument('--color-seed', type=int, default=utils.get_random_seed(), metavar='S',
                        help='seed for coloring with gvmap')
    coloring_group.add_argument('--shadow-color', metavar='C',
                        help='color of the shadow to use for highlighted nodes. Use with --node-size-mode highlight-new')
    # Image style
    styling_group = parent_parser.add_argument_group('image options')
    styling_group.add_argument('--node-size-mode', choices=['fixed', 'centrality', 'highlight-new'], default='fixed',
                        help='node size mode')
    styling_group.add_argument('--node-size', type=int, metavar='S',
                        help='node size in pixels (default=10). Use with --node-size-mode fixed.')
    styling_group.add_argument('--min-node-size', type=int, metavar='S',
                        help='minimum node size in pixels (default=10). Use with --node-size-mode centrality or highlight-new.')
    styling_group.add_argument('--max-node-size', type=int, metavar='S',
                        help='maximum node size in pixels (default=40). Use with --node-size-mode centrality or highlight-new.')
    styling_group.add_argument('--edge-size', type=int, default=1, metavar='S',
                        help='edge size in pixels (default=1)')
    styling_group.add_argument('--label-size', type=int, default=10, metavar='S',
                        help='label size in points (default=10)')
    styling_group.add_argument('--label-type', choices=['id', 'order'], default='id', metavar='T',
                        help='type of node labels (node id or node order)')
    styling_group.add_argument('--border-size', type=int, default=1, metavar='S',
                        help='border size between tiles (default=1)')
    styling_group.add_argument('--width', type=int, default=1280, metavar='W',
                        help='image width (default=1280)')
    styling_group.add_argument('--height', type=int, default=720, metavar='H',
                        help='image height (default=720)')
    # Video
    video_group = parent_parser.add_argument_group('video options')
    video_group.add_argument('--video',
                        help='output video file with tiled frames')
    video_group.add_argument('--fps', type=int,
                        help='frames per second (default=8)')
    # Pdf
    pdf_group = parent_parser.add_argument_group('pdf options')
    pdf_group.add_argument('--pdf', type=int, default=20, metavar='P',
                        help='Percentage of frames to convert to pdf (default=20)')
    
    # Sub-commands
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='scheme', help='select scheme to highlight either communities or cut edges')
    subparsers.required = True
    parser_communities = subparsers.add_parser('communities', parents = [parent_parser],
                                      help='highlight communities')
    parser_cut_edges = subparsers.add_parser('cut-edges', parents = [parent_parser],
                                      help='highlight cut edges')
                                      
    # Clustering
    clustering_group = parser_communities.add_argument_group('clustering options')
    clustering_group.add_argument('--clustering', '-c', choices=['oslom2','infomap','graphviz'], default='oslom2',
                        help='clustering method')
    clustering_group.add_argument('--cluster-seed', type=int, metavar='S',
                        help='seed for clustering')
    clustering_group.add_argument('--infomap-calls', type=int, metavar='C',
                        help='number of times infomap is called within oslom2. Good values are between 1 and 10 (default=0)')
                        
    # Cut edges
    parser_cut_edges.add_argument('--cut-edge-length', type=int, default=0, metavar='L',
                        help='length of cut edges (default=variable)')
    parser_cut_edges.add_argument('--cut-edge-node-size', default=5, metavar='S',
                        help='size of the nodes attached to cut edges (default=10)')

    return parser.parse_args()

def validate_arguments(args):
    errors = []
    # Partitioning
    if args.show_partitions and not args.assignments:
        errors.append("The --show-partitions option is only available when a partition assignments list is provided")
    # Clustering
    if args.scheme == 'communities':
        if args.clustering == 'graphviz' and args.cluster_seed:
            errors.append("The --cluster-seed option is not available with the graphviz clustering method")
        if args.clustering != 'oslom2' and args.infomap_calls:
            errors.append("The --infomap-calls option is only available with the oslom2 clustering method")
    # Layout
    if args.layout != 'linlog' and args.force:
        errors.append("The --force option is only available with the linlog layout")
    if args.layout != 'linlog' and args.attraction:
        errors.append("The --attraction option is only available with the linlog layout")
    if args.layout != 'linlog' and args.repulsion:
        errors.append("The --repulsion option is only available with the linlog layout")
    if not args.video and args.fps:
        errors.append("The --fps option is only available with the --video option")
    # Coloring
    # Image style
    if args.node_size and args.node_size_mode != 'fixed':
        errors.append("The --node-size option is only available with --node-size-mode fixed")
    if args.min_node_size and args.node_size_mode == 'fixed':
        errors.append("The --min-node-size option is only available with --node-size-mode centrality or highlight-new")
    if args.max_node_size and args.node_size_mode == 'fixed':
        errors.append("The --max-node-size option is only available with --node-size-mode centrality or highlight-new")

    if errors:
        for error in errors:
            logging.error(error)
        sys.exit(1)

    # Set default values
    if not args.fps:
        args.fps = 8
    if not args.node_size:
        args.node_size = 10
    if not args.min_node_size:
        args.min_node_size = 10
    if not args.min_node_size:
        args.max_node_size = 40
    if args.scheme == 'communities':
        if not args.cluster_seed:
            args.cluster_seed = utils.get_random_seed()
        if not args.infomap_calls:
            args.infomap_calls = 0

def parse_config_file(config_file):
    logging.debug("Reading the config file %s", config_file)
    config = configparser.ConfigParser()
    config.read(config_file)
    return config

def validate_install_dir(config_name, executable, errors):
    tool_bin = os.path.join(config['install_dirs'][config_name], executable)
    if not os.path.isfile(tool_bin):
        errors.append("The {} executable cannot be found in the directory {}. Please update the config file with the correct path.".format(config_name, config['install_dirs'][config_name]))

def validate_config(config):
    errors = []
    validate_install_dir('gvmap', 'gvmap', errors)
    validate_install_dir('oslom2', 'oslom_undir', errors)
    validate_install_dir('infomap', 'Infomap', errors)

    if errors:
        for error in errors:
            logging.error(error)
        sys.exit(1)

def run(args, config):
    # Clean output directory
    utils.create_or_clean_output_dir(args.output_dir)

    # Read input graph
    input_graph = file_io.read_graph_from_file(args.graph, args.format)
    logging.info("The input graph contains %d nodes and %d edges", nx.number_of_nodes(input_graph), nx.number_of_edges(input_graph))

    # Read assignments file
    assignments = get_assignments(args.assignments, args.show_partitions, input_graph)
    partitions = get_partitions(assignments) # Getting partitions from the assignments
    log_partitions_info(partitions, assignments)

    # Split graph into sub-graphs (one per partition)
    sub_graphs = split_graph(input_graph, assignments, partitions)

    # Add cut edges to graph
    cut_edge_length = 0
    if args.scheme == 'cut-edges':
        cut_edge_length = args.cut_edge_length
        add_cut_edges_to_subgraphs(input_graph, sub_graphs, assignments, args.cut_edge_node_size)

    # Read node order file
    filtered_node_order = get_node_order(args.order, args.order_seed, nx.number_of_nodes(input_graph), sub_graphs, assignments)

    # Get size per node
    get_size_per_node(input_graph, sub_graphs, args.node_size_mode, args.node_size, args.min_node_size, args.max_node_size)

    # Generate layout of each sub-graph
    generate_layouts(sub_graphs, nx.union_all(sub_graphs), args.output_dir, args.layout, args.layout_seed,
                     args.force, args.attraction, args.repulsion,
                     args.node_size_mode, args.shadow_color, args.edge_size, args.label_size, args.label_type, cut_edge_length, args.width, args.height)

    # Perform clustering of each sub-graph
    if args.scheme =='communities':
        clusters_per_node_per_graph = perform_clustering(sub_graphs, args.output_dir, args.clustering,
                                                         config['install_dirs']['oslom2'], config['install_dirs']['infomap'],
                                                         args.cluster_seed, args.infomap_calls)
        # Create local-cluster to global-cluster mapping for gvmap to see each cluster independently
        cluster.do_local_to_global_cluster_conversion(clusters_per_node_per_graph)
        if args.clustering != 'graphviz':
            cluster.add_clusters_to_graph(sub_graphs, clusters_per_node_per_graph) # cluster attributes must be omitted for gvmap to perform its own clustering
    else: # cut edges
        clusters_per_node_per_graph = cluster_nodes_per_partition(sub_graphs)
        cluster.add_clusters_to_graph(sub_graphs, clusters_per_node_per_graph)

    # Perform coloring
    perform_coloring(input_graph, sub_graphs, clusters_per_node_per_graph, args.output_dir, config['install_dirs']['gvmap'], args.node_color, args.color_scheme, args.color_seed)

    # Generate frames for each sub-graph
    for index, sub_graph in enumerate(sub_graphs):
        dgs_file = file_io.write_dgs_file(args.output_dir, sub_graph, nx.union_all(sub_graphs), args.label_type, 'fillcolor')
        generate_frames(dgs_file, args.output_dir, index, args.layout, args.layout_seed,
                        args.force, args.attraction, args.repulsion,
                        args.node_size_mode, args.shadow_color, args.edge_size, args.label_size, cut_edge_length, args.width, args.height, 'images') # compute layout from dgs file and write images

    # Combine frames into tiles
    if args.video or args.pdf:
        frame_files_png, frame_files_svg = combine_images_into_tiles(args.output_dir, partitions, args.border_size, args.width, args.height)

    # Convert frames to video
    if args.video:
        create_video_from_tiles(args.output_dir, args.video, args.fps)

    # Convert frames to pdfs
    if args.pdf:
        create_pdfs_from_tiles(args.output_dir, frame_files_svg, args.pdf)

def get_assignments(assignments_file, show_partitions, graph):
    if assignments_file:
        # Extracting assignments from file
        assignments = file_io.read_assignments_file(assignments_file)
        logging.info("%d assignments were found", len(assignments))
        if len(assignments) != nx.number_of_nodes(graph):
            logging.warning("The assignments file doesn't contain the same number of lines than the number of nodes in the graph")
        # Hide partitions according to show_partitions list
        if show_partitions:
            hidden_partitions = list(set(assignments.values()) - set(show_partitions + [-1]))
            logging.info("Filtering out partitions %s not in show-partitions list %s", hidden_partitions, show_partitions)
            assignments = {k:(a if a in show_partitions else -1) for k,a in assignments.items()}
    else:
        # Add all nodes to a single partition
        assignments = {v+1:0 for v in xrange(nx.number_of_nodes(graph))}
    return assignments

def get_hidden_nodes(sub_graphs):
    hidden_nodes = []
    for sub_graph in sub_graphs:
        for node in sub_graph.nodes():
            if 'hidden' in sub_graph.nodes[node]:
                hidden_nodes.append((node, sub_graph.nodes[node]['connect']))
    return hidden_nodes

def get_node_order(order_file, order_seed, total_node_count, sub_graphs, assignments):
    ''' Return ordered list of node IDs '''
    if order_file:
        # Extracting node order from file
        node_order = file_io.read_order_file(order_file)
        logging.info("%d node orders were found", len(node_order))
        if len(node_order) != total_node_count:
            logging.warning("The node order file doesn't contain the same number of lines than the number of nodes in the graph")
    else:
        # Generate random order
        node_order = list(range(1, total_node_count + 1)) # 1 to n
        random.seed(order_seed)
        random.shuffle(node_order)

    # Filter node_order with assignment list
    for node in node_order:
        if assignments[node] == -1:
            node_order.remove(node)

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

    return node_order

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

def split_graph(input_graph, assignments, partitions):
    return graph.create_sub_graphs(input_graph, partitions, assignments)

def is_edge_connected_to_graph(edge, graph):
    return edge[0] in graph.nodes() or edge[1] in graph.nodes()

def is_edge_in_list(edge, edge_list):
    return edge in edge_list or (edge[1], edge[0]) in edge_list # try both permutations

def get_cut_edges(input_graph, sub_graphs):
    sub_graph_edges = list(itertools.chain.from_iterable([sub_graph.edges() for sub_graph in sub_graphs]))
    sub_graph_nodes = list(itertools.chain.from_iterable([sub_graph.nodes() for sub_graph in sub_graphs]))
    cut_edges = [edge for edge in input_graph.edges()
                    if edge[0] in sub_graph_nodes
                    and edge[1] in sub_graph_nodes
                    and not is_edge_in_list(edge, sub_graph_edges)]
    return cut_edges

def get_size_per_node(graph, sub_graphs, node_size_mode, node_size, min_node_size, max_node_size):
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
    for sub_graph in sub_graphs:
        for node in sub_graph.nodes():
            if node in size_per_node:
                sub_graph.nodes[node]['size'] = size_per_node[node]

def get_partitions(assignments):
    unique_assignments = set(assignments.values())
    try:
        unique_assignments.remove(-1) # remove '-1' (node to be excluded)
    except KeyError:
       pass
    return list(unique_assignments)

def log_partitions_info(partitions, assignments):
    logging.info("Found %d partitions in the assignments", len(partitions))
    for partition in partitions:
        logging.info("[Partition %d contains %d nodes]", partition, len([p for _,p in assignments.items() if p == partition]))
    logging.info("[Number of nodes included: %d]", len([p for _,p in assignments.items() if p != -1]))
    logging.info("[Number of nodes excluded: %d]", len([p for _,p in assignments.items() if p == -1]))

def generate_layouts(sub_graphs, full_graph, output_dir, layout, seed, force, attraction, repulsion, node_size_mode, shadow_color, edge_size, label_size, label_type, cut_edge_length, width, height):
    for index, sub_graph in enumerate(sub_graphs):
        dgs_file = file_io.write_dgs_file(output_dir, sub_graph, full_graph, label_type, None)
        dot_filepath = generate_frames(dgs_file, output_dir, index, layout, seed, force, attraction, repulsion, node_size_mode, shadow_color, edge_size, label_size, cut_edge_length, width, height, 'dot') # compute layout from dgs file and write dot file
        pos_per_node = graph.get_node_attribute_from_dot_file(dot_filepath, '"pos"', True, True)
        nx.set_node_attributes(sub_graph, name='pos', values=pos_per_node)

def filter_visible_graph(graph):
    visibe_nodes = [node for node in graph.nodes() if not 'hidden' in graph.nodes[node]]
    return graph.subgraph(visibe_nodes)

def perform_clustering(sub_graphs, output_dir, clustering, oslom2_dir, infomap_dir, cluster_seed, infomap_calls):
    clusters_per_node_per_graph = []
    for index, sub_graph in enumerate(sub_graphs):
        logging.info("Performing clustering (%s) on sub-graph %d", clustering, index)

        sub_graph_without_hidden_nodes = filter_visible_graph(sub_graph)

        clusters_per_node = run_clustering(output_dir, clustering, sub_graph_without_hidden_nodes, index, oslom2_dir, infomap_dir, cluster_seed, infomap_calls)
        if clustering != 'graphviz': # clustering done directly by graphviz
            cluster.create_cluster_for_homeless_nodes(sub_graph_without_hidden_nodes, clusters_per_node) # add homeless nodes cluster
        clusters_per_node_per_graph.append(clusters_per_node)
    return clusters_per_node_per_graph

def run_clustering(output, clustering_method, graph, graph_id, oslom2_dir, infomap_dir, cluster_seed, infomap_calls):
    clusters_per_node = {}
    if graph.number_of_edges() == 0: # oslom2 and infomap do not support graphs with 0 edges
        clusters_per_node = {}
        cluster_index = 1
        for node in graph.nodes():
            clusters_per_node[node] = [cluster_index] # put each node in its own cluster
            cluster_index += 1
    elif clustering_method == 'oslom2':
        oslom_edge_file = file_io.write_oslom_edge_file(output, "oslom_edge_file_{}".format(graph_id), graph)
        cluster.run_oslom2(output, oslom_edge_file, oslom2_dir, cluster_seed, infomap_calls)
        output_tp_file = os.path.join(oslom_edge_file + "_oslo_files", "tp") # or tp1 or tp2 (to be exposed as parameter)
        clusters_per_node = file_io.read_oslom2_tp_file(output_tp_file)
    elif clustering_method == 'infomap':
        pajek_file = file_io.write_pajek_file(output, "pajek_file_{}".format(graph_id), graph)
        cluster.run_infomap(output, pajek_file, infomap_dir, cluster_seed)
        output_tree_file = os.path.splitext(pajek_file)[0]+'.tree'
        level = 1 # lowest hierarchy level
        clusters_per_node = file_io.read_infomap_tree_file(output_tree_file, level) # get cluster(s) from Infomap .tree file
    return clusters_per_node
    
def cluster_nodes_per_partition(sub_graphs):
    full_graph_with_attributes = nx.union_all(sub_graphs)
    clusters_per_node_per_graph = []
    for sub_graph in sub_graphs:
        clusters_per_node = {}
        for node in sub_graph.nodes(data=True):
            if 'hidden' in node[1]: # give hidden node the partition of the external node they represent
                connected_nodes = node[1]['connect']
                external_node = connected_nodes[1] if connected_nodes[0] in sub_graph.nodes() else connected_nodes[0]
                partition = full_graph_with_attributes.nodes[external_node]['partition']
            else:
                partition = node[1]['partition']
            clusters_per_node[node[0]] = [partition]
        clusters_per_node_per_graph.append(clusters_per_node)
    return clusters_per_node_per_graph

def perform_coloring(full_graph, sub_graphs, clusters_per_node_per_graph, output_dir, gvmap_dir, node_color, color_scheme, color_seed):
    if node_color:
        colors_per_node = {node:node_color for node in full_graph.nodes()}
    else:
        # Add width and height attributes (required by gvmap)
        for sub_graph in sub_graphs:
            attributes = {node:0.5 for node in sub_graph.nodes()}
            graph.add_node_attribute_to_graph(sub_graph, 'height', attributes)
            graph.add_node_attribute_to_graph(sub_graph, 'width', attributes)

        # Offset each subgraph to avoid them overlapping (required by gvmap)
        graph.offset_graphs_to_avoid_overlaps(sub_graphs, 5000.0)

        # Merge sub-graphs for gvmap
        merged_graph_dot_filepath = os.path.join(output_dir, 'merged_graph.dot')
        graph.merge_graphs(sub_graphs, merged_graph_dot_filepath)

        # Color nodes with gvmap
        gvmap_dot_file = color.color_nodes_with_gvmap(output_dir, color_scheme, color_seed, merged_graph_dot_filepath, gvmap_dir)

        # Extract colors from gvmap output and update partition graphs
        color_per_node = graph.get_node_attribute_from_dot_file(gvmap_dot_file, 'fillcolor', True, True)
        colors_per_node = color.get_colors_per_node_global(color_per_node, clusters_per_node_per_graph) # combine single color per node (from gvmap) and multiple clusters per node (from OSLOM2) to get multiple colors per node

    # add colors to graphs
    color.add_colors_to_partition_graphs(colors_per_node, sub_graphs)

def generate_frames(dgs_file, output, p, layout, seed, force, a, r, node_size_mode, shadow_color, edge_size, label_size, cut_edge_length, width, height, mode):
    output_dot_filepath = os.path.join(output, 'partition_{}.dot'.format(p))
    out = os.path.join(output, 'frames_partition/p{}_'.format(p))
    if mode == 'dot':
        logging.info("Generating graph layout for DGS file %s and exporting it in dot file %s", dgs_file, output_dot_filepath)
    else:
        logging.info("Generating graph images (%s) for DGS file %s", out, dgs_file)
    args = ['java', '-jar', DGSGS_JAR, '-dgs', dgs_file, '-out', out, '-layout', layout, '-seed', str(seed),
                    '-node_size_mode', node_size_mode, '-edge_size', str(edge_size), '-label_size', str(label_size),
                    '-width', str(width), '-height', str(height), '-cut_edge_length', str(cut_edge_length),
                    '-mode', mode, '-dotfile', output_dot_filepath]
    if force:
        args += ['-force', str(force)]
    if a:
        args += ['-a', str(a)]
    if r:
        args += ['-r', str(r)]
    if shadow_color:
        args += ['-shadow_color', shadow_color]
    logging.debug("dgs-graphstream.jar command: %s", ' '.join(args))
    graphstream_log = os.path.join(output, "graphstream.log")
    with open(graphstream_log, "w") as logwriter:
        retval = subprocess.call(
            args, cwd='.',
            stdout=logwriter,
            stderr=subprocess.STDOUT)
    return output_dot_filepath

def create_png_tiles(tiles, border_size, columns, output_png_file):
    args = ['/usr/bin/montage']
    args += tiles
    args += ['-tile', '{}x'.format(columns) , '-geometry', '+0+0', '-border', str(border_size), output_png_file]
    logging.debug("montage command: %s", ' '.join(args))
    retval = subprocess.call(
        args, cwd='.',
        stderr=subprocess.STDOUT)

def create_svg_tiles(svg_tiles, output_svg_file, width, height, border_size, columns):
    rows = math.ceil(len(svg_tiles) / columns) # number of rows

    # Add tiles
    svg_objects = []
    for index, tile in enumerate(svg_tiles):
        if tile:
            # 0-based row and column
            row = math.floor(index / columns)
            col = index % columns
            # width and height offsets
            width_offset = col * width
            height_offset = row * height
            # add tile with offsets
            svg_objects.append(SVG(tile).move(width_offset, height_offset))

    # Add grid lines
    total_width = width * columns
    total_height = height * rows
    for col in range(0, columns + 1):
        svg_objects.append(Line([(width * col, 0), (width * col, total_height)], width=border_size, color='silver')) # vertical line
    for row in range(0, rows + 1):
        svg_objects.append(Line([(0, height * row), (total_width, height * row)], width=border_size, color='silver')) # horizontal line

    # Create combined svg file from tiles
    Figure(total_width, total_height,
       *svg_objects
       ).save(output_svg_file)

def combine_images_into_tiles(output, partitions, border_size, width, height):
    logging.info("Combining images into tiles")
    partitions_count = len(partitions)

    # get all frames
    frames = {}
    for p in range(0, partitions_count):
        path_glob = os.path.join(output, 'frames_partition', 'p{}_*_new.png'.format(p))
        frames[p] = sorted(glob.glob(path_glob))

    frame_count = max([len(frames[p]) for p in frames]) # max number of frames per partition

    # create output folder
    path_joined = os.path.join(output, 'frames_joined')
    if not os.path.exists(path_joined):
        os.makedirs(path_joined)

    # compute number of rows and columns
    columns = math.ceil(math.sqrt(partitions_count))

    # insert white frames at the start to get the same number of frames per partition
    for p in range(0, partitions_count):
        frames[p] = ['frame_blank.png'] * (frame_count - len(frames[p])) + frames[p]

    frame_files_png = []
    frame_files_svg = []
    f = 0
    for _ in xrange(frame_count):
        try:
            # get all tiles for current frame (one tile per partition)
            tiles = [frames[p][f] for p in range(0, partitions_count)]

            # create png tiles
            png_frame_file = os.path.join(path_joined, 'frame_{0:06d}.png'.format(f))
            frame_files_png.append(png_frame_file)
            create_png_tiles(tiles, border_size, columns, png_frame_file)

            # create svg tiles
            svg_frame_file = os.path.join(path_joined, 'frame_{0:06d}.svg'.format(f))
            frame_files_svg.append(svg_frame_file)
            svg_tiles = [os.path.splitext(tile)[0]+'.svg' for tile in tiles] # replace .png by .svg
            svg_tiles = [svg_tile if os.path.isfile(svg_tile) else '' for svg_tile in svg_tiles ] # replace missing files by blank frames
            create_svg_tiles(svg_tiles, svg_frame_file, width, height, border_size, columns)

            f += 1

        except IndexError:
            print('Missing frame p{}_{}'.format(p, f))

    return frame_files_png, frame_files_svg

def create_video_from_tiles(output_directory, video_file, fps):
    logging.info("Creating video %s from tiles", video_file)
    args = ['ffmpeg', '-framerate', str(fps), '-i', 'output/frames_joined/frame_%6d.png', '-pix_fmt', 'yuv420p', '-r', '10', video_file]
    logging.debug("ffmpeg command: %s", ' '.join(args))
    log_file = os.path.join(output_directory, "ffmpeg.log")
    with open(log_file, "w") as logwriter:
        retval = subprocess.call(args, stdout=logwriter, stderr=subprocess.STDOUT)

def write_png_to_pdf(png_file, output_dir):
    pdf_file = os.path.join(output_dir, os.path.splitext(os.path.basename(png_file))[0]+'_png.pdf')
    pdf = fpdf.FPDF('L', 'mm', 'A4')
    pdf.add_page()
    pdf.image(png_file, w=277) # 277mm width to center image (default margin = 10mm)
    pdf.output(pdf_file, "F")

def write_svg_to_pdf(svg_file, output_dir):
    pdf_file = os.path.join(output_dir, os.path.splitext(os.path.basename(svg_file))[0]+'.pdf')
    drawing = svg2rlg(svg_file)
    renderPDF.drawToFile(drawing, pdf_file)

def create_pdfs_from_tiles(output_dir, frame_files_svg, pdf_percentage):
    pdf_dir = os.path.join(output_dir, 'pdf')
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)
    # filter frames to be converted to pdfs
    step = int(pdf_percentage / 100.0 * len(frame_files_svg))
    logging.info("Exporting every %d frames (every %d%%) as pdf", step, pdf_percentage)
    filtered_frame_files = list(reversed(frame_files_svg))[0::step]
    for frame_file in filtered_frame_files:
        write_png_to_pdf(os.path.splitext(frame_file)[0]+'.png', pdf_dir) # TEMPORARY (for validation)
        write_svg_to_pdf(frame_file, pdf_dir)

if __name__ == '__main__':
    # Initialize logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Parse arguments
    args = parse_arguments()
    validate_arguments(args)

    # Parse config file
    config = parse_config_file('config.ini')
    validate_config(config)

    # Run dgs-graphstream
    run(args, config)

    logging.info("Done")