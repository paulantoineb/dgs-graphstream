#!/usr/bin/env python3

import os
import sys
import glob
import logging
import argparse
import subprocess
import random
import networkx as nx

import file_io
import graph
import color
import cluster
import utils

DGSGS_JAR = 'dgs-graphstream/dist/dgs-graphstream.jar'

def parse_arguments():
    parser = argparse.ArgumentParser(description=
        '''Create animation of network partition assignments. First processes
        network file and assignments into DGS file format, then uses
        GraphStream to animate each frame, finally frames are stitched together.'''
    )
    # Required arguments
    required_group = parser.add_argument_group('required arguments')
    required_group.add_argument('graph',
                        help='input graph file')
    required_group.add_argument('-f', '--format', choices=['metis', 'edgelist'], required=True,
                        help='format of the input graph file')
    required_group.add_argument('-o', '--output_dir', required=True,
                        help='output directory')  
    # Input/output files
    io_group = parser.add_argument_group('input/outputs options')
    
    io_group.add_argument('-a', '--assignments',
                        help='partition assignments list')
    order_group = io_group.add_mutually_exclusive_group()
    order_group.add_argument('-n', '--order',
                        help='node order list')
    order_group.add_argument('--order-seed',
                        help='seed for ordering nodes')        
    # Clustering
    clustering_group = parser.add_argument_group('clustering options')
    clustering_group.add_argument('--clustering', '-c', choices=['oslom2','infomap','graphviz'], default='oslom2',
                        help='clustering method')
    clustering_group.add_argument('--cluster-seed', type=int, metavar='S',
                        help='seed for clustering')
    clustering_group.add_argument('--infomap-calls', type=int, metavar='C',
                        help='number of times infomap is called within oslom2. Good values are between 1 and 10 (default=0)')
    # Layout
    layout_group = parser.add_argument_group('layout options')
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
    coloring_group = parser.add_argument_group('coloring options')
    coloring_group.add_argument('--color-seed', type=int, default=utils.get_random_seed(), metavar='S',
                        help='seed for coloring with gvmap')
    # Image style
    styling_group = parser.add_argument_group('image options')
    styling_group.add_argument('--node-size', type=int, default=10, metavar='S',
                        help='node size in pixels')
    styling_group.add_argument('--edge-size', type=int, default=1, metavar='S',
                        help='edge size in pixels')
    styling_group.add_argument('--label-size', type=int, default=10, metavar='S',
                        help='label size in points')
    styling_group.add_argument('--border-size', type=int, default=1, metavar='S',
                        help='border size between tiles')
    styling_group.add_argument('--width', type=int, default=1280, metavar='W',
                        help='image width')
    styling_group.add_argument('--height', type=int, default=720, metavar='H',
                        help='image height')
    # Video
    video_group = parser.add_argument_group('video options')
    video_group.add_argument('--video',
                        help='output video file with tiled frames')
    video_group.add_argument('--fps', type=int,
                        help='frames per second (default=4)')
    # Pdf
    pdf_group = parser.add_argument_group('pdf options')
    pdf_group.add_argument('--pdf-frequency', type=int, default=1, metavar='F', # TODO
                        help='pdf generation frequency (every F steps)')

    return parser.parse_args()
    
def validate_arguments(args):
    errors = []
    # Clustering
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
        
    if errors:
        for error in errors:
            logging.error(error)
        sys.exit(1)
        
    # Set default values
    if not args.fps:
        args.fps = 4
    if not args.cluster_seed:
        args.cluster_seed = utils.get_random_seed()
    if not args.infomap_calls:
        args.infomap_calls = 0
    
def run(args):
    # Clean output directory
    utils.create_or_clean_output_dir(args.output_dir)

    # Read input graph
    input_graph = file_io.read_graph_from_file(args.graph, args.format)
    logging.info("The input graph contains %d nodes and %d edges", nx.number_of_nodes(input_graph), nx.number_of_edges(input_graph))
      
    # Read assignments and node order files
    assignments = get_assignments(args.assignments, input_graph)
    node_order = get_node_order(args.order, args.order_seed, input_graph)
      
    # Split graph into sub-graphs (one per partition)
    sub_graphs = split_graph(input_graph, assignments)
    
    # Generate layout of each sub-graph
    generate_layouts(sub_graphs, args.output_dir, node_order, args.layout, args.layout_seed, 
                     args.force, args.attraction, args.repulsion, 
                     args.node_size, args.edge_size, args.label_size, args.width, args.height)
     
    # Perform clustering of each sub-graph
    clusters_per_node_per_graph = perform_clustering(sub_graphs, args.output_dir, args.clustering, args.cluster_seed, args.infomap_calls)
        
    # Perform coloring
    perform_coloring(sub_graphs, clusters_per_node_per_graph, args.clustering, args.output_dir, args.color_seed)
    
    # Generate frames for each sub-graph
    for index, sub_graph in enumerate(sub_graphs):       
        dgs_file = file_io.write_dgs_file(args.output_dir, index, sub_graph, node_order, 'fillcolor')    
        generate_frames(dgs_file, args.output_dir, index, args.layout, args.layout_seed, 
                        args.force, args.attraction, args.repulsion,
                        args.node_size, args.edge_size, args.label_size, args.width, args.height, 'images') # compute layout from dgs file and write images
      
    # Combine frames into tiles
    if args.video:
        combine_images_into_tiles(args.output_dir, assignments, len(sub_graphs), args.border_size)
        create_video_from_tiles(args.output_dir, args.video, args.fps)
    
