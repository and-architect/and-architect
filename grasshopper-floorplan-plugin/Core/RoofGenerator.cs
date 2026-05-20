using System;
using System.Collections.Generic;
using Rhino.Geometry;

namespace AndArchitectGH.Core
{
    public enum RoofType
    {
        Flat,       // Flachdach
        Gable,      // Satteldach
        Hip,        // Walmdach
        Shed,       // Pultdach
        Mansard,    // Mansarddach
        Barrel,     // Tonnendach (zylindrisch)
        Butterfly   // Schmetterlingsdach (V-Form)
    }

    public class RoofGeometry
    {
        public List<Brep>  Surfaces   { get; set; } = new();
        public List<Curve> RidgeLines { get; set; } = new();
        public double      RidgeHeight { get; set; }
        public RoofType    Type        { get; set; }
    }

    public static class RoofGenerator
    {
        /// <summary>
        /// Generates a roof Brep over the given rectangular footprint.
        /// </summary>
        /// <param name="footprintMinX">West edge X</param>
        /// <param name="footprintMinY">South edge Y</param>
        /// <param name="footprintWidth">E-W dimension (m)</param>
        /// <param name="footprintDepth">N-S dimension (m)</param>
        /// <param name="baseZ">Z of top-floor ceiling / eaves level</param>
        /// <param name="pitchDeg">Roof pitch in degrees (ignored for Flat)</param>
        /// <param name="type">Roof shape</param>
        /// <param name="eaveOverhang">Traufüberstand – overhang on the eave sides (m)</param>
        /// <param name="gableOverhang">Ortgangüberstand – overhang on the gable ends (m); -1 = same as eaveOverhang</param>
        public static RoofGeometry Generate(
            double   footprintMinX,
            double   footprintMinY,
            double   footprintWidth,
            double   footprintDepth,
            double   baseZ,
            double   pitchDeg      = 35.0,
            RoofType type          = RoofType.Gable,
            double   eaveOverhang  = 0.5,
            double   gableOverhang = -1.0)
        {
            if (gableOverhang < 0) gableOverhang = eaveOverhang;

            // Gable roof: ridge runs N-S, eaves are E+W sides, gable ends are N+S
            // For all other types we use eaveOverhang uniformly
            bool distinctOverhang = (type == RoofType.Gable || type == RoofType.Butterfly)
                                    && Math.Abs(eaveOverhang - gableOverhang) > 1e-6;

            double x0 = footprintMinX - eaveOverhang;
            double y0 = footprintMinY - (distinctOverhang ? gableOverhang : eaveOverhang);
            double x1 = footprintMinX + footprintWidth  + eaveOverhang;
            double y1 = footprintMinY + footprintDepth  + (distinctOverhang ? gableOverhang : eaveOverhang);
            double w  = x1 - x0;
            double d  = y1 - y0;

            return type switch
            {
                RoofType.Flat      => GenerateFlat(x0, y0, x1, y1, baseZ),
                RoofType.Gable     => GenerateGable(x0, y0, x1, y1, baseZ, pitchDeg),
                RoofType.Hip       => GenerateHip(x0, y0, x1, y1, baseZ, pitchDeg),
                RoofType.Shed      => GenerateShed(x0, y0, x1, y1, baseZ, pitchDeg),
                RoofType.Mansard   => GenerateMansard(x0, y0, x1, y1, baseZ, pitchDeg),
                RoofType.Barrel    => GenerateBarrel(x0, y0, x1, y1, baseZ, pitchDeg),
                RoofType.Butterfly => GenerateButterfly(x0, y0, x1, y1, baseZ, pitchDeg),
                _                  => GenerateFlat(x0, y0, x1, y1, baseZ)
            };
        }

        // ── Flat ──────────────────────────────────────────────────────────────

        private static RoofGeometry GenerateFlat(
            double x0, double y0, double x1, double y1, double z)
        {
            var corners = new Point3d[]
            {
                new(x0, y0, z), new(x1, y0, z),
                new(x1, y1, z), new(x0, y1, z)
            };
            var brep = Brep.CreateFromCornerPoints(corners[0], corners[1], corners[2], corners[3], 1e-6);
            return new RoofGeometry
            {
                Type = RoofType.Flat,
                Surfaces = brep != null ? new List<Brep> { brep } : new(),
                RidgeHeight = z
            };
        }

        // ── Gable (Satteldach) ────────────────────────────────────────────────

