#!/usr/bin/env python3

import os
import sys
import logging
import argparse
import configparser
import subprocess
import random
import math
import networkx as nx
import nxmetis

import file_io
import graph
import color
import cluster
import utils
import image

DGSGS_JAR = 'dgs-graphstream/dist/dgs-graphstream.jar'

def parse_arguments():
    parent_parser = argparse.ArgumentParser(description=
        '''Create animation of network partition assignments. First processes
        network file and assignments into DGS file format, then uses
        GraphStream to animate each frame, finally frames are stitched together.'''
    )
    parent_parser.add_argument("-v", "--verbose", action="store_true",
                        help="increase output verbosity")

    # Required arguments
    required_group = parent_parser.add_argument_group('required arguments')
    required_group.add_argument('-g', '--graph', required=True,
                        help='input graph file')
    required_group.add_argument('-f', '--format', choices=['metis', 'edgelist', 'gml'], required=True,
                        help='format of the input graph file')
    required_group.add_argument('-o', '--output_dir', required=True,
                        help='output directory')
    # Input/output files
    io_group = parent_parser.add_argument_group('input/outputs options')
    order_group = io_group.add_mutually_exclusive_group()
    order_group.add_argument('-n', '--order',
                        help='node order list')
    order_group.add_argument('--order-seed', type=int, default=utils.get_random_seed(), metavar='S',
                        help='seed for ordering nodes')
    io_group.add_argument('--filter',
                        help='filter node list (<= 0 to exclude node)')
    io_group.add_argument('--node-weight', default='weight', metavar='W',
                        help='attribute used to determine the weight of each node (default=\'weight\')')
    io_group.add_argument('--edge-weight', default='weight', metavar='W',
                        help='attribute used to determine the weight of each edge (default=\'weight\')')
    # Partitioning
    partitioning_group = parent_parser.add_argument_group('partitioning options')
    partitioning_type_group = partitioning_group.add_mutually_exclusive_group()
    partitioning_type_group.add_argument('-a', '--assignments',
                        help='partition assignments list')
    partitioning_type_group.add_argument("--random-assignments", action="store_true",
                        help="generate random assignments")
    partitioning_group.add_argument('--partition-seed', type=int, default=utils.get_random_seed(), metavar='S',
                        help='seed for random assignments partitioning')
    partitioning_group.add_argument('--nparts', type=int, metavar='P',
                        help='number of partitions to generate with METIS')
    partitioning_group.add_argument('--ubvec', type=float, metavar='U',
                        help='allowed load imbalance among partitions in METIS (default=1.001). The load imbalance must be greater than 1.0, 1.2 indicates a desired maximum load imbalance of 20 percents.')
    partitioning_group.add_argument('--tpwgts', nargs='+', type=float, metavar='T',
                        help='desired weight for each partition in METIS. The sum of tpwgts[] must be 1.0')
    partitioning_group.add_argument('--show-partitions', nargs='+', type=int,
                        help='partitions to be displayed (based on nparts or partition values in assignments list)')
    # Layout
    layout_group = parent_parser.add_argument_group('layout options')
    layout_group.add_argument('--layout', '-l', choices=['springbox','linlog'], default='springbox',
                        help='graph layout')
    layout_group.add_argument('--layout-seed', type=int, default=utils.get_random_seed(), metavar='S',
                        help='seed for graph layout')
    layout_group.add_argument('--force', type=float, metavar='F',
                        help='force for linlog graph layout (default=3.0)')
    layout_group.add_argument('--attraction', type=float, metavar='A',
                        help='attraction factor for graph layout (default=0.06 for springbox, default=0.0 for linlog)')
    layout_group.add_argument('--repulsion', type=float, metavar='R',
                        help='repulsion factor for graph layout (default=0.024 for springbox, default=-1.2 for linlog)')
    # Coloring
    coloring_group = parent_parser.add_argument_group('coloring options')
    color_mode_group = coloring_group.add_mutually_exclusive_group()
    color_mode_group.add_argument('--color-scheme', choices=['pastel', 'primary-colors'], default='pastel',
                        help='color scheme used by gvmap (default=pastel)')
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
                        help='node size in pixels (default=20). Use with --node-size-mode fixed.')
    styling_group.add_argument('--min-node-size', type=int, metavar='S',
                        help='minimum node size in pixels (default=20). Use with --node-size-mode centrality or highlight-new.')
    styling_group.add_argument('--max-node-size', type=int, metavar='S',
                        help='maximum node size in pixels (default=60). Use with --node-size-mode centrality or highlight-new.')
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
    video_group.add_argument('--padding-time', type=float,
                        help='padding time in seconds to add extra frames at the end of the video (default=2.0)')
    # Pdf
    pdf_group = parent_parser.add_argument_group('pdf options')
    pdf_group.add_argument('--pdf', type=int, default=20, metavar='P',
                        help='Percentage of frames to convert to pdf (default=20)')

    # Scheme
    scheme_group = parent_parser.add_argument_group('scheme option')
    scheme_group.add_argument('-s', '--scheme', choices=['communities', 'cut-edges'], default='communities',
                    help='scheme to highlight either communities or cut edges (default=communities)')

    # Clustering
    clustering_group = parent_parser.add_argument_group('communities options (only for scheme=communities)')
    clustering_group.add_argument('--clustering', '-c', choices=['oslom2','infomap','graphviz'],
                        help='clustering method (default=oslom2)')
    clustering_group.add_argument('--cluster-seed', type=int, metavar='S',
                        help='seed for clustering')
    clustering_group.add_argument('--infomap-calls', type=int, metavar='C',
                        help='number of times infomap is called within oslom2. Good values are between 1 and 10 (default=0)')

    # Cut edges
    cut_edges_group = parent_parser.add_argument_group('cut-edges options (only for scheme=cut-edges)')
    cut_edges_group.add_argument('--cut-edge-length', type=int, metavar='L',
                        help='length of cut edges as percentage of original length (default=50)')
    cut_edges_group.add_argument('--cut-edge-node-size', metavar='S',
                        help='size of the nodes attached to cut edges (default=10)')

    return parent_parser.parse_args()

