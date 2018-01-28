package dgsgraphstreamanimate;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.lang.reflect.Field;
import org.graphstream.graph.Node;
import org.graphstream.graph.Edge;
import org.graphstream.graph.implementations.DefaultGraph;
import org.graphstream.stream.ProxyPipe;
import org.graphstream.stream.file.FileSourceDGS;
import org.graphstream.stream.file.FileSinkImages;
import org.graphstream.stream.file.FileSinkImages.Quality;
import org.graphstream.stream.file.FileSinkImages.Resolutions;
import org.graphstream.stream.file.FileSinkImages.OutputType;
import org.graphstream.stream.file.FileSinkImages.OutputPolicy;
import org.graphstream.stream.file.FileSinkImages.LayoutPolicy;
import org.graphstream.stream.file.FileSinkImages.RendererType;
import org.graphstream.stream.file.FileSinkImages.CustomResolution;
import org.graphstream.stream.file.FileSinkDOT;
import org.graphstream.stream.SinkAdapter;
import org.graphstream.ui.layout.springbox.implementations.LinLog;
import org.graphstream.ui.layout.springbox.implementations.SpringBox;
import org.graphstream.ui.layout.springbox.BarnesHutLayout ;
import org.graphstream.ui.view.Viewer;
import org.graphstream.ui.graphicGraph.GraphicGraph;
import org.graphstream.ui.graphicGraph.GraphicNode;

/**
 *
 * @author Sami Barakat
 */
public class DgsGraphStreamAnimate extends SinkAdapter {

    private DefaultGraph g;
    private FileSinkImages fsi;
    private ProxyPipe pipe;
    private BarnesHutLayout layout;
    private int nodeSize;
    private int edgeSize;
    private int labelSize;
    
    private enum LayoutType {
        LinLog,
        SpringBox
    }
    
    private enum Mode {
        Images,
        DotFile
    }
        
    private void AnimateDgs(String inputDGS, String outputDirectory, LayoutType layout_type, Mode mode, String outputDotFilepath, 
                            long seed, float force, float a, float r, float theta, 
                            int nodeSize, int edgeSize, int labelSize, int width, int height, Boolean display)
            throws java.io.IOException {

        System.setProperty("org.graphstream.ui.renderer","org.graphstream.ui.j2dviewer.J2DGraphRenderer");
        
        FileSourceDGS dgs = new FileSourceDGS();
        
        this.g = new DefaultGraph("graph");
        this.g.addAttribute("ui.stylesheet", "url('style.css')"); 
        
        this.nodeSize = nodeSize;
        this.edgeSize = edgeSize;
        this.labelSize = labelSize;
        
        layout = CreateLayout(layout_type, seed, force, a, r, theta);
        
        fsi = new FileSinkImages("frame_", OutputType.PNG, new CustomResolution(width, height), OutputPolicy.NONE);
        fsi.setOutputPolicy(OutputPolicy.BY_STEP);
        fsi.setLayoutPolicy(LayoutPolicy.NO_LAYOUT);
        fsi.setQuality(Quality.HIGH);
        fsi.setRenderer(RendererType.SCALA);
        fsi.setStyleSheet("url('style.css')");
        
        // chain: dgs -> g -> layout -> fsi
        dgs.addSink(this.g);
        this.g.addSink(layout);
        layout.addAttributeSink(this.g);
        layout.addSink(fsi);

        dgs.addSink(this);

        Viewer viewer = null;
        
        if (display) {
            viewer = this.g.display();
            viewer.enableAutoLayout(layout);
            //pipe = viewer.newViewerPipe();
            pipe = viewer.newThreadProxyOnGraphicGraph();
        }
        
        if (mode == Mode.Images) {
            fsi.begin(outputDirectory);
            try {
                dgs.begin(inputDGS);
                while (dgs.nextEvents()) {
                    
                    layout.compute();

                    if (display) {
                        pipe.pump();
                    }
                }    
                dgs.end();
                fsi.end();
            } catch (IOException e1) {
                e1.printStackTrace();
                System.exit(1);
            }
        } else { // DotFile
            try {
                dgs.begin(inputDGS);
                while (dgs.nextEvents()) {              
                    layout.compute();
                } 
                fsi.begin(outputDirectory); // Get last layout to propagate to fsi without generating any image file
                fsi.end();              
                dgs.end();              
            } catch (IOException e1) {
                e1.printStackTrace();
                System.exit(1);
            }       
            
            try {
                exportGraphAsDotFile(this.g, getGraphicGraph(fsi), outputDotFilepath);
            } catch (Exception e) {
                e.printStackTrace();
                System.exit(1);
            }
        }
    }
    
