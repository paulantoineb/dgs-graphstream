package org.graphstream.ui.batik;

import java.awt.Rectangle;
import java.awt.Graphics2D;
import java.awt.Color;
import java.io.Writer;
import java.io.OutputStreamWriter;
import java.io.IOException;
import org.apache.batik.svggen.SVGGraphics2D;
import org.apache.batik.dom.GenericDOMImplementation;
import org.w3c.dom.Document;
import org.w3c.dom.DOMImplementation;
import org.graphstream.ui.swingViewer.util.Graphics2DOutput;

public class BatikGraphics2D implements Graphics2DOutput {
    
    private SVGGraphics2D svgGenerator;
    
    public BatikGraphics2D() {
        // Get a DOMImplementation.
        DOMImplementation domImpl = GenericDOMImplementation.getDOMImplementation();

        // Create an instance of org.w3c.dom.Document.
        String svgNS = "http://www.w3.org/2000/svg";
        Document document = domImpl.createDocument(svgNS, "svg", null);

        // Create an instance of the SVG Generator.
        this.svgGenerator = new SVGGraphics2D(document);
    }

    public Graphics2D getGraphics() {
        return this.svgGenerator;
    }

   public void outputTo(String outputName) throws IOException {
       svgGenerator.stream(outputName);
   }
   
}
