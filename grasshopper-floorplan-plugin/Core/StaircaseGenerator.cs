using System;
using System.Collections.Generic;
using Rhino.Geometry;

namespace AndArchitectGH.Core
{
    public enum StaircaseType
    {
        Straight,   // einläufig gerade
        LShape,     // einläufig L-förmig
        UShape,     // zweiläufig U-förmig
        Spiral      // Wendeltreppe
    }

    public class StaircaseDefinition
    {
        public string Name { get; set; } = "Treppenhaus";
        public StaircaseType Type { get; set; } = StaircaseType.Straight;
        public int FromFloor { get; set; } = 0;
        public int ToFloor   { get; set; } = 1;
        public double Width  { get; set; } = 1.2;     // lichte Treppenbreite (m)
        public double TreadDepth  { get; set; } = 0.25; // Auftrittstiefe  (m)
        public double RiserHeight { get; set; } = 0.175; // Stufenhöhe    (m)

        // Footprint bounds (set by solver after placement)
        public double FootprintWidth  => ComputeFootprintW();
        public double FootprintDepth  => ComputeFootprintD();

        private double ComputeFootprintW() => Type switch
        {
            StaircaseType.Straight => Width,
            StaircaseType.LShape   => Width * 2,
            StaircaseType.UShape   => Width * 2,
            StaircaseType.Spiral   => Width * 2,
            _                      => Width
        };

        private double ComputeFootprintD() => Type switch
        {
            StaircaseType.Straight => StepsPerFlight() * TreadDepth,
            StaircaseType.LShape   => StepsPerFlight() * TreadDepth * 0.55,
            StaircaseType.UShape   => StepsPerFlight() * TreadDepth * 0.55,
            StaircaseType.Spiral   => Width * 2,
            _                      => 4.0
        };

        public int StepsPerFlight()
        {
            // Steps needed to cover one floor height (stored on Building)
            // We use a default floor height of 3.0 m here; solver sets real value
            return (int)Math.Ceiling(3.0 / RiserHeight);
        }

        public override string ToString() =>
            $"{Name}  {Type}  F{FromFloor}→F{ToFloor}  {Width:F2}m breit";
    }

    public class StaircaseGeometry
    {
        public List<Brep>  Volumes   { get; set; } = new(); // stairwell box per floor
        public List<Brep>  Treads    { get; set; } = new(); // individual step slabs
        public List<Curve> Handrails { get; set; } = new(); // railing lines
        public Point3d     EntryPt   { get; set; }          // point on FromFloor
        public Point3d     ExitPt    { get; set; }          // point on ToFloor
    }

    public static class StaircaseGeometryGenerator
    {
        public static StaircaseGeometry Generate(
            StaircaseDefinition stair,
            Point3d origin,          // SW corner of stairwell box
            double floorHeight,
            int floorCount)
        {
            return stair.Type switch
            {
                StaircaseType.Straight => GenStraight(stair, origin, floorHeight, floorCount),
                StaircaseType.LShape   => GenLShape(stair, origin, floorHeight, floorCount),
                StaircaseType.UShape   => GenUShape(stair, origin, floorHeight, floorCount),
                StaircaseType.Spiral   => GenSpiral(stair, origin, floorHeight, floorCount),
                _                      => GenStraight(stair, origin, floorHeight, floorCount)
            };
        }

        // ── Straight / einläufig ───────────────────────────────────────────────

        private static StaircaseGeometry GenStraight(
            StaircaseDefinition s, Point3d org, double fh, int floors)
        {
            var geo  = new StaircaseGeometry();
            int nSteps = (int)Math.Ceiling(fh / s.RiserHeight);

            for (int fl = s.FromFloor; fl < s.ToFloor; fl++)
            {
                double z0 = fl * fh;

                // Stairwell box
                var plane = new Plane(new Point3d(org.X, org.Y, z0), Vector3d.XAxis, Vector3d.YAxis);
                var box   = new Box(plane,
                    new Interval(0, s.Width),
                    new Interval(0, nSteps * s.TreadDepth),
                    new Interval(0, fh));
                var brep = Brep.CreateFromBox(box);
                if (brep != null) geo.Volumes.Add(brep);

                // Individual treads
                for (int i = 0; i < nSteps; i++)
                {
                    double y   = org.Y + i * s.TreadDepth;
                    double ztop = z0 + (i + 1) * s.RiserHeight;
                    var tp = new Plane(new Point3d(org.X, y, ztop), Vector3d.XAxis, Vector3d.YAxis);
                    var tb = new Box(tp,
                        new Interval(0, s.Width),
                        new Interval(0, s.TreadDepth),
                        new Interval(-0.04, 0));
                    var tbrep = Brep.CreateFromBox(tb);
                    if (tbrep != null) geo.Treads.Add(tbrep);
                }

                // Handrail – diagonal line along run
                var rail = new LineCurve(
                    new Point3d(org.X + s.Width + 0.05, org.Y, z0 + 1.0),
                    new Point3d(org.X + s.Width + 0.05, org.Y + nSteps * s.TreadDepth, z0 + fh + 1.0));
                geo.Handrails.Add(rail);
            }

            double runLen = nSteps * s.TreadDepth;
            geo.EntryPt = new Point3d(org.X + s.Width * 0.5, org.Y + s.TreadDepth, s.FromFloor * fh);
            geo.ExitPt  = new Point3d(org.X + s.Width * 0.5, org.Y + runLen, s.ToFloor * fh);
            return geo;
        }