def validate_arguments(args):
    # Initialize the logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    errors = []
    # Partitioning
    if not args.assignments:
        if args.nparts == None:
            errors.append("--nparts is required when not using --assignments")
        if not args.tpwgts:
            errors.append("--tpwgts is required when not using --assignments")
        if args.random_assignments:
            if args.nparts != None and args.nparts <= 0:
                errors.append("The --nparts value must be strictly positive")
        else:
            if args.nparts != None and args.nparts <= 1:
                errors.append("The --nparts value must be greater than 1")
        if args.ubvec != None and args.nparts == None:
            errors.append("The --ubvec option is only available with the --nparts option")
        if args.ubvec != None and args.ubvec <= 1.0:
            errors.append("The --ubvec value must be greater than 1.0")
        if args.tpwgts and not args.nparts:
            errors.append("The --tpwgts option is only available with the --nparts option")
        if args.tpwgts and args.nparts and len(args.tpwgts) != args.nparts:
            errors.append("The --tpwgts option requires a list of {} values (one value per partition)".format(args.nparts))
        if args.tpwgts and not math.isclose(sum(args.tpwgts), 1.0, rel_tol=1e-5):
            errors.append("The sum of --tpwgts values must be 1.0 (currently {})".format(sum(args.tpwgts)))
    # Clustering
    if args.scheme == 'communities':
        if args.clustering and args.clustering == 'graphviz' and args.cluster_seed:
            errors.append("The --cluster-seed option is not available with the graphviz clustering method")
        if args.clustering and args.clustering != 'oslom2' and args.infomap_calls:
            errors.append("The --infomap-calls option is only available with the oslom2 clustering method")
        if args.cut_edge_length:
            errors.append("The --cut-edge-length option is only available with the cut-edges scheme")
        if args.cut_edge_node_size:
            errors.append("The --cut-edge-node-size option is only available with the cut-edges scheme")
    # Cut edges
    if args.scheme == 'cut-edges':
        if args.cut_edge_length and (args.cut_edge_length < 0 or args.cut_edge_length > 100):
            errors.append("The --cut-edge-length value must be between 0 and 100")
        if args.clustering:
            errors.append("The --clustering option is only available with the communities scheme")
        if args.cluster_seed:
            errors.append("The --cluster-seed option is only available with the communities scheme")
        if args.infomap_calls:
            errors.append("The --infomap-calls option is only available with the communities scheme")
    # Layout
    if args.layout != 'linlog' and args.force:
        errors.append("The --force option is only available with the linlog layout")
    if not args.video and args.fps:
        errors.append("The --fps option is only available with the --video option")
    if not args.video and args.padding_time:
        errors.append("The --padding-time option is only available with the --video option")
    # Image style
    if args.node_size and args.node_size_mode != 'fixed':
        errors.append("The --node-size option is only available with --node-size-mode fixed")
    if args.min_node_size and args.node_size_mode == 'fixed':
        errors.append("The --min-node-size option is only available with --node-size-mode centrality or highlight-new")
    if args.max_node_size and args.node_size_mode == 'fixed':
        errors.append("The --max-node-size option is only available with --node-size-mode centrality or highlight-new")

    # Print errors and exit if any error found
    if errors:
        for error in errors:
            logging.error(error)
        sys.exit(1)

    # Set default values
    if args.layout == 'springbox':
        if not args.attraction:
            args.attraction = 0.012
        if not args.repulsion:
            args.repulsion = 0.024
    elif args.layout == 'linlog':
        if not args.attraction:
            args.attraction = 0.0
        if not args.repulsion:
            args.repulsion = -1.2
    if not args.fps:
        args.fps = 8
    if not args.padding_time:
        args.padding_time = 2.0
    if not args.node_size:
        args.node_size = 20
    if not args.min_node_size:
        args.min_node_size = 20
    if not args.min_node_size:
        args.max_node_size = 60
    if args.scheme == 'communities':
        if not args.clustering:
            args.clustering = 'oslom2'
        if not args.cluster_seed:
            args.cluster_seed = utils.get_random_seed()
        if not args.infomap_calls:
            args.infomap_calls = 0
    if args.scheme == 'cut-edges':
        if not args.cut_edge_length:
            args.cut_edge_length = 50
        if not args.cut_edge_node_size:
            args.cut_edge_node_size = 5
    if not args.cut_edge_length:
        args.cut_edge_length = 0 # to avoid passing None to Graphstream
    if not args.ubvec:
        args.ubvec = 1.0

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
    assignments = get_assignments(args.assignments, args.random_assignments, args.show_partitions, args.filter, args.order, input_graph, args.nparts, args.ubvec, args.tpwgts, args.node_weight, args.edge_weight, args.partition_seed)
    partitions = get_partitions(assignments) # Getting partitions from the assignments
    log_partitions_info(partitions, assignments)

    # Split graph into sub-graphs (one per partition)
    sub_graphs = split_graph(input_graph, assignments, partitions, args.scheme, args.order, args.order_seed, args.node_size_mode, args.node_size, args.min_node_size, args.max_node_size, args.cut_edge_node_size)

    # Generate layout of each sub-graph
    padding_frame_count = math.ceil(args.padding_time * args.fps)
    generate_layout_per_subgraph(sub_graphs, nx.union_all(sub_graphs), args.output_dir, args.layout, args.layout_seed,
                     args.force, args.attraction, args.repulsion,
                     args.node_size_mode, args.shadow_color, args.edge_size, args.label_size, args.label_type, args.cut_edge_length, args.width, args.height, padding_frame_count)

    # Perform clustering of each sub-graph
    clusters_per_node_per_graph = create_clusters(sub_graphs, args.output_dir, args.scheme, args.clustering, args.cluster_seed, args.infomap_calls)

    # Perform coloring
    perform_coloring(sub_graphs, clusters_per_node_per_graph, args.output_dir, config['install_dirs']['gvmap'], args.node_color, args.color_scheme, args.color_seed)

    # Generate frames for each sub-graph
    create_dgs_file_and_generate_frames(args.output_dir, sub_graphs, nx.union_all(sub_graphs), args.label_type, 'fillcolor', padding_frame_count,
                                        args.layout, args.layout_seed, args.force, args.attraction, args.repulsion, args.node_size_mode, args.shadow_color,
                                        args.edge_size, args.label_size, args.cut_edge_length, args.width, args.height, 'images')

    # Combine frames into tiles
    if args.video or args.pdf:
        frame_files_png, frame_files_svg = image.combine_images_into_tiles(args.output_dir, partitions, args.border_size, args.width, args.height, args.fps)

    # Convert frames to video
    if args.video:
        create_video_from_tiles(args.output_dir, args.video, args.fps)

    # Convert frames to pdfs
    if args.pdf:
        image.create_pdfs_from_tiles(args.output_dir, frame_files_svg, args.pdf)

