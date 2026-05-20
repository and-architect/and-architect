using System;
using System.Collections.Generic;
using System.Drawing;
using Grasshopper.Kernel;
using Rhino.Geometry;
using AndArchitectGH.Core;
using AndArchitectGH.Goo;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_Orient – defines solar orientation and view targets for the solver.
    /// </summary>
    public class OrientationSetupComponent : GH_Component
    {
        public OrientationSetupComponent()
            : base("AND Orientation", "AND_Orient",
                   "Define site orientation: which way is north, important view points " +
                   "and geographic latitude for solar calculations.",
                   "AND Architect", "01 Setup")
        { }

        public override Guid ComponentGuid => new Guid("D3E4F5A6-B7C8-9012-DEF0-234567890123");
        protected override Bitmap? Icon => ComponentIcons.Orient;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddVectorParameter("North",      "N",
                "World-space vector pointing north (default = +Y)",
                GH_ParamAccess.item, Vector3d.YAxis);
            pManager.AddPointParameter("ViewPoints",  "VP",
                "External points of interest (mountain, lake, street …) that rooms may face",
                GH_ParamAccess.list);
            pManager.AddNumberParameter("Latitude",   "Lat",
                "Geographic latitude in decimal degrees (e.g. 48.1 for Munich)",
                GH_ParamAccess.item, 48.0);

            pManager[1].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddGenericParameter("Orientation", "O",   "Site orientation data",            GH_ParamAccess.item);
            pManager.AddVectorParameter( "South",       "S",   "South vector (max solar gain)",    GH_ParamAccess.item);
            pManager.AddVectorParameter( "East",        "E",   "East vector  (morning sun)",       GH_ParamAccess.item);
            pManager.AddVectorParameter( "West",        "W",   "West vector  (afternoon sun)",     GH_ParamAccess.item);
            pManager.AddNumberParameter( "WinterAlt",   "WA",
                "Winter-solstice solar altitude at noon (degrees) – indicates depth of sunlight penetration",
                GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            var    north    = Vector3d.YAxis;
            var    viewPts  = new List<Point3d>();
            double latitude = 48.0;

            DA.GetData(0, ref north);
            DA.GetDataList(1, viewPts);
            DA.GetData(2, ref latitude);

            if (north.IsTiny())
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, "North vector is zero – using +Y.");
                north = Vector3d.YAxis;
            }
            north.Unitize();

            if (latitude < -90 || latitude > 90)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Latitude must be between -90° and 90°.");
                return;
            }

            var orientation = new OrientationData(north, latitude);
            orientation.ViewPoints.AddRange(viewPts);

            DA.SetData(0, new GH_Orientation(orientation));
            DA.SetData(1, orientation.South);
            DA.SetData(2, orientation.East);
            DA.SetData(3, orientation.West);
            DA.SetData(4, orientation.WinterSolsticeAltitudeDeg());
        }
    }
}