        // ── L-Shape / einläufig L-förmig ──────────────────────────────────────

        private static StaircaseGeometry GenLShape(
            StaircaseDefinition s, Point3d org, double fh, int floors)
        {
            var geo    = new StaircaseGeometry();
            int nSteps = (int)Math.Ceiling(fh / s.RiserHeight);
            int half1  = nSteps / 2;
            int half2  = nSteps - half1;

            for (int fl = s.FromFloor; fl < s.ToFloor; fl++)
            {
                double z0 = fl * fh;

                // First flight (Y-direction)
                double run1 = half1 * s.TreadDepth;
                var p1 = new Plane(new Point3d(org.X, org.Y, z0), Vector3d.XAxis, Vector3d.YAxis);
                var b1 = new Box(p1, new Interval(0, s.Width), new Interval(0, run1), new Interval(0, half1 * s.RiserHeight));
                var br1 = Brep.CreateFromBox(b1);
                if (br1 != null) geo.Volumes.Add(br1);

                // Landing
                double zLand = z0 + half1 * s.RiserHeight;
                double run2  = half2 * s.TreadDepth;

                // Second flight (X-direction, 90° turn)
                var p2 = new Plane(new Point3d(org.X, org.Y + run1, zLand), Vector3d.XAxis, Vector3d.YAxis);
                var b2 = new Box(p2, new Interval(0, run2), new Interval(0, s.Width), new Interval(0, half2 * s.RiserHeight));
                var br2 = Brep.CreateFromBox(b2);
                if (br2 != null) geo.Volumes.Add(br2);

                // Treads – first flight
                for (int i = 0; i < half1; i++)
                {
                    var tp = new Plane(new Point3d(org.X, org.Y + i * s.TreadDepth, z0 + (i + 1) * s.RiserHeight), Vector3d.XAxis, Vector3d.YAxis);
                    var tb = new Box(tp, new Interval(0, s.Width), new Interval(0, s.TreadDepth), new Interval(-0.04, 0));
                    var trep = Brep.CreateFromBox(tb);
                    if (trep != null) geo.Treads.Add(trep);
                }
                // Treads – second flight (rotated 90°)
                for (int i = 0; i < half2; i++)
                {
                    var tp = new Plane(new Point3d(org.X + (i + 1) * s.TreadDepth, org.Y + run1, zLand + (i + 1) * s.RiserHeight), Vector3d.XAxis, Vector3d.YAxis);
                    var tb = new Box(tp, new Interval(-s.TreadDepth, 0), new Interval(0, s.Width), new Interval(-0.04, 0));
                    var trep = Brep.CreateFromBox(tb);
                    if (trep != null) geo.Treads.Add(trep);
                }
            }

            geo.EntryPt = new Point3d(org.X + s.Width * 0.5, org.Y + s.TreadDepth, s.FromFloor * fh);
            geo.ExitPt  = new Point3d(org.X + (half2 * s.TreadDepth), org.Y + (half1 * s.TreadDepth) + s.Width * 0.5, s.ToFloor * fh);
            return geo;
        }

        // ── U-Shape / zweiläufig ───────────────────────────────────────────────

