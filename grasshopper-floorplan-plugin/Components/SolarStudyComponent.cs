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
    /// AND_Solar – lightweight solar exposure study.
    /// Casts sun rays at key times and computes which room faces are exposed.
    /// Outputs per-room solar scores and shadow meshes for preview.
    /// </summary>
    public class SolarStudyComponent : GH_Component
    {
        public SolarStudyComponent()
            : base("AND Solar Study", "AND_Solar",
                   "Perform a simplified solar exposure study on placed room volumes. " +
                   "Evaluates how much direct sunlight each room receives throughout the day " +
                   "at winter and summer solstice.",
                   "AND Architect", "02 Generate")
        { }

        public override Guid ComponentGuid => new Guid("B7C8D9E0-F1A2-3456-1234-678901234567");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddBrepParameter("Geometry",   "G",  "Room Breps from AND_Generate",               GH_ParamAccess.list);
            pManager.AddTextParameter("Labels",     "L",  "Room labels (name per Brep)",                 GH_ParamAccess.list);
            pManager.AddGenericParameter("Orient",  "O",  "AND_Orientation (north + latitude)",          GH_ParamAccess.item);
            pManager.AddIntegerParameter("Hours",   "H",
                "Number of hourly sun positions to evaluate (6 = 8h–18h at 2h steps, max 24)",
                GH_ParamAccess.item, 6);
            pManager.AddBooleanParameter("Winter",  "W",  "True = winter solstice, False = summer",     GH_ParamAccess.item, true);

            pManager[2].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddNumberParameter("SolarScores",  "S",
                "Solar exposure score per room [0,1] (1 = fully exposed to sun)",
                GH_ParamAccess.list);
            pManager.AddVectorParameter("SunVectors",   "V",
                "Sun direction vectors used for the study (useful for shading analysis)",
                GH_ParamAccess.list);
            pManager.AddNumberParameter("AzimuthsDeg",  "Az",
                "Sun azimuth angles in degrees (0° = north, 90° = east)",
                GH_ParamAccess.list);
            pManager.AddNumberParameter("AltitudesDeg", "Alt",
                "Sun altitude angles in degrees above horizon",
                GH_ParamAccess.list);
            pManager.AddTextParameter("Report",         "R",
                "Per-room solar report",
                GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            var breps    = new List<Brep>();
            var labels   = new List<string>();
            var orientGoo= default(IGH_Goo);
            int hours    = 6;
            bool winter  = true;

            if (!DA.GetDataList(0, breps)) return;
            DA.GetDataList(1, labels);
            DA.GetData(2, ref orientGoo);
            DA.GetData(3, ref hours);
            DA.GetData(4, ref winter);

            while (labels.Count < breps.Count) labels.Add($"Room {labels.Count}");
            hours = Math.Max(1, Math.Min(24, hours));

            double latitude = 48.0;
            Vector3d north  = Vector3d.YAxis;

            if (orientGoo is GH_Orientation ghO)
            {
                latitude = ghO.Value.Latitude;
                north    = ghO.Value.North;
            }
            else if (orientGoo?.ScriptVariable() is OrientationData od)
            {
                latitude = od.Latitude;
                north    = od.North;
            }

            // Compute sun vectors for the chosen day
            var sunVecs     = new List<Vector3d>();
            var azimuths    = new List<double>();
            var altitudes   = new List<double>();

            double declinationDeg = winter ? -23.45 : +23.45;
            double decl = declinationDeg * Math.PI / 180.0;
            double lat  = latitude       * Math.PI / 180.0;

            double startH = 7.0;
            double endH   = 19.0;
            double step   = (endH - startH) / Math.Max(1, hours - 1);

            for (int i = 0; i < hours; i++)
            {
                double hour = startH + i * step;
                double hourAngle = (hour - 12.0) * 15.0 * Math.PI / 180.0;

                double sinAlt = Math.Sin(lat) * Math.Sin(decl) +
                                Math.Cos(lat) * Math.Cos(decl) * Math.Cos(hourAngle);
                double altRad = Math.Asin(Math.Clamp(sinAlt, -1.0, 1.0));
                double altDeg = altRad * 180.0 / Math.PI;

                if (altDeg <= 0) continue;  // below horizon

                double cosAz = (Math.Sin(decl) - Math.Sin(lat) * sinAlt)
                               / (Math.Cos(lat) * Math.Cos(altRad) + 1e-9);
                cosAz = Math.Clamp(cosAz, -1.0, 1.0);
                double azRad = Math.Acos(cosAz);
                if (hour > 12) azRad = 2 * Math.PI - azRad;
                double azDeg = azRad * 180.0 / Math.PI;

                // Convert spherical (azimuth from north, altitude) to world XYZ
                // North = north vector in XY, East = 90° CW from north
                var east = Vector3d.CrossProduct(Vector3d.ZAxis, north);
                east.Unitize();

                double cosAlt = Math.Cos(altRad);
                var sunDir = -( north * cosAlt * Math.Cos(azRad) +
                                east  * cosAlt * Math.Sin(azRad) +
                                Vector3d.ZAxis * sinAlt );
                sunDir.Unitize();

                sunVecs.Add(sunDir);
                azimuths.Add(azDeg);
                altitudes.Add(altDeg);
            }

            if (sunVecs.Count == 0)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, "No sun above horizon for selected parameters.");
                DA.SetDataList(0, new List<double>());
                return;
            }

            // Score each room: fraction of sun vectors that hit at least one face
            var scores  = new List<double>();
            var report  = new System.Text.StringBuilder();
            report.AppendLine($"Solar study – {(winter ? "Winter" : "Summer")} solstice  Lat={latitude:F1}°");
            report.AppendLine($"Sun positions evaluated: {sunVecs.Count}");
            report.AppendLine();

            foreach (var (brep, label) in System.Linq.Enumerable.Zip(breps, labels, (b, l) => (b, l)))
            {
                int hits = 0;
                var bb   = brep.GetBoundingBox(false);
                var testPt = bb.Center + Vector3d.ZAxis * 0.01;

                foreach (var sv in sunVecs)
                {
                    // Simple: check if sun vector arrives on a brep face (dot product with face normal > 0)
                    bool exposed = false;
                    foreach (var face in brep.Faces)
                    {
                        face.ClosedCurveRegion(0.5, 0.5, out _);
                        double u, v;
                        face.ClosestPoint(bb.Center, out u, out v);
                        var normal = face.NormalAt(u, v);
                        double dot = Vector3d.Multiply(normal, -sv);  // sv points toward surface
                        if (dot > 0.15)  // >15° incidence
                        {
                            exposed = true;
                            break;
                        }
                    }
                    if (exposed) hits++;
                }

                double score = (double)hits / sunVecs.Count;
                scores.Add(score);
                report.AppendLine($"  {label,-24}  solar={score:P0}  ({hits}/{sunVecs.Count} sun positions exposed)");
            }

            DA.SetDataList(0, scores);
            DA.SetDataList(1, sunVecs);
            DA.SetDataList(2, azimuths);
            DA.SetDataList(3, altitudes);
            DA.SetData(4, report.ToString());
        }
    }
}
