using System;
using System.Collections.Generic;
using System.Linq;
using Rhino.Geometry;
using Rhino.Geometry.Intersect;

namespace AndArchitectGH.Core
{
    // ─── Result types ──────────────────────────────────────────────────────────

    public class ShadowResult
    {
        public string RoomName        { get; set; } = "";
        public double ExposureScore   { get; set; }  // fraction of sun positions unobstructed [0,1]
        public double ShadowedScore   { get; set; }  // fraction shadowed by neighbours [0,1]
        public List<double> HourlyExposure { get; set; } = new();  // one value per sun position
    }

    public class SunPosition
    {
        public double AzimuthDeg    { get; set; }
        public double AltitudeDeg   { get; set; }
        public Vector3d Direction   { get; set; }   // unit vector FROM sun TOWARD earth
        public double Hour          { get; set; }
    }

    // ─── Calculator ───────────────────────────────────────────────────────────

    public static class ShadowCalculator
    {
        // ── Sun positions ──────────────────────────────────────────────────────

        /// <summary>
        /// Computes sun positions for the given latitude and date (summer/winter solstice).
        /// Returns only positions where the sun is above the horizon.
        /// </summary>
        public static List<SunPosition> ComputeSunPositions(
            double latitudeDeg,
            bool winter,
            Vector3d northVec,
            int stepsPerDay = 10)
        {
            var positions  = new List<SunPosition>();
            double decl    = (winter ? -23.45 : +23.45) * Math.PI / 180.0;
            double lat     = latitudeDeg * Math.PI / 180.0;

            var east = Vector3d.CrossProduct(Vector3d.ZAxis, northVec);
            east.Unitize();

            double startH = 5.0, endH = 21.0;
            double step   = (endH - startH) / Math.Max(1, stepsPerDay - 1);

            for (int i = 0; i < stepsPerDay; i++)
            {
                double hour   = startH + i * step;
                double omega  = (hour - 12.0) * 15.0 * Math.PI / 180.0;

                double sinAlt = Math.Sin(lat) * Math.Sin(decl)
                              + Math.Cos(lat) * Math.Cos(decl) * Math.Cos(omega);
                double altRad = Math.Asin(Math.Clamp(sinAlt, -1.0, 1.0));
                double altDeg = altRad * 180.0 / Math.PI;

                if (altDeg <= 1.0) continue;  // below or just above horizon → skip

                double cosAz = (Math.Sin(decl) - Math.Sin(lat) * sinAlt)
                             / (Math.Cos(lat) * Math.Cos(altRad) + 1e-9);
                cosAz = Math.Clamp(cosAz, -1.0, 1.0);
                double azRad = Math.Acos(cosAz);
                if (hour > 12.0) azRad = 2 * Math.PI - azRad;
                double azDeg = azRad * 180.0 / Math.PI;

                // Sun direction vector (FROM sun TO earth surface)
                double cosAlt = Math.Cos(altRad);
                var sunFromEarth = northVec * cosAlt * Math.Cos(azRad)
                                 + east     * cosAlt * Math.Sin(azRad)
                                 + Vector3d.ZAxis * sinAlt;
                sunFromEarth.Unitize();
                var sunToEarth = -sunFromEarth;   // ray goes downward toward surfaces

                positions.Add(new SunPosition
                {
                    AzimuthDeg  = azDeg,
                    AltitudeDeg = altDeg,
                    Direction   = sunToEarth,
                    Hour        = hour
                });
            }

            return positions;
        }

        // ── Main shadow analysis ───────────────────────────────────────────────