def get_assignments_from_file(assignments_file, graph):
    # Extracting assignments from file
    assignments = file_io.read_assignments_file(assignments_file)
    logging.info("%d assignments were found", len(assignments))
    if len(assignments) != nx.number_of_nodes(graph):
        logging.warning("The assignments file doesn't contain the same number of lines than the number of nodes in the graph")
    return assignments

def filter_graph(graph, filter_file):
    if not filter_file:
        return graph
    # Extracting filtered nodes from file
    filter_values = file_io.read_filter_file(filter_file)
    if len(filter_values) != nx.number_of_nodes(graph):
        logging.warning("The filter file doesn't contain the same number of lines than the number of nodes in the graph")
    filtered_nodes = [n for n,p in filter_values.items() if p > 0]
    # Filtering graph
    filtered_graph = graph.subgraph(filtered_nodes)
    return filtered_graph

def get_assignments_from_metis(graph, filter_file, nparts, ubvec, tpwgts, node_weight, edge_weight):
    filtered_graph = filter_graph(graph, filter_file)
    # Run partitioning with METIS
    assignments = run_metis_partitioning(filtered_graph, nparts, ubvec, tpwgts, node_weight, edge_weight)
    add_excluded_nodes_to_assignments(graph, assignments)
    return assignments

def add_excluded_nodes_to_assignments(graph, assignments):
    for node in graph.nodes():
        if not node in assignments:
            assignments[node] = -1