        private static RoofGeometry GenerateGable(
            double x0, double y0, double x1, double y1, double z, double pitchDeg)
        {
            double cx   = (x0 + x1) * 0.5;
            double halfW = (x1 - x0) * 0.5;
            double rise = halfW * Math.Tan(pitchDeg * Math.PI / 180.0);
            double zr   = z + rise;

            // Ridge along N-S axis at centre X
            var ridgeS = new Point3d(cx, y0, zr);
            var ridgeN = new Point3d(cx, y1, zr);

            var p = new Point3d[]
            {
                new(x0, y0, z), new(x1, y0, z),
                new(x1, y1, z), new(x0, y1, z)
            };

            var surfaces = new List<Brep>();

            // West slope: p[0], ridgeS, ridgeN, p[3]
            AddQuadBrep(surfaces, p[0], ridgeS, ridgeN, p[3]);
            // East slope: ridgeS, p[1], p[2], ridgeN
            AddQuadBrep(surfaces, ridgeS, p[1], p[2], ridgeN);
            // South gable (triangle): p[0], p[1], ridgeS
            AddTriBrep(surfaces, p[0], p[1], ridgeS);
            // North gable (triangle): p[3], ridgeN, p[2]
            AddTriBrep(surfaces, p[3], ridgeN, p[2]);

            return new RoofGeometry
            {
                Type = RoofType.Gable,
                Surfaces = surfaces,
                RidgeLines = new List<Curve> { new LineCurve(ridgeS, ridgeN) },
                RidgeHeight = zr
            };
        }

        // ── Hip (Walmdach) ────────────────────────────────────────────────────

        private static RoofGeometry GenerateHip(
            double x0, double y0, double x1, double y1, double z, double pitchDeg)
        {
            double cx   = (x0 + x1) * 0.5;
            double cy   = (y0 + y1) * 0.5;
            double hw   = (x1 - x0) * 0.5;
            double hd   = (y1 - y0) * 0.5;
            double rise = Math.Min(hw, hd) * Math.Tan(pitchDeg * Math.PI / 180.0);
            double zr   = z + rise;

            // Hip roof: ridge runs E-W if width < depth, else N-S
            bool ridgeNS = hw < hd;
            double ridgeLen = ridgeNS ? Math.Abs(hd - hw) : Math.Abs(hw - hd);

            Point3d ridgeE, ridgeW, ridgeN, ridgeS;

            if (ridgeNS)
            {
                ridgeS = new(cx, cy - ridgeLen, zr);
                ridgeN = new(cx, cy + ridgeLen, zr);
                ridgeE = ridgeW = Point3d.Unset;
            }
            else
            {
                ridgeW = new(cx - ridgeLen, cy, zr);
                ridgeE = new(cx + ridgeLen, cy, zr);
                ridgeS = ridgeN = Point3d.Unset;
            }

            var p = new Point3d[]
            {
                new(x0, y0, z), new(x1, y0, z),
                new(x1, y1, z), new(x0, y1, z)
            };

            var surfaces = new List<Brep>();
            var ridges   = new List<Curve>();

            if (ridgeNS)
            {
                // West slope: p0, p3, ridgeN, ridgeS (trapezoid)
                AddQuadBrep(surfaces, p[0], p[3], ridgeN, ridgeS);
                // East slope: p1, ridgeS, ridgeN, p2
                AddQuadBrep(surfaces, p[1], ridgeS, ridgeN, p[2]);
                // South hip (triangle)
                AddTriBrep(surfaces, p[0], p[1], ridgeS);
                // North hip (triangle)
                AddTriBrep(surfaces, p[3], ridgeN, p[2]);
                ridges.Add(new LineCurve(ridgeS, ridgeN));
            }
            else
            {
                // South slope: p0, p1, ridgeE, ridgeW
                AddQuadBrep(surfaces, p[0], p[1], ridgeE, ridgeW);
                // North slope: p3, ridgeW, ridgeE, p2
                AddQuadBrep(surfaces, p[3], ridgeW, ridgeE, p[2]);
                // West hip (triangle)
                AddTriBrep(surfaces, p[0], ridgeW, p[3]);
                // East hip (triangle)
                AddTriBrep(surfaces, p[1], p[2], ridgeE);
                ridges.Add(new LineCurve(ridgeW, ridgeE));
            }

            return new RoofGeometry
            {
                Type = RoofType.Hip,
                Surfaces = surfaces,
                RidgeLines = ridges,
                RidgeHeight = zr
            };
        }

        // ── Shed / Pultdach ───────────────────────────────────────────────────

        private static RoofGeometry GenerateShed(
            double x0, double y0, double x1, double y1, double z, double pitchDeg)
        {
            double rise = (y1 - y0) * Math.Tan(pitchDeg * Math.PI / 180.0);
            double zTop = z + rise;

            var surfaces = new List<Brep>();
            AddQuadBrep(surfaces,
                new(x0, y0, z),  new(x1, y0, z),
                new(x1, y1, zTop), new(x0, y1, zTop));

            return new RoofGeometry
            {
                Type = RoofType.Shed,
                Surfaces = surfaces,
                RidgeHeight = zTop
            };
        }

        // ── Mansard ───────────────────────────────────────────────────────────