    /**
     * Create graph layout
     */
    private BarnesHutLayout CreateLayout(LayoutType layout_type, long seed, float force, float a, float r, float theta) {
        if (layout_type == LayoutType.LinLog) {
            LinLog layout = new LinLog(false, new Random(seed));

            layout.configure(a, r, true, force);
            layout.setQuality(1);
            layout.setBarnesHutTheta(theta);
            //layout.setStabilizationLimit(0);
            
            return layout;
        } else {
            SpringBox layout = new SpringBox(false, new Random(seed));
            layout.setQuality(1);
            return layout;
        }
    }
    
    /**
     * Export graph as Graphviz dot file
     */
    private void exportGraphAsDotFile(DefaultGraph graph, GraphicGraph graphicGraph, String outputFilePath) throws IOException {          
        // Add position attribute to DefaultGraph from GraphicGraph
        for (Node node : graph) {
            GraphicNode graphics_graph_node = graphicGraph.getNode(node.getId());
            node.addAttribute("pos", graphics_graph_node.x*100+","+graphics_graph_node.y*100);
            node.addAttribute("height", 0.5);
            node.addAttribute("width", 0.5);
        }
        // Export graph as dot file 
        FileSinkDOT dot_sink = new FileSinkDOT();
        dot_sink.writeAll(graph, outputFilePath); 
    }
    
    /**
     * Get GraphicGraph instance from FileSinkImages (only place where to get a node's position)
     */
    private GraphicGraph getGraphicGraph(FileSinkImages fsi) throws NoSuchFieldException, IllegalAccessException {
        Field field = getField(fsi.getClass(), "gg");
        field.setAccessible(true);
        return (GraphicGraph)field.get(fsi);
    }
    
    /**
     * Get class field using reflection
     */
    private static Field getField(Class clazz, String fieldName) throws NoSuchFieldException {
        try {
            return clazz.getDeclaredField(fieldName);
        } catch (NoSuchFieldException e) {
            Class superClass = clazz.getSuperclass();
            if (superClass == null) {
                throw e;
            } else {
                return getField(superClass, fieldName);
            }
        }
    }
    
    @Override
    public void nodeAttributeChanged(String sourceId, long timeId,
                    String nodeId, String attribute, Object oldValue, Object newValue) {

        if (attribute.equals("c")) {
            Node n = this.g.getNode(nodeId);
            

            int count = newValue.toString().length() - newValue.toString().replace(",", "").length() + 1;
            float share = 1.0f / (float)count;
            float[] pie_values = new float[count];
            Arrays.fill(pie_values, share);

            n.setAttribute("ui.style", "shape: pie-chart; fill-color: " + newValue.toString() + ";");
            n.setAttribute("ui.pie-values", pie_values);
        }
    }
    
    public void nodeAdded(String sourceId, long timeId, String nodeId) {
        Node n = this.g.getNode(nodeId);
        n.setAttribute("ui.size", this.nodeSize);
        if (this.labelSize > 0) {
            n.addAttribute("text-size", this.labelSize);
            n.addAttribute("label", nodeId);
        }
    }        
    
    public void edgeAdded(String sourceId, long timeId, String edgeId,
            String fromNodeId, String toNodeId, boolean directed) {
        Edge e = this.g.getEdge(edgeId);
        Node source_node = this.g.getNode(fromNodeId);
        String style_attr = source_node.getAttribute("ui.style");
        if (style_attr != null) {
            e.setAttribute("ui.style", style_attr.split(";")[1] + ";");
        }
        e.setAttribute("ui.size", this.edgeSize);
    }
    