def get_assignments(assignments_file, graph):
    if assignments_file:
        # Extracting assignments from file
        assignments = file_io.read_assignments_file(assignments_file)
        logging.info("%d assignments were found", len(assignments))
        if len(assignments) != nx.number_of_nodes(graph):
            logging.warning("The assignments file doesn't contain the same number of lines than the number of nodes in the graph")
    else:
        # Add all nodes to a single partition
        assignments = [0] * nx.number_of_nodes(graph)
    return assignments
    
def get_node_order(order_file, order_seed, graph):
    if order_file:
        # Extracting node order from file
        node_order = file_io.read_order_file(order_file)
        logging.info("%d node orders were found", len(node_order))
        if len(node_order) != nx.number_of_nodes(graph):
            logging.warning("The node order file doesn't contain the same number of lines than the number of nodes in the graph")
    else:
        # Generate random order
        node_order = list(range(nx.number_of_nodes(graph)))
        random.seed(order_seed)
        random.shuffle(node_order)
    return node_order
    
def split_graph(input_graph, assignments):
    partitions = get_partitions(assignments) # Getting partitions from the assignments
    log_partitions_info(partitions, assignments)
    sub_graphs = graph.create_sub_graphs(input_graph, partitions, assignments)
    return sub_graphs

def get_partitions(assignments):
    unique_assignments = set(assignments)
    try:
        unique_assignments.remove(-1) # remove '-1' (node to be excluded)
    except KeyError:
       pass
    return unique_assignments
    
def log_partitions_info(partitions, assignments):
    logging.info("Found %d partitions in the assignments", len(partitions))
    for partition in partitions:
        logging.info("[Partition %d contains %d nodes]", partition, len([p for p in assignments if p == partition]))
    logging.info("[Number of nodes excluded: %d]", len([p for p in assignments if p == -1]))
    
def generate_layouts(sub_graphs, output_dir, node_order, layout, seed, force, attraction, repulsion, node_size, edge_size, label_size, width, height):
    for index, sub_graph in enumerate(sub_graphs):       
        dgs_file = file_io.write_dgs_file(output_dir, index, sub_graph, node_order, None)            
        dot_filepath = generate_frames(dgs_file, output_dir, index, layout, seed, force, attraction, repulsion, node_size, edge_size, label_size, width, height, 'dot') # compute layout from dgs file and write dot file
        pos_per_node = graph.get_node_attribute_from_dot_file(dot_filepath, '"pos"', True, True) 
        nx.set_node_attributes(sub_graph, name='pos', values=pos_per_node)
    
def perform_clustering(sub_graphs, output_dir, clustering, cluster_seed, infomap_calls):
    clusters_per_node_per_graph = []
    for index, sub_graph in enumerate(sub_graphs):
        logging.info("Performing clustering (%s) on sub-graph %d", clustering, index)
        clusters_per_node = run_clustering(output_dir, clustering, sub_graph, cluster_seed, infomap_calls)
        if clustering != 'graphviz': # clustering done directly by graphviz
            cluster.create_cluster_for_homeless_nodes(sub_graph, clusters_per_node) # add homeless nodes cluster
        clusters_per_node_per_graph.append(clusters_per_node)
    return clusters_per_node_per_graph
    
def run_clustering(output, clustering_method, graph, cluster_seed, infomap_calls):
    clusters_per_node = {}
    if clustering_method == 'oslom2':
        oslom_edge_file = file_io.write_oslom_edge_file(output, "oslom_edge_file", graph)                                                
        cluster.run_oslom2(output, oslom_edge_file, cluster_seed, infomap_calls)
        output_tp_file = os.path.join(oslom_edge_file + "_oslo_files", "tp") # or tp1 or tp2 (to be exposed as parameter)
        clusters_per_node = file_io.read_oslom2_tp_file(output_tp_file)
    elif clustering_method == 'infomap':
        pajek_file = file_io.write_pajek_file(output, "pajek_file", graph)
        cluster.run_infomap(output, pajek_file, cluster_seed)
        output_tree_file = os.path.splitext(pajek_file)[0]+'.tree'
        level = 1 # to be exposed as parameter
        clusters_per_node = file_io.read_infomap_tree_file(output_tree_file, level) # get cluster(s) from Infomap .tree file
    return clusters_per_node
    