def splitting_nodes_into_partitions(node_count, tpwgts):
    quota = [v * node_count for v in tpwgts]
    truncated_quota = [math.floor(v) for v in quota]
    remainders_and_quotas = [(quota_i - truncated_quota_i, quota_i) for quota_i, truncated_quota_i in zip(quota, truncated_quota)]
    sorted_remainder_indexes = [i[0] for i in sorted(enumerate(remainders_and_quotas), key=lambda x:x[1], reverse=True)] # sort remainders by descending remainders first and by descending quota second
    missing_node_count = node_count - sum(truncated_quota) # number of missing nodes due to truncation
    partition_sizes = truncated_quota
    for i in xrange(missing_node_count): # iterate over number of missing nodes
        partition_sizes[sorted_remainder_indexes[i]] += 1 # increment quota of selected partition
    return partition_sizes

def get_begin_end_node_indexes(partition_sizes):
    begin_end_node_indexes = []
    node_index = 0
    for partition_size in partition_sizes:
        begin_end_node_indexes.append((node_index, node_index + partition_size)) # add (begin, end) indexes to list
        node_index += partition_size
    return begin_end_node_indexes

def get_random_node_buckets(node_count, partition_sizes, partition_seed):
    nodes = list(range(node_count))
    random.seed(partition_seed)
    random.shuffle(nodes) # shuffle the nodes
    random.shuffle(partition_sizes) # shuffle the partition sizes
    begin_end_node_indexes = get_begin_end_node_indexes(partition_sizes)
    return [nodes[begin:end] for begin, end in begin_end_node_indexes]

def get_assignments_from_buckets(node_buckets):
    assignments = {}
    for partition, nodes in enumerate(node_buckets):
        for node in nodes:
            assignments[node] = partition
    return assignments