    public static void main(String[] args) {
        
        Map<String, List<String>> params = new HashMap<>();
        List<String> options = null;

        for (String a : args) {
            if (a.charAt(0) == '-' && Character.isLetter(a.charAt(1))) {
                if (a.length() < 2) {
                    System.err.println("Error at argument " + a);
                    return;
                }

                options = new ArrayList<>();
                params.put(a.substring(1), options);
            }
            else if (options != null) {
                options.add(a);
            }
            else {
                System.err.println("Illegal parameter usage");
                return;
            }
        }
        
        Boolean error = false;
        if (!params.containsKey("dgs")) {
            System.out.println("Missing required option: -dgs\n");
            error = true;
        }
        if (!params.containsKey("out")) {
            System.out.println("Missing required option: -out\n");
            error = true;
        }
        if (error || params.containsKey("help") || params.containsKey("h")) {
            System.out.println("usage: DgsGraphStreamAnimate.jar [OPTIONS]...");
            System.out.println("-dgs <arg>          input GraphStream DGS file");
            System.out.println("-out <arg>          frame filenames are prepended with this path");
            System.out.println("-layout <arg>       layout type to use. options: [springbox|linlog]. default: springbox");
            System.out.println("-seed <arg>         random seed for the layout");
            System.out.println("-force <arg>        force for LinLog layout");
			System.out.println("-a <arg>            attraction factor for LinLog layout");
			System.out.println("-r <arg>            repulsion factor for LinLog layout");
            System.out.println("-theta <arg>        theta for LinLog layout");
            System.out.println("-node_size <arg>    node size");
            System.out.println("-edge_size <arg>    edge size");
            System.out.println("-width <arg>        image width");
            System.out.println("-height <arg>       image height");
            System.out.println("-mode <arg>         mode. options: [images|dot]. default: images");
            System.out.println("-dotfile <arg>      output dot file");          
            System.out.println("-display screen     layout option to use. options: [screen]");
            System.out.println("-h,-help            display this help and exit");
            System.exit(1);
        }
        
        LayoutType layout_type = LayoutType.SpringBox;      
        if (params.containsKey("layout") && params.get("layout").get(0).equals("linlog")) {
            layout_type = LayoutType.LinLog;
        }
        Mode mode = Mode.Images;      
        if (params.containsKey("mode") && params.get("mode").get(0).equals("dot")) {
            mode = Mode.DotFile;
        }
        Boolean display = false;
        if (params.containsKey("display") && params.get("display").get(0).equals("screen")) {
            display = true;
        }
        long seed = System.currentTimeMillis(); // random seed
        if (params.containsKey("seed")) {
            seed = Long.parseLong(params.get("seed").get(0));
        }
        float force = 3.0f; // default force value for LinLog layout
        if (params.containsKey("force")) {
            force = Float.parseFloat(params.get("force").get(0));
        }
		float a = 0f; // default attraction value for LinLog layout
        if (params.containsKey("a")) {
            a = Float.parseFloat(params.get("a").get(0));
        }
		float r = -1.2f; // default repulsion value for LinLog layout
        if (params.containsKey("r")) {
            r = Float.parseFloat(params.get("r").get(0));
        }
        float theta = 0.7f; // default theta value for LinLog layout
        if (params.containsKey("theta")) {
            theta = Float.parseFloat(params.get("theta").get(0));
        }
        int nodeSize = 10; // default node size in pixels
        if (params.containsKey("node_size")) {
            nodeSize = Integer.parseInt(params.get("node_size").get(0));
        }
        int edgeSize = 2; // default edge size in pixels
        if (params.containsKey("edge_size")) {
            edgeSize = Integer.parseInt(params.get("edge_size").get(0));
        }
        int labelSize = 0; // default label size in points
        if (params.containsKey("label_size")) {
            labelSize = Integer.parseInt(params.get("label_size").get(0));
        }
        int width = 1280; // default image width
        if (params.containsKey("width")) {
            width = Integer.parseInt(params.get("width").get(0));
        }
        int height = 720; // default image height
        if (params.containsKey("height")) {
            height = Integer.parseInt(params.get("height").get(0));
        }
        
        try {
            System.out.println(params.get("dgs").get(0));
            DgsGraphStreamAnimate dgs = new DgsGraphStreamAnimate();
            
            dgs.AnimateDgs(params.get("dgs").get(0), params.get("out").get(0), layout_type, mode, params.get("dotfile").get(0), 
                           seed, force, a, r, theta, nodeSize, edgeSize, labelSize, width, height, display);
        } catch(IOException e) {
            e.printStackTrace();
        }
    }
}
