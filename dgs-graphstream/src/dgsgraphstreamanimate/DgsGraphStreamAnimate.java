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
    
    private enum LayoutType {
        LinLog,
        SpringBox
    }
        
    private void AnimateDgs(String inputDGS, String outputDirectory, LayoutType layout_type, long seed, Boolean display)
            throws java.io.IOException {

        System.setProperty("org.graphstream.ui.renderer","org.graphstream.ui.j2dviewer.J2DGraphRenderer");
        
        FileSourceDGS dgs = new FileSourceDGS();
        
        this.g = new DefaultGraph("graph");
        this.g.addAttribute("ui.stylesheet", "url('style.css')");
        
        layout = CreateLayout(layout_type, seed);
        
        fsi = new FileSinkImages(OutputType.PNG, Resolutions.HD720);
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

        dgs.addAttributeSink(this);

        Viewer viewer = null;
        
        if (display) {
            viewer = this.g.display();
            viewer.enableAutoLayout(layout);
            //pipe = viewer.newViewerPipe();
            pipe = viewer.newThreadProxyOnGraphicGraph();
        }
        
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
        
        try {
            String outputFilePath = inputDGS.split("\\.(?=[^\\.]+$)")[0]+".dot"; // replace ".dhs" by ".dot"
            exportGraphAsDotFile(this.g, getGraphicGraph(fsi), outputFilePath);
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }
    }
    
    /**
     * Create graph layout
     */
    private BarnesHutLayout CreateLayout(LayoutType layout_type, long seed) {
        if (layout_type == LayoutType.LinLog) {
            LinLog layout = new LinLog(false, new Random(seed));
            double a = 0;
            double r = -1.9;
            double force = 3;

            layout.configure(a, r, true, force);
            layout.setQuality(1);
            layout.setBarnesHutTheta(0.5);
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
            node.addAttribute("pos", "["+graphics_graph_node.x+","+graphics_graph_node.y+"]");
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
    
    public static void main(String[] args) {
        
        Map<String, List<String>> params = new HashMap<>();
        List<String> options = null;

        for (String a : args) {
            if (a.charAt(0) == '-') {
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
            System.out.println("-dgs <arg>      input GraphStream DGS file");
            System.out.println("-out <arg>      frame filenames are prepended with this path");
            System.out.println("-layout <arg>   layout type to use. options: [springbox|linlog]. default: springbox");
            System.out.println("-seed <arg>     random seed for the layout");
            System.out.println("-display screen layout option to use. options: [screen]");
            System.out.println("-h,-help        display this help and exit");
            System.exit(1);
        }
        
        LayoutType layout_type = LayoutType.SpringBox;      
        if (params.containsKey("layout") && params.get("layout").get(0).equals("linlog")) {
            layout_type = LayoutType.LinLog;
        }
        Boolean display = false;
        if (params.containsKey("display") && params.get("display").get(0).equals("screen")) {
            display = true;
        }
        long seed = System.currentTimeMillis(); // random seed
        if (params.containsKey("seed")) {
            seed = Long.parseLong(params.get("seed").get(0));
        }
        
        try {
            System.out.println(params.get("dgs").get(0));
            DgsGraphStreamAnimate a = new DgsGraphStreamAnimate();
            a.AnimateDgs(params.get("dgs").get(0), params.get("out").get(0), layout_type, seed, display);
        } catch(IOException e) {
            e.printStackTrace();
        }
    }
}
