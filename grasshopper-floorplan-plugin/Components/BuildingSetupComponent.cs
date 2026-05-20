using System;
using System.Drawing;
using Grasshopper.Kernel;
using Rhino.Geometry;
using AndArchitectGH.Core;
using AndArchitectGH.Goo;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_Building – defines the building envelope (footprint + floors).
    /// Accepts either a rectangle by width/depth or an arbitrary closed planar polyline.
    /// </summary>
    public class BuildingSetupComponent : GH_Component
    {
        public BuildingSetupComponent()
            : base("AND Building", "AND_Building",
                   "Define the building envelope: footprint dimensions (or curve), " +
                   "number of floors and floor-to-floor height.",
                   "AND Architect", "01 Setup")
        { }

        public override Guid ComponentGuid => new Guid("C2D3E4F5-A6B7-8901-CDEF-123456789012");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddCurveParameter("Footprint", "FP",
                "Optional closed planar curve as footprint. If omitted, use W × D.",
                GH_ParamAccess.item);
            pManager.AddNumberParameter("Width",  "W",  "Footprint width  (m) – ignored if FP is set", GH_ParamAccess.item, 12.0);
            pManager.AddNumberParameter("Depth",  "D",  "Footprint depth  (m) – ignored if FP is set", GH_ParamAccess.item, 10.0);
            pManager.AddIntegerParameter("Floors","FL", "Number of above-ground floors",               GH_ParamAccess.item, 2);
            pManager.AddNumberParameter("FloorH", "FH", "Floor-to-floor height (m)",                   GH_ParamAccess.item, 3.0);

            pManager[0].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddGenericParameter("Building", "B",  "Building envelope",              GH_ParamAccess.item);
            pManager.AddBrepParameter(   "Envelope", "E",  "3-D envelope as Brep (preview)", GH_ParamAccess.item);
            pManager.AddNumberParameter( "GFA",      "GFA","Gross floor area (m²)",          GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            Curve? fp      = null;
            double width   = 12.0;
            double depth   = 10.0;
            int    floors  = 2;
            double floorH  = 3.0;

            DA.GetData(0, ref fp);
            DA.GetData(1, ref width);
            DA.GetData(2, ref depth);
            DA.GetData(3, ref floors);
            DA.GetData(4, ref floorH);

            if (floors < 1) { AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Floors must be ≥ 1."); return; }
            if (floorH <= 0) { AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Floor height must be > 0."); return; }

            Building building;

            if (fp != null)
            {
                if (!fp.IsClosed)
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Footprint curve must be closed.");
                    return;
                }
                if (!fp.IsPlanar())
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Footprint curve must be planar (XY).");
                    return;
                }

                // Convert curve to polyline approximation
                fp.TryGetPolyline(out var poly);
                if (poly == null || poly.Count < 3)
                {
                    // Discretise at 1 m resolution
                    var pts = fp.DivideEquidistant(1.0);
                    poly = new Polyline(pts ?? Array.Empty<Point3d>());
                    poly.Add(poly[0]);
                }
                building = new Building(poly, floors, floorH);
            }
            else
            {
                if (width <= 0 || depth <= 0)
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Width and Depth must be > 0.");
                    return;
                }
                building = new Building(width, depth, floors, floorH);
            }

            DA.SetData(0, new GH_Building(building));
            DA.SetData(1, building.GetEnvelopeBrep());
            DA.SetData(2, building.FootprintArea * building.NumberOfFloors);
        }
    }
}
