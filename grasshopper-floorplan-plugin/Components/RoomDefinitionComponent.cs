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
    /// AND_Room – defines a single room.
    /// Dimensions can be given as area OR explicit width × depth.
    /// Both inputs are live-adjustable with sliders.
    /// </summary>
    public class RoomDefinitionComponent : GH_Component
    {
        public RoomDefinitionComponent()
            : base("AND Room", "AND_Room",
                   "Define a room. Specify area OR width + depth (explicit dimensions override area).\n" +
                   "All inputs accept sliders for real-time layout updates.",
                   "AND Architect", "01 Setup")
        { }

        public override Guid ComponentGuid =>
            new Guid("B1C2D3E4-F5A6-7890-BCDE-F12345678901");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            // Identity
            pManager.AddTextParameter("Name",       "N",  "Room name (e.g. 'Wohnzimmer')",      GH_ParamAccess.item, "Raum");
            pManager.AddIntegerParameter("Floor",   "FL", "Floor level  (0 = EG, 1 = OG …)",    GH_ParamAccess.item, 0);
            pManager.AddTextParameter("Type",       "T",
                "Room type: LivingRoom | Kitchen | DiningRoom | MasterBedroom | Bedroom | " +
                "ChildRoom | Bathroom | WC | Office | Library | Hallway | Staircase | " +
                "Storage | Garage | Balcony | Terrace | Custom",
                GH_ParamAccess.item, "Custom");

            // Dimensions – three modes:
            //   A only         → solver estimates W×D from A using a default aspect
            //   W + D only     → area derived as W×D
            //   A + W + D      → W and D override; A is informational
            pManager.AddNumberParameter("Area",     "A",  "Floor area (m²) – used when W/D are 0",    GH_ParamAccess.item, 20.0);
            pManager.AddNumberParameter("Width",    "W",  "Room width  (m) – 0 = auto from area",      GH_ParamAccess.item, 0.0);
            pManager.AddNumberParameter("Depth",    "D",  "Room depth  (m) – 0 = auto from area",      GH_ParamAccess.item, 0.0);
            pManager.AddNumberParameter("MinH",     "MH", "Minimum ceiling height (m, 0 = building default)", GH_ParamAccess.item, 0.0);

            // Environmental preferences
            pManager.AddTextParameter("Solar",      "S",
                "Solar preference: South | East | West | North | Any",
                GH_ParamAccess.item, "Any");
            pManager.AddVectorParameter("ViewDir",  "VD",
                "Preferred façade direction (world XY). Zero = no preference.",
                GH_ParamAccess.item, Vector3d.Zero);

            // Adjacency constraints
            pManager.AddTextParameter("NearRooms",  "NR",
                "Room names this room must be adjacent to",
                GH_ParamAccess.list);
            pManager.AddTextParameter("AwayRooms",  "AR",
                "Room names this room must NOT be adjacent to",
                GH_ParamAccess.list);

            // Solver weight
            pManager.AddNumberParameter("Priority", "P",
                "Placement priority 0–1 (higher = placed first, better position)",
                GH_ParamAccess.item, 0.5);

            // Optional inputs
            for (int i = 4; i <= 11; i++)
                pManager[i].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddGenericParameter("Room",    "R",  "Room definition",                    GH_ParamAccess.item);
            pManager.AddNumberParameter("Area",     "A",  "Effective floor area (m²)",          GH_ParamAccess.item);
            pManager.AddNumberParameter("Width",    "W",  "Effective room width  (m)",           GH_ParamAccess.item);
            pManager.AddNumberParameter("Depth",    "D",  "Effective room depth  (m)",           GH_ParamAccess.item);
            pManager.AddTextParameter("Info",       "I",  "Summary string",                     GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            string name    = "Raum";
            int    floor   = 0;
            string typeStr = "Custom";
            double area    = 20.0;
            double width   = 0.0;
            double depth   = 0.0;
            double minH    = 0.0;
            string solar   = "Any";
            var    viewDir = Vector3d.Zero;
            var    near    = new List<string>();
            var    away    = new List<string>();
            double prio    = 0.5;

            if (!DA.GetData(0, ref name))  return;
            DA.GetData(1, ref floor);
            DA.GetData(2, ref typeStr);
            DA.GetData(3, ref area);
            DA.GetData(4, ref width);
            DA.GetData(5, ref depth);
            DA.GetData(6, ref minH);
            DA.GetData(7, ref solar);
            DA.GetData(8, ref viewDir);
            DA.GetDataList(9, near);
            DA.GetDataList(10, away);
            DA.GetData(11, ref prio);

            // Resolve room type
            if (!Enum.TryParse<RoomType>(typeStr, true, out var roomType))
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                    $"Unbekannter Raumtyp '{typeStr}' → Custom");
                roomType = RoomType.Custom;
            }

            // Resolve solar preference
            if (!Enum.TryParse<SolarPreference>(solar, true, out var solarPref))
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                    $"Unbekannte Sonnen-Präferenz '{solar}' → Any");
                solarPref = SolarPreference.Any;
            }
            if (solar == "Any" && roomType != RoomType.Custom)
                solarPref = Room.DefaultSolar(roomType);

            // Resolve dimensions
            bool hasW = width > 0.01;
            bool hasD = depth > 0.01;

            double effW, effD, effA;

            if (hasW && hasD)
            {
                effW = width;
                effD = depth;
                effA = width * depth;
            }
            else if (hasW)
            {
                effW = width;
                effD = area / Math.Max(0.1, width);
                effA = area;
            }
            else if (hasD)
            {
                effD = depth;
                effW = area / Math.Max(0.1, depth);
                effA = area;
            }
            else
            {
                if (area <= 0)
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error,
                        "Fläche muss > 0 m² sein.");
                    return;
                }
                double ratio = 1.4;
                effW = Math.Sqrt(area / ratio);
                effD = area / effW;
                effA = area;
            }

            // Clamp priority
            prio = Math.Clamp(prio, 0, 1);
            if (floor < 0) { floor = 0; AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, "Geschoss < 0 → 0 gesetzt."); }

            var room = new Room
            {
                Name                   = name.Trim(),
                Area                   = effA,
                Floor                  = floor,
                Type                   = roomType,
                SolarPref              = solarPref,
                MustBeNear             = new List<string>(near),
                MustBeAway             = new List<string>(away),
                PreferredViewDirection = viewDir,
                Priority               = roomType != RoomType.Custom
                                         ? Math.Max(prio, Room.DefaultPriority(roomType))
                                         : prio,
                MinCeilingHeight       = minH
            };

            // Store explicit dimensions so the solver doesn't re-estimate
            room.SetExplicitDimensions(effW, effD);

            DA.SetData(0, new GH_Room(room));
            DA.SetData(1, effA);
            DA.SetData(2, effW);
            DA.SetData(3, effD);
            DA.SetData(4, $"[F{floor}] {name}  {effW:F1}×{effD:F1} m  ({effA:F1} m²)  {solarPref}");
        }
    }
}