def generate_random_assignments(graph, filter_file, nparts, tpwgts, partition_seed):
    filtered_graph = filter_graph(graph, filter_file)
    node_count = nx.number_of_nodes(filtered_graph)
    logging.info("Generating random assignments of %d nodes into %d partitions (tpwgts=%s)", node_count, nparts, tpwgts)
    partition_sizes = splitting_nodes_into_partitions(node_count, tpwgts)
    logging.info("Splitting nodes into partitions of sizes %s", partition_sizes)
    node_buckets = get_random_node_buckets(node_count, partition_sizes, partition_seed)
    assignments = get_assignments_from_buckets(node_buckets)
    add_excluded_nodes_to_assignments(graph, assignments)
    return assignments

def get_assignments(assignments_file, random_assignments, show_partitions, filter_file, order_file, graph, nparts, ubvec, tpwgts, node_weight, edge_weight, partition_seed):
    # Get assignments
    if assignments_file:
        assignments = get_assignments_from_file(assignments_file, graph)
    elif random_assignments:
        assignments = generate_random_assignments(graph, filter_file, nparts, tpwgts, partition_seed)
    else:
        assignments = get_assignments_from_metis(graph, filter_file, nparts, ubvec, tpwgts, node_weight, edge_weight)
    # Hide partitions in assignments according to show_partitions list
    if show_partitions:
        hidden_partitions = list(set(assignments.values()) - set(show_partitions + [-1]))
        logging.info("Filtering out partitions %s not in show-partitions list %s", hidden_partitions, show_partitions)
        assignments = {k:(a if a in show_partitions else -1) for k,a in assignments.items()}
    return assignments

def run_metis_partitioning(graph, nparts, ubvec, tpwgts, node_weight, edge_weight):
    # Format metis parameters
    if tpwgts != None:
        tpwgts=[[val] for val in tpwgts]
    ubvec=[ubvec]
    # Run metis
    logging.info("Partitioning the graph using METIS (nparts=%s, ubvec=%s, tpwgts=%s, node_weight=%s, edge_weight=%s)", nparts, ubvec, tpwgts, node_weight, edge_weight)
    output = nxmetis.partition(graph, nparts, node_weight=node_weight, edge_weight=edge_weight, tpwgts=tpwgts, ubvec=ubvec)
    objval = output[0]
    partitions = output[1]
    logging.info("The graph was partitioned into %s partitions by METIS (objval=%s)", len(partitions), objval)
    # Create assignments
    assignments = {}
    for index, partition in enumerate(partitions):
        for node in partition:
            assignments[node] = index # node IDs start at 0, partition IDs start at 0
    return assignments

def filter_node_order(node_order, assignments):
    ''' Filter node_order with assignment list '''
    for node in node_order:
        if assignments[node] == -1:
            node_order.remove(node)

def get_node_order(order_file, order_seed, total_node_count):
    if order_file:
        # Extracting node order from file
        node_order = file_io.read_order_file(order_file)
        logging.info("%d node orders were found", len(node_order))
        if len(node_order) != total_node_count:
            logging.warning("The node order file doesn't contain the same number of lines than the number of nodes in the graph")
    else:
        # Generate random order
        node_order = list(range(total_node_count)) # 0 to n-1
        random.seed(order_seed)
        random.shuffle(node_order)
    return node_order

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

def split_graph(input_graph, assignments, partitions, scheme, order, order_seed, node_size_mode, node_size, min_node_size, max_node_size, cut_edge_node_size):
    # Create one subgraph per partition
    sub_graphs = graph.create_sub_graphs(input_graph, partitions, assignments)

    # Add cut edges to subgraphs
    if scheme == 'cut-edges':
        graph.add_cut_edges_to_subgraphs(input_graph, sub_graphs, assignments, cut_edge_node_size)

    # Add node order to subgraphs
    node_order = get_node_order(order, order_seed, nx.number_of_nodes(input_graph))
    filter_node_order(node_order, assignments) # remove entries from node order that are excluded in assignments
    graph.add_node_order_to_subgraphs(sub_graphs, node_order)

    # Add node size to subgraphs
    graph.add_node_size_to_subgraphs(input_graph, sub_graphs, node_size_mode, node_size, min_node_size, max_node_size)

    return sub_graphs

