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
    /// AND_Room – defines a single room with all spatial and environmental preferences.
    /// </summary>
    public class RoomDefinitionComponent : GH_Component
    {
        public RoomDefinitionComponent()
            : base("AND Room", "AND_Room",
                   "Define a room with area, floor level, solar preference, view direction and adjacency rules.",
                   "AND Architect", "01 Setup")
        { }

        public override Guid ComponentGuid => new Guid("B1C2D3E4-F5A6-7890-BCDE-F12345678901");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddTextParameter("Name",     "N",  "Room name (e.g. 'Living Room')", GH_ParamAccess.item, "Room");
            pManager.AddNumberParameter("Area",   "A",  "Room area in m²",                GH_ParamAccess.item, 20.0);
            pManager.AddIntegerParameter("Floor", "FL", "Floor level (0 = ground floor)",  GH_ParamAccess.item, 0);
            pManager.AddTextParameter("Type",     "T",
                "Room type: LivingRoom | Kitchen | DiningRoom | MasterBedroom | Bedroom | " +
                "ChildRoom | Bathroom | WC | Office | Library | Hallway | Staircase | " +
                "Storage | Garage | Balcony | Terrace | Custom",
                GH_ParamAccess.item, "Custom");
            pManager.AddTextParameter("Solar",    "S",
                "Solar/orientation preference: South | East | West | North | Any",
                GH_ParamAccess.item, "Any");
            pManager.AddTextParameter("NearRooms","NR",
                "Room names this room must be adjacent to (list)",
                GH_ParamAccess.list);
            pManager.AddTextParameter("AwayRooms","AR",
                "Room names this room should NOT be adjacent to (list)",
                GH_ParamAccess.list);
            pManager.AddVectorParameter("ViewDir","VD",
                "Preferred façade direction (world-space XY; leave zero for no preference)",
                GH_ParamAccess.item, Vector3d.Zero);
            pManager.AddNumberParameter("Priority","P",
                "Placement priority 0–1 (higher = placed first and better positioned)",
                GH_ParamAccess.item, 0.5);

            // Make optional inputs so the component works with minimal wiring
            pManager[5].Optional = true;
            pManager[6].Optional = true;
            pManager[7].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddGenericParameter("Room", "R", "Room definition", GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            string name    = "Room";
            double area    = 20.0;
            int    floor   = 0;
            string typeStr = "Custom";
            string solar   = "Any";
            var    near    = new List<string>();
            var    away    = new List<string>();
            var    viewDir = Vector3d.Zero;
            double prio    = 0.5;

            if (!DA.GetData(0, ref name))   return;
            if (!DA.GetData(1, ref area))   return;
            DA.GetData(2, ref floor);
            DA.GetData(3, ref typeStr);
            DA.GetData(4, ref solar);
            DA.GetDataList(5, near);
            DA.GetDataList(6, away);
            DA.GetData(7, ref viewDir);
            DA.GetData(8, ref prio);

            if (area <= 0)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Area must be > 0 m².");
                return;
            }
            if (floor < 0)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, "Floor level < 0 – using 0.");
                floor = 0;
            }

            if (!Enum.TryParse<RoomType>(typeStr, true, out var roomType))
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                    $"Unknown room type '{typeStr}', using Custom.");
                roomType = RoomType.Custom;
            }

            if (!Enum.TryParse<SolarPreference>(solar, true, out var solarPref))
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                    $"Unknown solar preference '{solar}', using Any.");
                solarPref = SolarPreference.Any;
            }

            // Apply defaults when type is known and user left solar at "Any"
            if (solar == "Any" && roomType != RoomType.Custom)
                solarPref = Room.DefaultSolar(roomType);

            if (prio < 0 || prio > 1)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                    "Priority clamped to [0,1].");
                prio = Math.Max(0, Math.Min(1, prio));
            }

            var room = new Room
            {
                Name                  = name.Trim(),
                Area                  = area,
                Floor                 = floor,
                Type                  = roomType,
                SolarPref             = solarPref,
                MustBeNear            = new List<string>(near),
                MustBeAway            = new List<string>(away),
                PreferredViewDirection = viewDir,
                Priority              = prio
            };

            if (roomType != RoomType.Custom)
                room.Priority = Math.Max(prio, Room.DefaultPriority(roomType));

            DA.SetData(0, new GH_Room(room));
        }
    }
}