        private static StaircaseGeometry GenUShape(
            StaircaseDefinition s, Point3d org, double fh, int floors)
        {
            var geo    = new StaircaseGeometry();
            int nSteps = (int)Math.Ceiling(fh / s.RiserHeight);
            int half   = nSteps / 2;

            for (int fl = s.FromFloor; fl < s.ToFloor; fl++)
            {
                double z0     = fl * fh;
                double run    = half * s.TreadDepth;
                double zMid   = z0 + half * s.RiserHeight;

                // First flight going up (Y-direction, left side)
                var p1  = new Plane(new Point3d(org.X, org.Y, z0), Vector3d.XAxis, Vector3d.YAxis);
                var b1  = new Box(p1, new Interval(0, s.Width), new Interval(0, run), new Interval(0, half * s.RiserHeight));
                var br1 = Brep.CreateFromBox(b1);
                if (br1 != null) geo.Volumes.Add(br1);

                // Landing
                var lp  = new Plane(new Point3d(org.X, org.Y + run, zMid), Vector3d.XAxis, Vector3d.YAxis);
                var lb  = new Box(lp, new Interval(0, s.Width * 2 + 0.4), new Interval(0, s.Width), new Interval(0, 0.18));
                var lbr = Brep.CreateFromBox(lb);
                if (lbr != null) geo.Volumes.Add(lbr);

                // Second flight going up (Y-direction reversed, right side)
                double xOff = s.Width + 0.4;
                var p2  = new Plane(new Point3d(org.X + xOff, org.Y + run, zMid), Vector3d.XAxis, Vector3d.YAxis);
                var b2  = new Box(p2, new Interval(0, s.Width), new Interval(0, -run), new Interval(0, half * s.RiserHeight));
                var br2 = Brep.CreateFromBox(b2);
                if (br2 != null) geo.Volumes.Add(br2);

                // Handrails
                geo.Handrails.Add(new LineCurve(
                    new Point3d(org.X - 0.05, org.Y, z0 + 1.0),
                    new Point3d(org.X - 0.05, org.Y + run, zMid + 1.0)));
                geo.Handrails.Add(new LineCurve(
                    new Point3d(org.X + xOff + s.Width + 0.05, org.Y + run, zMid + 1.0),
                    new Point3d(org.X + xOff + s.Width + 0.05, org.Y, fh * s.ToFloor + 1.0)));
            }

            geo.EntryPt = new Point3d(org.X + s.Width * 0.5, org.Y + s.TreadDepth, s.FromFloor * fh);
            geo.ExitPt  = new Point3d(org.X + s.Width * 1.5 + 0.4, org.Y + s.TreadDepth, s.ToFloor * fh);
            return geo;
        }

        // ── Spiral / Wendeltreppe ──────────────────────────────────────────────

        private static StaircaseGeometry GenSpiral(
            StaircaseDefinition s, Point3d org, double fh, int floors)
        {
            var geo    = new StaircaseGeometry();
            double r   = s.Width;
            double cx  = org.X + r;
            double cy  = org.Y + r;
            int nSteps = (int)Math.Ceiling(fh / s.RiserHeight);
            double angStep = (2 * Math.PI) / nSteps;

            for (int fl = s.FromFloor; fl < s.ToFloor; fl++)
            {
                double z0 = fl * fh;

                // Central cylinder
                var circle = new Circle(new Plane(new Point3d(cx, cy, z0), Vector3d.ZAxis), r);
                var cyl    = Brep.CreateFromCylinder(
                    new Cylinder(circle, fh), true, true);
                if (cyl != null) geo.Volumes.Add(cyl);

                // Tread wedges
                for (int i = 0; i < nSteps; i++)
                {
                    double a0  = i * angStep;
                    double a1  = a0 + angStep;
                    double zt  = z0 + (i + 1) * s.RiserHeight;
                    double rInner = 0.15;  // central pole radius

                    var pts = new Point3d[]
                    {
                        new(cx + rInner * Math.Cos(a0), cy + rInner * Math.Sin(a0), zt),
                        new(cx + r      * Math.Cos(a0), cy + r      * Math.Sin(a0), zt),
                        new(cx + r      * Math.Cos(a1), cy + r      * Math.Sin(a1), zt),
                        new(cx + rInner * Math.Cos(a1), cy + rInner * Math.Sin(a1), zt)
                    };
                    var tread = Brep.CreateFromCornerPoints(pts[0], pts[1], pts[2], pts[3], 1e-6);
                    if (tread != null) geo.Treads.Add(tread);
                }

                // Handrail helix (approximated by polyline)
                var railPts = new List<Point3d>();
                for (int i = 0; i <= nSteps; i++)
                {
                    double a = i * angStep;
                    double z = z0 + i * s.RiserHeight + 1.0;
                    railPts.Add(new Point3d(cx + (r - 0.05) * Math.Cos(a), cy + (r - 0.05) * Math.Sin(a), z));
                }
                geo.Handrails.Add(new PolylineCurve(railPts));
            }

            geo.EntryPt = new Point3d(cx + r, cy, s.FromFloor * fh);
            geo.ExitPt  = new Point3d(cx + r * Math.Cos(2 * Math.PI * (s.ToFloor - s.FromFloor)),
                                       cy + r * Math.Sin(2 * Math.PI * (s.ToFloor - s.FromFloor)),
                                       s.ToFloor * fh);
            return geo;
        }
    }
}
