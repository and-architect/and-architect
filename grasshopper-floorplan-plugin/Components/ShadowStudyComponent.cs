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
    /// AND_Shadow – comprehensive shadow and solar exposure study.
    /// Ray-casts from each room toward the sun; neighbouring rooms act as occluders.
    /// Outputs per-room exposure scores, shadow footprints and hourly exposure curves.
    /// </summary>
    public class ShadowStudyComponent : GH_Component
    {
        public ShadowStudyComponent()
            : base("AND Shadow Study", "AND_Shadow",
                   "Solar exposure + shadow casting study.\n" +
                   "Computes mutual shading between room volumes and external context.\n" +
                   "Outputs per-room exposure scores and shadow footprints for selected sun positions.",
                   "AND Architect", "02 Generate")
        { }

        public override Guid ComponentGuid =>
            new Guid("C8D9E0F1-A2B3-4567-2345-789012345678");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddBrepParameter("Geometry",    "G",
                "Room Breps from AND_Generate",                                     GH_ParamAccess.list);
            pManager.AddTextParameter("Labels",      "L",
                "Room labels from AND_Generate",                                    GH_ParamAccess.list);
            pManager.AddGenericParameter("Orient",   "O",
                "AND_Orientation (north vector + latitude)",                        GH_ParamAccess.item);
            pManager.AddBrepParameter("Context",     "C",
                "Additional occluder Breps (neighbouring buildings, trees …)",     GH_ParamAccess.list);
            pManager.AddIntegerParameter("Steps",    "St",
                "Sun positions per day  (6–20 recommended)",                        GH_ParamAccess.item, 10);
            pManager.AddBooleanParameter("Winter",   "W",
                "True = winter solstice  |  False = summer solstice",              GH_ParamAccess.item, true);
            pManager.AddBooleanParameter("Summer",   "Su",
                "True = also compute summer solstice and output average",          GH_ParamAccess.item, false);
            pManager.AddIntegerParameter("ShadowIdx","SI",
                "Index of sun position for shadow footprint output (0 = first above horizon)", GH_ParamAccess.item, 3);

            pManager[2].Optional = true;
            pManager[3].Optional = true;
            pManager[7].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddNumberParameter("Exposure",     "E",
                "Solar exposure score per room [0,1]  (1 = fully unobstructed all day)",
                GH_ParamAccess.list);
            pManager.AddNumberParameter("Shadow",       "Sh",
                "Shadow fraction per room [0,1]  (1 = fully shadowed all day)",
                GH_ParamAccess.list);
            pManager.AddNumberParameter("ExpWinter",    "EW",
                "Winter solstice exposure score per room",                          GH_ParamAccess.list);
            pManager.AddNumberParameter("ExpSummer",    "ES",
                "Summer solstice exposure score per room (needs Summer=True)",      GH_ParamAccess.list);
            pManager.AddCurveParameter("ShadowFootprints","SF",
                "Shadow footprint curves on ground plane for selected sun position",GH_ParamAccess.list);
            pManager.AddVectorParameter("SunVectors",   "SV",
                "Sun direction vectors for the studied day",                        GH_ParamAccess.list);
            pManager.AddNumberParameter("Azimuths",     "Az",
                "Sun azimuth angles [°]  (0°=N, 90°=E, 180°=S, 270°=W)",          GH_ParamAccess.list);
            pManager.AddNumberParameter("Altitudes",    "Alt",
                "Sun altitude angles [°] above horizon",                            GH_ParamAccess.list);
            pManager.AddTextParameter("Report",         "R",
                "Detailed per-room shadow report",                                  GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            var breps    = new List<Brep>();
            var labels   = new List<string>();
            var orientGoo= default(IGH_Goo);
            var context  = new List<Brep>();
            int steps    = 10;
            bool winter  = true;
            bool summer  = false;
            int  shadowIdx = 3;

            if (!DA.GetDataList(0, breps)) return;
            DA.GetDataList(1, labels);
            DA.GetData(2, ref orientGoo);
            DA.GetDataList(3, context);
            DA.GetData(4, ref steps);
            DA.GetData(5, ref winter);
            DA.GetData(6, ref summer);
            DA.GetData(7, ref shadowIdx);

            while (labels.Count < breps.Count)
                labels.Add($"Room {labels.Count}");

            steps = Math.Clamp(steps, 2, 24);

            // Orientation
            double latitude = 48.0;
            var    north    = Vector3d.YAxis;
            if (orientGoo is GH_Orientation ghO)
                { latitude = ghO.Value.Latitude; north = ghO.Value.North; }
            else if (orientGoo?.ScriptVariable() is OrientationData od)
                { latitude = od.Latitude; north = od.North; }

            // ── Winter study ──────────────────────────────────────────────────
            var sunW = ShadowCalculator.ComputeSunPositions(latitude, true,  north, steps);
            var resW = ShadowCalculator.Analyze(breps, labels, sunW,
                       context.Count > 0 ? context : null);

            // ── Summer study (optional) ───────────────────────────────────────
            List<ShadowResult>? resS = null;
            if (summer)
            {
                var sunS = ShadowCalculator.ComputeSunPositions(latitude, false, north, steps);
                resS = ShadowCalculator.Analyze(breps, labels, sunS,
                       context.Count > 0 ? context : null);
            }

            // ── Combined exposure (average of both if requested) ──────────────
            var expCombined = new List<double>();
            var expWinter   = resW.Select(r => r.ExposureScore).ToList();
            var expSummer   = resS?.Select(r => r.ExposureScore).ToList() ?? new List<double>();
            var shadowScore = resW.Select(r => r.ShadowedScore).ToList();

            for (int i = 0; i < resW.Count; i++)
            {
                double comb = resS != null && i < resS.Count
                    ? (resW[i].ExposureScore + resS[i].ExposureScore) * 0.5
                    : resW[i].ExposureScore;
                expCombined.Add(comb);
            }

            // ── Shadow footprints for selected sun position ───────────────────
            var footprints = new List<Curve>();
            var activeSun  = winter ? sunW : (resS != null
                ? ShadowCalculator.ComputeSunPositions(latitude, false, north, steps)
                : sunW);

            if (activeSun.Count > 0)
            {
                int si = Math.Clamp(shadowIdx, 0, activeSun.Count - 1);
                var polys = ShadowCalculator.ProjectShadowFootprints(breps, activeSun[si]);
                footprints.AddRange(polys.Select(p => p.ToNurbsCurve() as Curve));
            }

            // ── Report ────────────────────────────────────────────────────────
            var sb = new System.Text.StringBuilder();
            sb.AppendLine($"Schatten-Studie  Lat={latitude:F1}°  {(winter ? "Winter" : "Sommer")}-Sonnenwende");
            sb.AppendLine($"Sonnen-Positionen: {sunW.Count}  Raumanzahl: {breps.Count}");
            sb.AppendLine();

            for (int i = 0; i < resW.Count; i++)
            {
                sb.Append($"  {resW[i].RoomName,-22}");
                sb.Append($"  Winter={resW[i].ExposureScore:P0}");
                if (resS != null && i < resS.Count)
                    sb.Append($"  Sommer={resS[i].ExposureScore:P0}");
                sb.AppendLine($"  Schatten={resW[i].ShadowedScore:P0}");
            }

            // ── Outputs ───────────────────────────────────────────────────────
            DA.SetDataList(0, expCombined);
            DA.SetDataList(1, shadowScore);
            DA.SetDataList(2, expWinter);
            DA.SetDataList(3, expSummer.Count > 0 ? expSummer : expWinter);
            DA.SetDataList(4, footprints);
            DA.SetDataList(5, activeSun.Select(s => s.Direction).ToList());
            DA.SetDataList(6, activeSun.Select(s => s.AzimuthDeg).ToList());
            DA.SetDataList(7, activeSun.Select(s => s.AltitudeDeg).ToList());
            DA.SetData(8, sb.ToString());
        }
    }
}
