using System;
using System.Drawing;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Types;
using Rhino.Geometry;
using AndArchitectGH.Core;
using AndArchitectGH.Goo;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_Building – defines the building envelope.
    /// Supports above-ground floors AND basement levels (Kellergeschosse).
    /// Accepts footprint curve OR width × depth.
    /// </summary>
    public class BuildingSetupComponent : GH_Component
    {
        public BuildingSetupComponent()
            : base("AND Building", "AND_Building",
                   "Define the building envelope.\n" +
                   "Above-ground: NumberOfFloors × FloorHeight\n" +
                   "Below-ground: Basements × BasementHeight (Kellergeschosse)\n\n" +
                   "Footprint: connect a closed curve OR set Width + Depth.",
                   "AND Architect", "01 Setup")
        { }

        public override Guid ComponentGuid =>
            new Guid("C2D3E4F5-A6B7-8901-CDEF-123456789012");
        protected override Bitmap? Icon => ComponentIcons.Building;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            // Footprint
            pManager.AddCurveParameter("Footprint",    "FP",
                "Optional closed planar curve as footprint. If omitted, use W × D.",
                GH_ParamAccess.item);
            pManager.AddNumberParameter("Width",       "W",
                "Footprint width  (m) – ignored if FP is set",                     GH_ParamAccess.item, 12.0);
            pManager.AddNumberParameter("Depth",       "D",
                "Footprint depth  (m) – ignored if FP is set",                     GH_ParamAccess.item, 10.0);

            // Above-ground
            pManager.AddIntegerParameter("Floors",     "FL",
                "Number of above-ground floors (EG = 1, EG+OG = 2 …)",            GH_ParamAccess.item, 2);
            pManager.AddNumberParameter("FloorH",      "FH",
                "Floor-to-floor height (m)",                                        GH_ParamAccess.item, 3.0);

            // Below-ground
            pManager.AddIntegerParameter("Basements",  "KG",
                "Number of basement levels / Kellergeschosse (0 = none)",          GH_ParamAccess.item, 0);
            pManager.AddNumberParameter("BasementH",   "KH",
                "Basement floor height (m, default 2.5)",                          GH_ParamAccess.item, 2.5);

            pManager[0].Optional = true;
            pManager[5].Optional = true;
            pManager[6].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddGenericParameter("Building",  "B",   "Building envelope",                    GH_ParamAccess.item);
            pManager.AddBrepParameter("Envelope",     "E",   "Full 3-D envelope (above + below)",    GH_ParamAccess.item);
            pManager.AddBrepParameter("AboveGround",  "AG",  "Above-ground shell only",              GH_ParamAccess.item);
            pManager.AddBrepParameter("Basement",     "BG",  "Basement shell (null if none)",        GH_ParamAccess.item);
            pManager.AddNumberParameter("GFA",        "GFA", "Gross floor area above ground (m²)",   GH_ParamAccess.item);
            pManager.AddNumberParameter("TotalGFA",   "TGFA","Total GFA incl. basements (m²)",       GH_ParamAccess.item);
            pManager.AddTextParameter("Info",         "I",   "Building summary",                     GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            Curve? fp        = null;
            double width     = 12.0;
            double depth     = 10.0;
            int    floors    = 2;
            double floorH    = 3.0;
            int    basements = 0;
            double basementH = 2.5;

            DA.GetData(0, ref fp);
            DA.GetData(1, ref width);
            DA.GetData(2, ref depth);
            DA.GetData(3, ref floors);
            DA.GetData(4, ref floorH);
            DA.GetData(5, ref basements);
            DA.GetData(6, ref basementH);

            if (floors < 1)    { AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Floors muss ≥ 1 sein."); return; }
            if (floorH <= 0)   { AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "FloorHeight muss > 0 sein."); return; }
            if (basements < 0) { basements = 0; AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, "Basements < 0 → 0 gesetzt."); }
            if (basementH <= 0) basementH = 2.5;

            Building building;

            if (fp != null)
            {
                if (!fp.IsClosed)
                { AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Grundriss-Kurve muss geschlossen sein."); return; }
                if (!fp.IsPlanar())
                { AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Grundriss-Kurve muss planar (XY) sein."); return; }

                fp.TryGetPolyline(out var poly);
                if (poly == null || poly.Count < 3)
                {
                    var pts = fp.DivideEquidistant(1.0);
                    poly = new Polyline(pts ?? Array.Empty<Point3d>());
                    poly.Add(poly[0]);
                }
                building = new Building(poly, floors, floorH, basements, basementH);
            }
            else
            {
                if (width <= 0 || depth <= 0)
                { AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Breite und Tiefe müssen > 0 sein."); return; }
                building = new Building(width, depth, floors, floorH, basements, basementH);
            }

            double gfaAbove = building.FootprintArea * building.NumberOfFloors;
            double gfaTotal = gfaAbove + building.FootprintArea * building.NumberOfBasements;

            DA.SetData(0, new GH_Building(building));
            DA.SetData(1, building.GetEnvelopeBrep());
            DA.SetData(2, building.GetAboveGroundBrep());
            DA.SetData(3, building.GetBasementBrep());
            DA.SetData(4, gfaAbove);
            DA.SetData(5, gfaTotal);
            DA.SetData(6, building.ToString() +
                         $"\nGFA oberirdisch: {gfaAbove:F0} m²" +
                         (basements > 0 ? $"  KG: {building.FootprintArea * basements:F0} m²" : ""));
        }
    }
}
