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
    /// AND_Roof – generates a 3-D roof geometry over the building envelope.
    ///
    /// Supported types (German / English accepted):
    ///   Flat | Flachdach
    ///   Gable | Satteldach
    ///   Hip | Walmdach
    ///   Shed | Pultdach
    ///   Mansard | Mansarddach
    ///   Barrel | Tonnendach
    ///   Butterfly | Schmetterlingsdach
    /// </summary>
    public class RoofGeneratorComponent : GH_Component
    {
        public RoofGeneratorComponent()
            : base("AND Roof", "AND_Roof",
                   "Generate a parametric 3-D roof over the building.\n" +
                   "Types: Flat · Gable (Satteldach) · Hip (Walmdach) · " +
                   "Shed (Pultdach) · Mansard · Barrel (Tonnendach) · Butterfly (Schmetterlingsdach)",
                   "AND Architect", "02 Generate")
        { }

        public override Guid ComponentGuid =>
            new Guid("D9E0F1A2-B3C4-5678-3456-890123456789");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddGenericParameter("Building", "B",
                "AND_Building envelope",                                           GH_ParamAccess.item);
            pManager.AddTextParameter("Type",        "T",
                "Roof type: Flat | Gable | Hip | Shed | Mansard | Barrel | Butterfly\n" +
                "(German aliases: Flachdach | Satteldach | Walmdach | Pultdach | Mansarddach | Tonnendach | Schmetterlingsdach)",
                GH_ParamAccess.item, "Gable");
            pManager.AddNumberParameter("Pitch",     "P",
                "Roof pitch in degrees (ignored for Flat, default 35°)",          GH_ParamAccess.item, 35.0);
            pManager.AddNumberParameter("Overhang",  "Ov",
                "Eave overhang / Dachüberstand (m, default 0.5)",                GH_ParamAccess.item, 0.5);
            pManager.AddBooleanParameter("AtTop",    "AT",
                "True = roof sits on top of building  |  False = at custom Z",   GH_ParamAccess.item, true);
            pManager.AddNumberParameter("BaseZ",     "Z",
                "Base elevation (m) – used when AtTop=False",                     GH_ParamAccess.item, 0.0);

            pManager[4].Optional = true;
            pManager[5].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddBrepParameter("Roof",        "R",  "Roof surface Breps",                GH_ParamAccess.list);
            pManager.AddCurveParameter("RidgeLines", "RL", "Ridge and valley lines",            GH_ParamAccess.list);
            pManager.AddNumberParameter("RidgeH",    "RH", "Ridge height above ground (m)",     GH_ParamAccess.item);
            pManager.AddNumberParameter("EavesH",    "EH", "Eaves / base height above ground (m)", GH_ParamAccess.item);
            pManager.AddTextParameter("Info",        "I",  "Roof type and dimensions",          GH_ParamAccess.item);
        }

        // ── Type alias map ─────────────────────────────────────────────────────

        private static readonly Dictionary<string, RoofType> Aliases =
            new(StringComparer.OrdinalIgnoreCase)
        {
            ["flat"]              = RoofType.Flat,
            ["flachdach"]         = RoofType.Flat,
            ["gable"]             = RoofType.Gable,
            ["satteldach"]        = RoofType.Gable,
            ["hip"]               = RoofType.Hip,
            ["walmdach"]          = RoofType.Hip,
            ["shed"]              = RoofType.Shed,
            ["pultdach"]          = RoofType.Shed,
            ["mansard"]           = RoofType.Mansard,
            ["mansarddach"]       = RoofType.Mansard,
            ["barrel"]            = RoofType.Barrel,
            ["tonnendach"]        = RoofType.Barrel,
            ["butterfly"]         = RoofType.Butterfly,
            ["schmetterlingsdach"]= RoofType.Butterfly
        };

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            var    buildGoo = default(IGH_Goo);
            string typeStr  = "Gable";
            double pitch    = 35.0;
            double overhang = 0.5;
            bool   atTop    = true;
            double baseZ    = 0.0;

            if (!DA.GetData(0, ref buildGoo)) return;
            DA.GetData(1, ref typeStr);
            DA.GetData(2, ref pitch);
            DA.GetData(3, ref overhang);
            DA.GetData(4, ref atTop);
            DA.GetData(5, ref baseZ);

            // Unpack building
            Building? building = null;
            if (buildGoo is GH_Building gb)        building = gb.Value;
            else if (buildGoo?.ScriptVariable() is Building b) building = b;

            if (building == null)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, "Kein gültiges Gebäude.");
                return;
            }

            // Resolve type
            if (!Aliases.TryGetValue(typeStr, out var roofType))
            {
                if (!Enum.TryParse<RoofType>(typeStr, true, out roofType))
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                        $"Unbekannter Dachtyp '{typeStr}' → Satteldach (Gable) verwendet.");
                    roofType = RoofType.Gable;
                }
            }

            // Validate pitch
            pitch = Math.Clamp(pitch, 0.1, 89.9);
            overhang = Math.Max(0, overhang);

            // Base elevation
            var bb    = building.GetBoundingBox();
            double ez = atTop ? building.TotalHeight : baseZ;

            // Generate
            var roof = RoofGenerator.Generate(
                bb.Min.X, bb.Min.Y,
                building.FootprintWidth,
                building.FootprintDepth,
                ez, pitch, roofType, overhang);

            // Info string
            string info =
                $"Dachtyp: {roofType}  " +
                $"Neigung: {pitch:F1}°  " +
                $"Traufhöhe: {ez:F2} m  " +
                $"Firsthöhe: {roof.RidgeHeight:F2} m  " +
                $"Überstand: {overhang:F2} m";

            DA.SetDataList(0, roof.Surfaces);
            DA.SetDataList(1, roof.RidgeLines);
            DA.SetData(2, roof.RidgeHeight);
            DA.SetData(3, ez);
            DA.SetData(4, info);
        }
    }
}
