import gov.nasa.jpf.Config;
import gov.nasa.jpf.JPF;
import gov.nasa.jpf.ListenerAdapter;
import gov.nasa.jpf.search.Search;
import gov.nasa.jpf.vm.Instruction;
import gov.nasa.jpf.vm.MethodInfo;
import gov.nasa.jpf.vm.Path;
import gov.nasa.jpf.vm.Step;
import gov.nasa.jpf.vm.Transition;
import gov.nasa.jpf.vm.VM;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

/**
 * JPF listener for root-cause analysis.
 *
 * Writes into the directory given by  tracedump.out  (default: jpf_out):
 *   trace.json  - counterexample path (only if a property was violated):
 *                 every executed instruction of USER code, per thread, with source line
 *   graph.json  - explored state graph (edges: from, to, isNew, thread)
 *   graph.dot   - same graph for Graphviz
 *
 * Config keys:  tracedump.out=<dir>   tracedump.max_edges=<int, default 20000>
 * Requires:     vm.store_steps=true
 */
public class TraceDump extends ListenerAdapter {

  private final File outDir;
  private final int maxEdges;

  private final List<int[]> edges = new ArrayList<int[]>();
  private final List<String> edgeThreads = new ArrayList<String>();
  private final Set<Integer> endStates = new TreeSet<Integer>();
  private int lastId = -1;
  private int errorState = -1;
  private boolean truncated = false;
  private String errorText = null;
  private String stepsJson = null;

  public TraceDump(Config conf, JPF jpf) {
    outDir = new File(conf.getString("tracedump.out", "jpf_out"));
    maxEdges = conf.getInt("tracedump.max_edges", 20000);
  }

  // ---------------------------------------------------------------- state graph

  @Override
  public void stateAdvanced(Search search) {
    int id = search.getStateId();
    if (lastId >= 0) {
      if (edges.size() < maxEdges) {
        edges.add(new int[] { lastId, id, search.isNewState() ? 1 : 0 });
        edgeThreads.add(lastThread(search));
      } else {
        truncated = true;
      }
    }
    if (search.isEndState()) {
      endStates.add(id);
    }
    lastId = id;
  }

  @Override
  public void stateBacktracked(Search search) {
    lastId = search.getStateId();
  }

  @Override
  public void stateRestored(Search search) {
    lastId = search.getStateId();
  }

  private String lastThread(Search search) {
    Transition t = search.getTransition();
    if (t != null && t.getThreadInfo() != null) {
      return t.getThreadInfo().getName();
    }
    return "?";
  }

  // ---------------------------------------------------------------- counterexample

  @Override
  public void propertyViolated(Search search) {
    if (stepsJson != null) {
      return; // keep only the first error
    }
    errorState = search.getStateId();
    if (search.getLastError() != null) {
      errorText = String.valueOf(search.getLastError().getDescription());
    }

    VM vm = search.getVM();
    Path path = vm.getPath();
    StringBuilder sb = new StringBuilder("[");
    boolean first = true;
    int trIndex = 0;

    for (Transition t : path) {
      String thread = (t.getThreadInfo() != null) ? t.getThreadInfo().getName() : "?";
      int n = t.getStepCount();
      for (int i = 0; i < n; i++) {
        Step s = t.getStep(i);
        if (s == null) {
          continue;
        }
        Instruction insn = s.getInstruction();
        if (insn == null) {
          continue;
        }
        MethodInfo mi = insn.getMethodInfo();
        if (mi == null) {
          continue;
        }
        String cls = mi.getClassName();
        if (isSystem(cls)) {
          continue;
        }
        if (!first) {
          sb.append(',');
        }
        first = false;
        sb.append("{\"tr\":").append(trIndex)
          .append(",\"th\":").append(q(thread))
          .append(",\"cls\":").append(q(cls))
          .append(",\"m\":").append(q(mi.getBaseName()))
          .append(",\"line\":").append(insn.getLineNumber())
          .append(",\"op\":").append(q(insn.getMnemonic()))
          .append(",\"insn\":").append(q(String.valueOf(insn)))
          .append(",\"sync\":").append(mi.isSynchronized())
          .append('}');
      }
      trIndex++;
    }
    sb.append(']');
    stepsJson = sb.toString();
  }

  private static boolean isSystem(String cls) {
    return cls == null
        || cls.startsWith("java.") || cls.startsWith("javax.")
        || cls.startsWith("sun.") || cls.startsWith("jdk.")
        || cls.startsWith("com.sun.") || cls.startsWith("gov.nasa.");
  }

  // ---------------------------------------------------------------- output

  @Override
  public void searchFinished(Search search) {
    try {
      outDir.mkdirs();

      if (stepsJson != null) {
        String err = errorText == null ? "" : errorText;
        if (err.length() > 6000) {
          err = err.substring(0, 6000) + "...";
        }
        write("trace.json",
            "{\"error\":" + q(err) + ",\"error_state\":" + errorState
                + ",\"steps\":" + stepsJson + "}");
      }

      StringBuilder g = new StringBuilder();
      g.append("{\"edges\":[");
      for (int i = 0; i < edges.size(); i++) {
        int[] e = edges.get(i);
        if (i > 0) {
          g.append(',');
        }
        g.append('[').append(e[0]).append(',').append(e[1]).append(',').append(e[2])
         .append(',').append(q(edgeThreads.get(i))).append(']');
      }
      g.append("],\"end_states\":[");
      boolean f = true;
      for (Integer id : endStates) {
        if (!f) {
          g.append(',');
        }
        f = false;
        g.append(id);
      }
      g.append("],\"error_state\":").append(errorState)
       .append(",\"truncated\":").append(truncated).append('}');
      write("graph.json", g.toString());

      StringBuilder d = new StringBuilder();
      d.append("digraph statespace {\n  rankdir=TB;\n  node [shape=circle,fontsize=9];\n");
      d.append("  s0 [shape=box,style=filled,fillcolor=lightgray];\n");
      for (Integer id : endStates) {
        d.append("  s").append(id).append(" [shape=doublecircle];\n");
      }
      if (errorState >= 0) {
        d.append("  s").append(errorState)
         .append(" [style=filled,fillcolor=tomato,shape=octagon];\n");
      }
      for (int i = 0; i < edges.size(); i++) {
        int[] e = edges.get(i);
        d.append("  s").append(e[0]).append(" -> s").append(e[1])
         .append(" [label=").append(q(edgeThreads.get(i)))
         .append(e[2] == 0 ? ",style=dashed" : "").append("];\n");
      }
      d.append("}\n");
      write("graph.dot", d.toString());
    } catch (Exception ex) {
      System.err.println("[TraceDump] failed: " + ex);
    }
  }

  private void write(String name, String content) throws Exception {
    Writer w = new OutputStreamWriter(new FileOutputStream(new File(outDir, name)), "UTF-8");
    try {
      w.write(content);
    } finally {
      w.close();
    }
  }

  private static String q(String s) {
    if (s == null) {
      return "null";
    }
    StringBuilder b = new StringBuilder("\"");
    for (int i = 0; i < s.length(); i++) {
      char c = s.charAt(i);
      switch (c) {
        case '"':  b.append("\\\""); break;
        case '\\': b.append("\\\\"); break;
        case '\n': b.append("\\n"); break;
        case '\r': b.append("\\r"); break;
        case '\t': b.append("\\t"); break;
        default:
          if (c < 0x20) {
            b.append(String.format("\\u%04x", (int) c));
          } else {
            b.append(c);
          }
      }
    }
    return b.append('"').toString();
  }
}