def generate_layout_per_subgraph(sub_graphs, full_graph, output_dir, layout, seed, force, attraction, repulsion, node_size_mode, shadow_color,
                                 edge_size, label_size, label_type, cut_edge_length, width, height, trailing_frame_count):

    dot_filepaths = create_dgs_file_and_generate_frames(output_dir, sub_graphs, full_graph, label_type, None, trailing_frame_count,
                                                       layout, seed, force, attraction, repulsion, node_size_mode, shadow_color, edge_size,
                                                       label_size, cut_edge_length, width, height, 'dot')

    # Extract node positions from dot files
    for index, sub_graph in enumerate(sub_graphs):
        pos_per_node = graph.get_node_attribute_from_dot_file(dot_filepaths[index], '"pos"', True, True)
        nx.set_node_attributes(sub_graph, name='pos', values=pos_per_node)

def create_dgs_file_and_generate_frames(output_dir, sub_graphs, full_graph, label_type, colour_attr, trailing_frame_count,
                                        layout, seed, force, attraction, repulsion, node_size_mode, shadow_color, edge_size, label_size, cut_edge_length, width, height, mode):
    dot_filepaths = []
    for index, sub_graph in enumerate(sub_graphs):
        dgs_file = file_io.write_dgs_file(output_dir, sub_graph, full_graph, label_type, colour_attr, trailing_frame_count)
        dot_filepath = generate_frames(dgs_file, output_dir, index, layout, seed, force, attraction, repulsion, node_size_mode,
                                       shadow_color, edge_size, label_size, cut_edge_length, width, height, mode)
        dot_filepaths.append(dot_filepath)
    return dot_filepaths

def create_clusters(sub_graphs, output_dir, scheme, clustering, cluster_seed, infomap_calls):
    clusters_per_node_per_graph = []
    if scheme == 'communities' and clustering != 'graphviz': # gvmap performs its own clustering if clustering=graphviz
        clusters_per_node_per_graph = perform_clustering(sub_graphs, output_dir, clustering,
                                                         config['install_dirs']['oslom2'], config['install_dirs']['infomap'],
                                                         cluster_seed, infomap_calls)
        # Create local-cluster to global-cluster mapping for gvmap to see each cluster independently
        cluster.do_local_to_global_cluster_conversion(clusters_per_node_per_graph)
    elif scheme =='cut-edges':
        clusters_per_node_per_graph = cluster.cluster_nodes_per_partition(sub_graphs)

    # Add clusters to graph as node attributes
    if clusters_per_node_per_graph:
        cluster.add_clusters_to_graph(sub_graphs, clusters_per_node_per_graph)

    return clusters_per_node_per_graph

def perform_clustering(sub_graphs, output_dir, clustering, oslom2_dir, infomap_dir, cluster_seed, infomap_calls):
    clusters_per_node_per_graph = []
    for index, sub_graph in enumerate(sub_graphs):
        logging.info("Performing clustering (%s) on sub-graph %d", clustering, index)

        sub_graph_without_hidden_nodes = graph.filter_visible_graph(sub_graph)

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

def perform_coloring(sub_graphs, clusters_per_node_per_graph, output_dir, gvmap_dir, node_color, color_scheme, color_seed):
    if node_color:
        colors_per_node = {node:node_color for node in nx.union_all(sub_graphs).nodes()}
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
    graph.add_node_attribute_to_subgraphs(sub_graphs, 'fillcolor', colors_per_node)

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

def create_video_from_tiles(output_directory, video_file, fps):
    logging.info("Creating video %s from tiles", video_file)
    args = ['ffmpeg', '-framerate', str(fps), '-i', 'output/frames_joined/frame_%6d.png', '-pix_fmt', 'yuv420p', '-r', '10', video_file]
    logging.debug("ffmpeg command: %s", ' '.join(args))
    log_file = os.path.join(output_directory, "ffmpeg.log")
    with open(log_file, "w") as logwriter:
        retval = subprocess.call(args, stdout=logwriter, stderr=subprocess.STDOUT)

if __name__ == '__main__':
    # Initialize logging
    #logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Parse arguments
    args = parse_arguments()
    validate_arguments(args)

    # Parse config file
    config = parse_config_file('config.ini')
    validate_config(config)

    # Run dgs-graphstream
    run(args, config)

    logging.info("Done")