using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using Grasshopper.Kernel;
using Rhino.Geometry;
using AndArchitectGH.Core;
using AndArchitectGH.Goo;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_Generate – core solver component.
    /// Generates N layout variants in 3-D and lets the user select one.
    /// </summary>
    public class FloorplanGeneratorComponent : GH_Component
    {
        public FloorplanGeneratorComponent()
            : base("AND Generate", "AND_Gen",
                   "Generate floor-plan variants in 3-D based on rooms, building envelope and site orientation. " +
                   "Rooms are placed to maximise solar gain, view exposure and programmatic adjacency.",
                   "AND Architect", "02 Generate")
        { }

        public override Guid ComponentGuid => new Guid("E4F5A6B7-C8D9-0123-EF01-345678901234");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddGenericParameter("Rooms",       "R",  "List of AND_Room definitions",     GH_ParamAccess.list);
            pManager.AddGenericParameter("Building",    "B",  "AND_Building envelope",            GH_ParamAccess.item);
            pManager.AddGenericParameter("Orientation", "O",  "AND_Orientation data (optional)",  GH_ParamAccess.item);
            pManager.AddIntegerParameter("Variants",    "V",  "Number of variants to generate",   GH_ParamAccess.item, 3);
            pManager.AddIntegerParameter("Select",      "S",  "Index of variant to output (0-based)", GH_ParamAccess.item, 0);

            pManager[2].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            // Selected variant
            pManager.AddBrepParameter(  "Geometry",   "G",  "Room volumes (Breps) of selected variant", GH_ParamAccess.list);
            pManager.AddTextParameter(  "Labels",     "L",  "Room labels for text tags",                GH_ParamAccess.list);
            pManager.AddPointParameter( "Centres",    "C",  "Room centre points for text placement",    GH_ParamAccess.list);
            pManager.AddNumberParameter("Scores",     "Sc", "Individual room placement scores [0,1]",   GH_ParamAccess.list);
            pManager.AddNumberParameter("VariantScore","VS", "Overall variant score",                   GH_ParamAccess.item);
            pManager.AddTextParameter(  "Report",     "Rp", "Full variant layout report",               GH_ParamAccess.item);

            // All variants (for preview / comparison)
            pManager.AddBrepParameter(  "AllBreps",   "AB", "All variants stacked for comparison (separated by offset)", GH_ParamAccess.list);
            pManager.AddTextParameter(  "AllLabels",  "AL", "Variant labels for comparison view",       GH_ParamAccess.list);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            var roomGoos = new List<IGH_Goo>();
            var buildGoo = default(IGH_Goo);
            var orientGoo= default(IGH_Goo);
            int variants = 3;
            int select   = 0;

            if (!DA.GetDataList(0, roomGoos))  return;
            if (!DA.GetData(1, ref buildGoo))  return;
            DA.GetData(2, ref orientGoo);
            DA.GetData(3, ref variants);
            DA.GetData(4, ref select);

            // Unpack rooms
            var rooms = new List<Room>();
            foreach (var goo in roomGoos)
            {
                if (goo is GH_Room ghRoom)
                    rooms.Add(ghRoom.Value);
                else if (goo?.ScriptVariable() is Room r)
                    rooms.Add(r);
                else
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, $"Skipped non-room input: {goo}");
            }

            if (rooms.Count == 0)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "No valid rooms provided.");
                return;
            }

            // Unpack building
            Building? building = null;
            if (buildGoo is GH_Building ghBuilding)
                building = ghBuilding.Value;
            else if (buildGoo?.ScriptVariable() is Building bld)
                building = bld;

            if (building == null)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "No valid building provided.");
                return;
            }

            // Unpack orientation (optional)
            OrientationData orientation = new OrientationData();
            if (orientGoo is GH_Orientation ghOrient)
                orientation = ghOrient.Value;
            else if (orientGoo?.ScriptVariable() is OrientationData od)
                orientation = od;

            // Validate
            if (variants < 1) variants = 1;
            if (variants > 10)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, "Capped variants at 10.");
                variants = 10;
            }

            // Validate room areas vs building
            double totalRoomArea = rooms.Sum(r => r.Area);
            double buildingGFA   = building.FootprintArea * building.NumberOfFloors;
            if (totalRoomArea > buildingGFA * 1.1)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                    $"Total room area ({totalRoomArea:F0} m²) exceeds building GFA ({buildingGFA:F0} m²). " +
                    "Some rooms may not be placed.");
            }

            // ── Run solver ─────────────────────────────────────────────────────

            var solver      = new FloorplanSolver(rooms, building, orientation);
            var allVariants = solver.GenerateVariants(variants);

            if (allVariants.Count == 0)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Solver produced no variants.");
                return;
            }

            // Clamp selection index
            select = Math.Max(0, Math.Min(select, allVariants.Count - 1));
            var chosen = allVariants[select];

            // ── Output selected variant ────────────────────────────────────────

            var geom    = chosen.AllBreps();
            var labels  = chosen.Rooms.Select(r =>
                $"{r.Name}\n{r.Source.Area:F1} m²").ToList();
            var centres = chosen.Rooms.Select(r => r.Center).ToList();
            var scores  = chosen.Rooms.Select(r => r.PlacementScore).ToList();

            DA.SetDataList(0, geom);
            DA.SetDataList(1, labels);
            DA.SetDataList(2, centres);
            DA.SetDataList(3, scores);
            DA.SetData(4, chosen.Score);
            DA.SetData(5, chosen.Summary());

            // ── Output all variants offset for comparison ──────────────────────

            var allBreps  = new List<Brep>();
            var allLabels = new List<string>();

            double offsetX = building.FootprintWidth + 5.0;  // 5 m gap between variants

            for (int i = 0; i < allVariants.Count; i++)
            {
                var v = allVariants[i];
                var xf = Transform.Translation(offsetX * i, 0, 0);

                foreach (var brep in v.AllBreps())
                {
                    var copy = brep.DuplicateBrep();
                    copy.Transform(xf);
                    allBreps.Add(copy);
                }

                allLabels.Add($"[{i}] {v.Label}  score={v.Score:F3}");
            }

            DA.SetDataList(6, allBreps);
            DA.SetDataList(7, allLabels);
        }
    }
}
