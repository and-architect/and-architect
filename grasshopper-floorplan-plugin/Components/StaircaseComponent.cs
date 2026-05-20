using System;
using System.Collections.Generic;
using System.Drawing;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Types;
using Rhino.Geometry;
using AndArchitectGH.Core;
using AndArchitectGH.Goo;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_Stair – defines and places a staircase between floor levels.
    ///
    /// Outputs a Room-compatible object (so the solver treats it as a space),
    /// plus detailed 3-D geometry for visualization.
    ///
    /// Staircase types:
    ///   Straight   / Gerade
    ///   LShape     / LFörmig
    ///   UShape     / UFörmig (zweiläufig)
    ///   Spiral     / Wendel
    /// </summary>
    public class StaircaseComponent : GH_Component
    {
        public StaircaseComponent()
            : base("AND Staircase", "AND_Stair",
                   "Define a staircase between floor levels.\n" +
                   "Types: Straight (Gerade) | LShape (L-förmig) | UShape (U/zweiläufig) | Spiral (Wendel)\n\n" +
                   "Connect the Room output to AND_Generate alongside regular rooms.\n" +
                   "Connect Geometry + Treads + Handrails to AND_Viz or CustomPreview.",
                   "AND Architect", "01 Setup")
        { }

        public override Guid ComponentGuid =>
            new Guid("A2B3C4D5-E6F7-8901-5678-012345678901");
        protected override Bitmap? Icon => ComponentIcons.Staircase;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddTextParameter("Name",       "N",
                "Staircase name",                                                   GH_ParamAccess.item, "Treppenhaus");
            pManager.AddTextParameter("Type",       "T",
                "Staircase type: Straight | LShape | UShape | Spiral\n" +
                "(German: Gerade | LFörmig | UFörmig | Wendel)",                   GH_ParamAccess.item, "Straight");
            pManager.AddIntegerParameter("FromFloor","FF",
                "Starting floor level (0 = EG, -1 = KG, etc.)",                   GH_ParamAccess.item, 0);
            pManager.AddIntegerParameter("ToFloor",  "TF",
                "Ending floor level",                                              GH_ParamAccess.item, 1);
            pManager.AddNumberParameter("Width",    "W",
                "Clear staircase width (m, min. 0.9 for residential, 1.2 recommended)", GH_ParamAccess.item, 1.2);
            pManager.AddNumberParameter("TreadD",   "TD",
                "Tread depth / Auftrittstiefe (m, default 0.25)",                 GH_ParamAccess.item, 0.25);
            pManager.AddNumberParameter("RiserH",   "RH",
                "Riser height / Stufenhöhe (m, default 0.175)",                   GH_ParamAccess.item, 0.175);
            pManager.AddGenericParameter("Building","B",
                "AND_Building (needed to read floor height and position)",         GH_ParamAccess.item);
            pManager.AddPointParameter("Origin",    "O",
                "Placement origin (SW corner). Leave unset for auto-placement.",   GH_ParamAccess.item, new Point3d(0,0,0));

            pManager[7].Optional = true;
            pManager[8].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddGenericParameter("Room",      "R",
                "Staircase as AND_Room (connect to AND_Generate)",              GH_ParamAccess.item);
            pManager.AddBrepParameter("Geometry",    "G",
                "Stairwell volume per floor level",                            GH_ParamAccess.list);
            pManager.AddBrepParameter("Treads",      "Tr",
                "Individual tread slabs",                                      GH_ParamAccess.list);
            pManager.AddCurveParameter("Handrails",  "HR",
                "Handrail / Geländer curves",                                 GH_ParamAccess.list);
            pManager.AddPointParameter("EntryPt",    "E",
                "Entry point (bottom landing)",                                GH_ParamAccess.item);
            pManager.AddPointParameter("ExitPt",     "X",
                "Exit point (top landing)",                                    GH_ParamAccess.item);
            pManager.AddTextParameter("Info",        "I",
                "Staircase summary (steps, dimensions, DIN 18065 check)",      GH_ParamAccess.item);
        }

        // ── Type aliases ───────────────────────────────────────────────────────

        private static readonly Dictionary<string, StaircaseType> Aliases =
            new(StringComparer.OrdinalIgnoreCase)
        {
            ["straight"] = StaircaseType.Straight, ["gerade"]   = StaircaseType.Straight,
            ["lshape"]   = StaircaseType.LShape,   ["lförmig"]  = StaircaseType.LShape,
            ["ushape"]   = StaircaseType.UShape,   ["uförmig"]  = StaircaseType.UShape,
                                                   ["zweiläufig"]= StaircaseType.UShape,
            ["spiral"]   = StaircaseType.Spiral,   ["wendel"]   = StaircaseType.Spiral
        };

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            string name    = "Treppenhaus";
            string typeStr = "Straight";
            int    fromF   = 0;
            int    toF     = 1;
            double width   = 1.2;
            double tread   = 0.25;
            double riser   = 0.175;
            var    buildGoo= default(IGH_Goo);
            var    origin  = new Point3d(0, 0, 0);

            DA.GetData(0, ref name);
            DA.GetData(1, ref typeStr);
            DA.GetData(2, ref fromF);
            DA.GetData(3, ref toF);
            DA.GetData(4, ref width);
            DA.GetData(5, ref tread);
            DA.GetData(6, ref riser);
            DA.GetData(7, ref buildGoo);
            DA.GetData(8, ref origin);

            if (toF <= fromF)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "ToFloor muss > FromFloor sein.");
                return;
            }
            if (width < 0.5)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, "Treppenbreite < 0.5 m – unrealistisch.");
            }

            // Resolve type
            if (!Aliases.TryGetValue(typeStr, out var stairType))
            {
                if (!Enum.TryParse<StaircaseType>(typeStr, true, out stairType))
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, $"Unbekannter Treppentyp '{typeStr}' → Gerade");
                    stairType = StaircaseType.Straight;
                }
            }

            // Floor height from building
            double floorHeight = 3.0;
            int    floors      = toF - fromF + 1;
            if (buildGoo is GH_Building gb)
            {
                floorHeight = gb.Value.FloorHeight;
                floors      = gb.Value.NumberOfFloors;
            }
            else if (buildGoo?.ScriptVariable() is Building bld)
            {
                floorHeight = bld.FloorHeight;
                floors      = bld.NumberOfFloors;
            }

            var stair = new StaircaseDefinition
            {
                Name        = name,
                Type        = stairType,
                FromFloor   = fromF,
                ToFloor     = toF,
                Width       = width,
                TreadDepth  = tread,
                RiserHeight = riser
            };

            // DIN 18065 check: 2×h + a = 63 ± 3 cm
            double din = 2 * riser * 100 + tread * 100;
            string dinCheck = Math.Abs(din - 63) <= 3
                ? $"✓ DIN 18065: 2h+a = {din:F1} cm (63±3)"
                : $"⚠ DIN 18065: 2h+a = {din:F1} cm (Ziel 63±3 cm)";

            // Generate 3-D geometry
            var geo = StaircaseGeometryGenerator.Generate(stair, origin, floorHeight, floors);

            // Create Room object for solver
            double stairArea = stair.FootprintWidth * stair.FootprintDepth;
            var room = new Room
            {
                Name        = name,
                Area        = stairArea,
                Floor       = fromF,
                Type        = RoomType.Staircase,
                Priority    = 0.9,  // must be placed first (central location)
                MustBeNear  = new List<string>(),
                MustBeAway  = new List<string>()
            };
            room.SetExplicitDimensions(stair.FootprintWidth, stair.FootprintDepth);

            // Info string
            int nSteps    = (int)Math.Ceiling(floorHeight / riser);
            double runLen = nSteps * tread;
            string info =
                $"{stairType}  Stufen: {nSteps}×{riser * 100:F0}/{tread * 100:F0} cm  " +
                $"Lauflänge: {runLen:F2} m  " +
                $"Grundriss: {stair.FootprintWidth:F2}×{stair.FootprintDepth:F2} m\n" +
                $"{dinCheck}";

            DA.SetData(0, new GH_Room(room));
            DA.SetDataList(1, geo.Volumes);
            DA.SetDataList(2, geo.Treads);
            DA.SetDataList(3, geo.Handrails);
            DA.SetData(4, geo.EntryPt);
            DA.SetData(5, geo.ExitPt);
            DA.SetData(6, info);
        }
    }
}
