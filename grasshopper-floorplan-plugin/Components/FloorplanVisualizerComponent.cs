using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Data;
using Grasshopper.Kernel.Types;
using Rhino.Geometry;
using AndArchitectGH.Core;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_Viz – colours room volumes by type/floor and draws annotation lines.
    /// Also outputs floor-plate curves (bottom face of each room box) for 2-D plan drawings.
    /// </summary>
    public class FloorplanVisualizerComponent : GH_Component
    {
        public FloorplanVisualizerComponent()
            : base("AND Visualize", "AND_Viz",
                   "Colour-code room volumes, extract floor plates and centre labels " +
                   "for annotation. Connect to AND_Generate outputs.",
                   "AND Architect", "04 Visualize")
        { }

        public override Guid ComponentGuid => new Guid("A6B7C8D9-E0F1-2345-0123-567890123456");
        protected override Bitmap? Icon => ComponentIcons.Visualize;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddBrepParameter("Geometry",  "G",  "Room Breps from AND_Generate",              GH_ParamAccess.list);
            pManager.AddTextParameter("Labels",    "L",  "Room labels from AND_Generate",             GH_ParamAccess.list);
            pManager.AddPointParameter("Centres",  "C",  "Room centre points from AND_Generate",      GH_ParamAccess.list);
            pManager.AddNumberParameter("FloorH",  "FH", "Floor-to-floor height (m) to extract planes", GH_ParamAccess.item, 3.0);
            pManager.AddBooleanParameter("ShowAll","SA",
                "True = show all rooms; False = show only rooms on SelFloor",                          GH_ParamAccess.item, true);
            pManager.AddIntegerParameter("SelFloor","SF",
                "Floor to show when ShowAll=False (0 = ground)",                                       GH_ParamAccess.item, 0);

            pManager[4].Optional = true;
            pManager[5].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddBrepParameter("Rooms",       "R",  "Filtered room volumes",             GH_ParamAccess.list);
            pManager.AddCurveParameter("FloorPlates","FP", "Bottom-face curves (for 2-D plans)",GH_ParamAccess.list);
            pManager.AddPointParameter("LabelPts",   "LP", "Label insertion points",            GH_ParamAccess.list);
            pManager.AddTextParameter( "LabelText",  "LT", "Label strings (name + area)",       GH_ParamAccess.list);
            pManager.AddNumberParameter("ColourR",   "CR", "Red channel 0-255 per room",        GH_ParamAccess.list);
            pManager.AddNumberParameter("ColourG",   "CG", "Green channel 0-255 per room",      GH_ParamAccess.list);
            pManager.AddNumberParameter("ColourB",   "CB", "Blue channel 0-255 per room",       GH_ParamAccess.list);
        }

        // ── Colour palette ─────────────────────────────────────────────────────

        private static readonly Color[] FloorColors = new[]
        {
            Color.FromArgb(180, 210, 240),  // floor 0 – light blue
            Color.FromArgb(200, 240, 200),  // floor 1 – light green
            Color.FromArgb(250, 220, 180),  // floor 2 – light orange
            Color.FromArgb(240, 200, 240),  // floor 3 – light purple
            Color.FromArgb(240, 240, 180),  // floor 4 – light yellow
        };

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            var breps    = new List<Brep>();
            var labels   = new List<string>();
            var centres  = new List<Point3d>();
            double floorH = 3.0;
            bool showAll  = true;
            int  selFloor = 0;

            if (!DA.GetDataList(0, breps))   return;
            DA.GetDataList(1, labels);
            DA.GetDataList(2, centres);
            DA.GetData(3, ref floorH);
            DA.GetData(4, ref showAll);
            DA.GetData(5, ref selFloor);

            // Pad labels / centres if shorter than breps list
            while (labels.Count < breps.Count)  labels.Add($"Room {labels.Count}");
            while (centres.Count < breps.Count) centres.Add(breps[centres.Count].GetBoundingBox(false).Center);

            // Determine floor of each room from centre Z
            int FloorOf(Point3d c) => floorH > 0 ? (int)Math.Round(c.Z / floorH) : 0;

            // Filter
            var outBreps   = new List<Brep>();
            var outPlates  = new List<Curve>();
            var outPts     = new List<Point3d>();
            var outLabels  = new List<string>();
            var reds       = new List<double>();
            var greens     = new List<double>();
            var blues      = new List<double>();

            for (int i = 0; i < breps.Count; i++)
            {
                var brep   = breps[i];
                var centre = centres[i];
                int floor  = FloorOf(centre);

                if (!showAll && floor != selFloor) continue;

                // Floor plate = bottom face
                Curve? plate = ExtractBottomFace(brep);

                outBreps.Add(brep);
                if (plate != null) outPlates.Add(plate);
                outPts.Add(centre);
                outLabels.Add(labels[i]);

                var col = FloorColors[Math.Abs(floor) % FloorColors.Length];
                reds.Add(col.R);
                greens.Add(col.G);
                blues.Add(col.B);
            }

            DA.SetDataList(0, outBreps);
            DA.SetDataList(1, outPlates);
            DA.SetDataList(2, outPts);
            DA.SetDataList(3, outLabels);
            DA.SetDataList(4, reds);
            DA.SetDataList(5, greens);
            DA.SetDataList(6, blues);
        }

        // ── Helpers ────────────────────────────────────────────────────────────

        private static Curve? ExtractBottomFace(Brep brep)
        {
            // Find the face whose centre has the lowest Z value
            BrepFace? bottom = null;
            double minZ = double.MaxValue;

            foreach (var face in brep.Faces)
            {
                var bb = face.GetBoundingBox(false);
                double z = bb.Center.Z;
                if (z < minZ) { minZ = z; bottom = face; }
            }

            if (bottom == null) return null;

            var loops = bottom.OuterLoop;
            if (loops == null) return null;

            return loops.To3dCurve();
        }
    }
}