        private static RoofGeometry GenerateMansard(
            double x0, double y0, double x1, double y1, double z, double pitchDeg)
        {
            double inset = Math.Min((x1 - x0), (y1 - y0)) * 0.25;
            double steepPitch = Math.Min(pitchDeg + 30, 80);
            double shallowPitch = pitchDeg;

            double lowerH  = inset * Math.Tan(steepPitch  * Math.PI / 180.0);
            double upperH  = inset * Math.Tan(shallowPitch * Math.PI / 180.0);
            double zBreak  = z + lowerH;
            double zTop    = zBreak + upperH;

            double xi0 = x0 + inset, yi0 = y0 + inset;
            double xi1 = x1 - inset, yi1 = y1 - inset;

            var surfaces = new List<Brep>();

            // Lower steep slopes (4 faces)
            AddQuadBrep(surfaces, new(x0,y0,z),  new(x1,y0,z),  new(xi1,yi0,zBreak), new(xi0,yi0,zBreak));
            AddQuadBrep(surfaces, new(x1,y0,z),  new(x1,y1,z),  new(xi1,yi1,zBreak), new(xi1,yi0,zBreak));
            AddQuadBrep(surfaces, new(x1,y1,z),  new(x0,y1,z),  new(xi0,yi1,zBreak), new(xi1,yi1,zBreak));
            AddQuadBrep(surfaces, new(x0,y1,z),  new(x0,y0,z),  new(xi0,yi0,zBreak), new(xi0,yi1,zBreak));

            // Upper shallow slopes → use gable on inner rectangle
            var inner = GenerateGable(xi0, yi0, xi1, yi1, zBreak, shallowPitch / 2.0);
            surfaces.AddRange(inner.Surfaces);

            return new RoofGeometry
            {
                Type = RoofType.Mansard,
                Surfaces = surfaces,
                RidgeLines = inner.RidgeLines,
                RidgeHeight = inner.RidgeHeight
            };
        }

        // ── Barrel / Tonnendach ───────────────────────────────────────────────

        private static RoofGeometry GenerateBarrel(
            double x0, double y0, double x1, double y1, double z, double pitchDeg)
        {
            double w    = x1 - x0;
            double r    = w * 0.5 / Math.Cos((90 - pitchDeg) * Math.PI / 180.0);
            double rise = r - Math.Sqrt(Math.Max(0, r * r - (w * 0.5) * (w * 0.5)));
            double cx   = (x0 + x1) * 0.5;

            int seg = 12;
            double angStart = -Math.PI * 0.5;
            double angEnd   =  Math.PI * 0.5;

            var surfaces = new List<Brep>();

            for (int i = 0; i < seg; i++)
            {
                double a0 = angStart + (angEnd - angStart) * i       / seg;
                double a1 = angStart + (angEnd - angStart) * (i + 1) / seg;

                double xl0 = cx + r * Math.Cos(a0);
                double zl0 = z  + r * Math.Sin(a0) + r;
                double xl1 = cx + r * Math.Cos(a1);
                double zl1 = z  + r * Math.Sin(a1) + r;

                AddQuadBrep(surfaces,
                    new(xl0, y0, zl0), new(xl1, y0, zl1),
                    new(xl1, y1, zl1), new(xl0, y1, zl0));
            }

            return new RoofGeometry
            {
                Type = RoofType.Barrel,
                Surfaces = surfaces,
                RidgeHeight = z + r
            };
        }

        // ── Butterfly / Schmetterlingsdach ────────────────────────────────────

        private static RoofGeometry GenerateButterfly(
            double x0, double y0, double x1, double y1, double z, double pitchDeg)
        {
            double cx  = (x0 + x1) * 0.5;
            double hw  = (x1 - x0) * 0.5;
            double dip = hw * Math.Tan(pitchDeg * Math.PI / 180.0);
            double zV  = z - dip;   // valley is below eaves

            var ridgeV = new Point3d(cx, y0, zV);
            var ridgeN = new Point3d(cx, y1, zV);

            var surfaces = new List<Brep>();
            // West wing slopes DOWN toward centre
            AddQuadBrep(surfaces, new(x0,y0,z), ridgeV, ridgeN, new(x0,y1,z));
            // East wing
            AddQuadBrep(surfaces, ridgeV, new(x1,y0,z), new(x1,y1,z), ridgeN);
            // Gable ends
            AddTriBrep(surfaces, new(x0,y0,z), ridgeV, new(x1,y0,z));
            AddTriBrep(surfaces, new(x0,y1,z), new(x1,y1,z), ridgeN);

            return new RoofGeometry
            {
                Type = RoofType.Butterfly,
                Surfaces = surfaces,
                RidgeLines = new List<Curve> { new LineCurve(ridgeV, ridgeN) },
                RidgeHeight = zV
            };
        }

        // ── Geometry helpers ──────────────────────────────────────────────────

        private static void AddQuadBrep(List<Brep> list,
            Point3d a, Point3d b, Point3d c, Point3d d)
        {
            var b1 = Brep.CreateFromCornerPoints(a, b, c, d, 1e-6);
            if (b1 != null) list.Add(b1);
        }

        private static void AddTriBrep(List<Brep> list,
            Point3d a, Point3d b, Point3d c)
        {
            var b1 = Brep.CreateFromCornerPoints(a, b, c, 1e-6);
            if (b1 != null) list.Add(b1);
        }
    }
}