def perform_coloring(sub_graphs, clusters_per_node_per_graph, clustering, output_dir, color_seed):
    if clustering != 'graphviz':
        # Create local-cluster to global-cluster mapping for gvmap to see each cluster independently
        cluster.do_local_to_global_cluster_conversion(clusters_per_node_per_graph)
        for index, clusters_per_node in enumerate(clusters_per_node_per_graph):   
            cluster.add_clusters_to_graph(sub_graphs[index], clusters_per_node) 
    
    # Add width and height attributes (required by gvmap)
    for sub_graph in sub_graphs:   
        attributes = {node:0.5 for node in sub_graph.nodes()}
        graph.add_node_attribute_to_graph(sub_graph, 'height', attributes)
        graph.add_node_attribute_to_graph(sub_graph, 'width', attributes)

    # Offset each subgraph to avoid them overlapping (required by gvmap)
    graph.offset_graphs_to_avoid_overlaps(sub_graphs, 50.0)
    
    # Merge sub-graphs for gvmap
    merged_graph_dot_filepath = os.path.join(output_dir, 'merged_graph.dot')
    graph.merge_graphs(sub_graphs, merged_graph_dot_filepath)
    
    # Color nodes with gvmap
    gvmap_dot_file = color.color_nodes_with_gvmap(output_dir, color_seed, merged_graph_dot_filepath)
    
    # Extract colors from gvmap output and update partition graphs
    color.add_colors_to_partition_graphs(gvmap_dot_file, sub_graphs, clusters_per_node_per_graph)
    
def generate_frames(dgs_file, output, p, layout, seed, force, a, r, node_size, edge_size, label_size, width, height, mode):
    output_dot_filepath = os.path.join(output, 'partition_{}.dot'.format(p))
    out = os.path.join(output, 'frames_partition/p{}_'.format(p))
    if mode == 'dot':
        logging.info("Generating graph layout for DGS file %s and exporting it in dot file %s", dgs_file, output_dot_filepath)
    else:
        logging.info("Generating graph images (%s) for DGS file %s", out, dgs_file)
    args = ['java', '-jar', DGSGS_JAR, '-dgs', dgs_file, '-out', out, '-layout', layout, '-seed', str(seed), 
                    '-node_size', str(node_size), '-edge_size', str(edge_size), '-label_size', str(label_size),
                    '-width', str(width), '-height', str(height), 
                    '-mode', mode, '-dotfile', output_dot_filepath]
    if force:
        args += ['-force', str(force)]
    if a:
        args += ['-a', str(a)]
    if r:
        args += ['-r', str(r)]
    logging.debug("dgs-graphstream.jar command: %s", ' '.join(args))
    graphstream_log = os.path.join(output, "graphstream.log")
    with open(graphstream_log, "w") as logwriter:
        retval = subprocess.call(
            args, cwd='.',
            stdout=logwriter,
            stderr=subprocess.STDOUT)
    return output_dot_filepath    

def combine_images_into_tiles(output, assignments, partitions_num, border_size):
    logging.info("Combining images into tiles")
    frames = {}
    frames_max = 0
    for p in range(0, partitions_num):
        path_glob = os.path.join(output, 'frames_partition', 'p{}_*.png'.format(p))
        frames[p] = sorted(glob.glob(path_glob))
        total = len(frames[p])
        if frames_max < total:
            frames_max = total

    path_joined = os.path.join(output, 'frames_joined')
    if not os.path.exists(path_joined):
        os.makedirs(path_joined)

    pframe = [-1] * partitions_num
    tiles = ['frame_blank.png'] * partitions_num

    f = 0
    for a in assignments:
        if a == -1: # XXX remove > 3
            continue

        try:
            pframe[a] += 1
            tiles[a] = frames[a][pframe[a]]

            args = ['/usr/bin/montage']
            args += tiles
            args += ['-geometry', '+0+0', '-border', str(border_size), os.path.join(path_joined, 'frame_{0:06d}.png'.format(f))]
            logging.debug("montage command: %s", ' '.join(args))
            retval = subprocess.call(
                args, cwd='.',
                stderr=subprocess.STDOUT)

            f += 1

        except IndexError:
            print('Missing frame p{}_{}'.format(a, pframe[a]))
            
def create_video_from_tiles(output_directory, video_file, fps):
    logging.info("Creating video %s from tiles", video_file)
    args = ['ffmpeg', '-framerate', str(fps), '-i', 'output/frames_joined/frame_%6d.png', '-pix_fmt', 'yuv420p', '-r', '10', video_file]
    logging.debug("ffmpeg command: %s", ' '.join(args))
    log_file = os.path.join(output_directory, "ffmpeg.log")
    with open(log_file, "w") as logwriter:
        retval = subprocess.call(args, stdout=logwriter, stderr=subprocess.STDOUT) 
      
if __name__ == '__main__':
    # Initialize logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    # Parse arguments
    args = parse_arguments()
    validate_arguments(args)   

    # Run dgs-graphstream
    run(args)

    logging.info("Done")