        /// <summary>
        /// For each room brep, compute:
        ///   - ExposureScore  : fraction of sun positions where the room is unobstructed
        ///   - ShadowedScore  : 1 - ExposureScore (convenient alias)
        ///   - HourlyExposure : per-step exposure (0 = fully shadowed, 1 = fully lit)
        ///   - ShadowMeshes   : projected shadow footprints per sun position (optional)
        /// </summary>
        public static List<ShadowResult> Analyze(
            List<Brep>   rooms,
            List<string> labels,
            List<SunPosition> sunPositions,
            List<Brep>?  context = null)   // additional occluders (neighbouring buildings)
        {
            if (sunPositions.Count == 0)
                return rooms.Select((_, i) => new ShadowResult
                {
                    RoomName = i < labels.Count ? labels[i] : $"Room {i}",
                    ExposureScore = 1.0
                }).ToList();

            // Build occluder mesh list (all rooms + context)
            var allMeshes = new List<Mesh>();
            foreach (var b in rooms)
            {
                var m = BrepToMesh(b);
                if (m != null) allMeshes.Add(m);
            }
            if (context != null)
                foreach (var b in context)
                {
                    var m = BrepToMesh(b);
                    if (m != null) allMeshes.Add(m);
                }

            var results = new List<ShadowResult>();

            for (int ri = 0; ri < rooms.Count; ri++)
            {
                var label   = ri < labels.Count ? labels[ri] : $"Room {ri}";
                var brep    = rooms[ri];
                var bbox    = brep.GetBoundingBox(false);
                var center  = bbox.Center;

                // Sample points on the south-facing faces of this room
                var testPoints = GetFaceSamplePoints(brep, 3);
                if (testPoints.Count == 0)
                    testPoints.Add(center + Vector3d.ZAxis * 0.1);

                // Build occluder meshes excluding self
                var selfMesh = ri < allMeshes.Count ? allMeshes[ri] : null;
                var occluders = allMeshes
                    .Where((m, i) => m != selfMesh)
                    .ToList();

                int totalHits = 0;
                var hourly    = new List<double>();

                foreach (var sun in sunPositions)
                {
                    // Shoot ray from each sample point toward the sun
                    // (opposite of sun.Direction, which points earth-ward)
                    var toSun = -sun.Direction;
                    toSun.Unitize();

                    int pointsLit = 0;
                    foreach (var pt in testPoints)
                    {
                        var origin = pt + toSun * 0.05;  // slight offset to avoid self-intersection
                        var ray    = new Ray3d(origin, toSun);

                        bool shadowed = false;
                        foreach (var occluder in occluders)
                        {
                            double t = Intersection.MeshRay(occluder, ray);
                            if (t >= 0)  // hit
                            {
                                shadowed = true;
                                break;
                            }
                        }
                        if (!shadowed) pointsLit++;
                    }

                    double exposure = (double)pointsLit / testPoints.Count;
                    hourly.Add(exposure);
                    if (exposure > 0.5) totalHits++;
                }

                double expScore = sunPositions.Count > 0
                    ? hourly.Average()
                    : 1.0;

                results.Add(new ShadowResult
                {
                    RoomName      = label,
                    ExposureScore = expScore,
                    ShadowedScore = 1.0 - expScore,
                    HourlyExposure = hourly
                });
            }

            return results;
        }

        // ── Shadow footprint projection ────────────────────────────────────────

        /// <summary>
        /// Projects each room's top face along the sun direction to the ground plane (z=0).
        /// Returns shadow polygons useful for site-context shadow studies.
        /// </summary>
        public static List<Polyline> ProjectShadowFootprints(
            List<Brep> rooms,
            SunPosition sun,
            double groundZ = 0.0)
        {
            var footprints = new List<Polyline>();
            var groundPlane = new Plane(new Point3d(0, 0, groundZ), Vector3d.ZAxis);

            foreach (var brep in rooms)
            {
                // Get top face outline
                var topCurve = ExtractTopOutline(brep);
                if (topCurve == null) continue;

                // Project each point along sun ray to ground
                var pts = new List<Point3d>();
                double divLen = topCurve.GetLength() / 12.0;
                var divPts    = topCurve.DivideByLength(divLen, true, out _);
                if (divPts == null) continue;

                foreach (double t in divPts)
                {
                    var pt  = topCurve.PointAt(t);
                    var ray = new Ray3d(pt, sun.Direction);  // points toward earth
                    double d = (groundZ - pt.Z) / (sun.Direction.Z + 1e-9);
                    var shadow = pt + sun.Direction * d;
                    pts.Add(shadow);
                }

                if (pts.Count >= 3)
                {
                    pts.Add(pts[0]);
                    footprints.Add(new Polyline(pts));
                }
            }

            return footprints;
        }

        // ── Helpers ────────────────────────────────────────────────────────────

        private static Mesh? BrepToMesh(Brep brep)
        {
            var meshes = Mesh.CreateFromBrep(brep,
                new MeshingParameters(0.5));
            if (meshes == null || meshes.Length == 0) return null;
            var joined = new Mesh();
            foreach (var m in meshes) joined.Append(m);
            joined.Compact();
            return joined;
        }

        /// <summary>Returns n×n sample points distributed over each face normal pointing upward or outward.</summary>
        private static List<Point3d> GetFaceSamplePoints(Brep brep, int n = 2)
        {
            var pts = new List<Point3d>();
            foreach (var face in brep.Faces)
            {
                face.GetSurface()?.ClosestPoint(
                    brep.GetBoundingBox(false).Center, out double u, out double v);
                face.ClosestPoint(brep.GetBoundingBox(false).Center, out u, out v);
                var normal = face.NormalAt(u, v);

                // Sample only outward-facing faces (not bottom)
                if (normal.Z < -0.5) continue;

                var bb = face.GetBoundingBox(false);
                for (int i = 0; i < n; i++)
                    for (int j = 0; j < n; j++)
                    {
                        double s = (i + 0.5) / n;
                        double t = (j + 0.5) / n;
                        double fu = bb.Min.X + s * (bb.Max.X - bb.Min.X);
                        double fv = bb.Min.Y + t * (bb.Max.Y - bb.Min.Y);
                        pts.Add(new Point3d(fu, fv, bb.Min.Z + (bb.Max.Z - bb.Min.Z) * 0.5));
                    }
            }
            return pts;
        }

        private static Curve? ExtractTopOutline(Brep brep)
        {
            BrepFace? topFace = null;
            double maxZ = double.MinValue;
            foreach (var f in brep.Faces)
            {
                double z = f.GetBoundingBox(false).Center.Z;
                if (z > maxZ) { maxZ = z; topFace = f; }
            }
            return topFace?.OuterLoop?.To3dCurve();
        }
    }
}
