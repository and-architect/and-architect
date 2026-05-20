using System;
using System.Collections.Generic;
using Rhino.Geometry;

namespace AndArchitectGH.Core
{
    /// <summary>
    /// Building envelope – defines the outer shell that all rooms must fit inside.
    /// Supports above-ground floors (NumberOfFloors) and below-ground basement
    /// levels (NumberOfBasements). Floor -1 = first basement, -2 = second, etc.
    /// </summary>
    public class Building
    {
        // Footprint polygon in XY plane (closed, counter-clockwise)
        public Polyline Footprint { get; set; }

        public int    NumberOfFloors    { get; set; } = 2;      // above ground (≥1)
        public int    NumberOfBasements { get; set; } = 0;      // below ground (≥0)
        public double FloorHeight       { get; set; } = 3.0;    // m, all floors same
        public double BasementHeight    { get; set; } = 2.5;    // m, basement floor height

        public double TotalAboveGroundHeight => NumberOfFloors    * FloorHeight;
        public double TotalBelowGroundDepth  => NumberOfBasements * BasementHeight;
        public double TotalHeight            => TotalAboveGroundHeight + TotalBelowGroundDepth;

        // Pre-computed bounding box of the footprint
        private BoundingBox _bbox;

        // ── Constructors ──────────────────────────────────────────────────────

        public Building(double width, double depth,
                        int floors = 2, double floorHeight = 3.0,
                        int basements = 0, double basementHeight = 2.5)
        {
            Footprint         = RectangleFootprint(Point3d.Origin, width, depth);
            NumberOfFloors    = floors;
            FloorHeight       = floorHeight;
            NumberOfBasements = basements;
            BasementHeight    = basementHeight;
            _bbox             = Footprint.BoundingBox;
        }

        public Building(Polyline footprint,
                        int floors = 2, double floorHeight = 3.0,
                        int basements = 0, double basementHeight = 2.5)
        {
            Footprint         = footprint;
            NumberOfFloors    = floors;
            FloorHeight       = floorHeight;
            NumberOfBasements = basements;
            BasementHeight    = basementHeight;
            _bbox             = footprint.BoundingBox;
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        public BoundingBox GetBoundingBox() => _bbox;

        public double FootprintWidth => _bbox.Max.X - _bbox.Min.X;
        public double FootprintDepth => _bbox.Max.Y - _bbox.Min.Y;
        public double FootprintArea  => FootprintWidth * FootprintDepth;

        public Point3d Center => new Point3d(
            (_bbox.Min.X + _bbox.Max.X) * 0.5,
            (_bbox.Min.Y + _bbox.Max.Y) * 0.5,
            0);

        /// <summary>
        /// Z-elevation of the bottom of a given floor level.
        ///   floor  >= 0 : above ground  (0 = EG, 1 = OG1, …)
        ///   floor  <  0 : below ground  (-1 = KG1, -2 = KG2, …)
        /// </summary>
        public double FloorElevation(int floor)
        {
            if (floor >= 0) return floor * FloorHeight;
            // floor = -1 → z = -BasementHeight
            // floor = -2 → z = -2 × BasementHeight
            return floor * BasementHeight;
        }

        /// <summary>True if floor is a basement level.</summary>
        public bool IsBasement(int floor) => floor < 0;

        /// <summary>Lowest valid floor index (0 if no basements, else -NumberOfBasements).</summary>
        public int LowestFloor => -NumberOfBasements;

        /// <summary>Highest valid floor index (NumberOfFloors - 1).</summary>
        public int HighestFloor => NumberOfFloors - 1;

        /// <summary>
        /// Returns the extruded Brep of the full envelope including basements.
        /// Origin is at ground level (z=0).
        /// </summary>
        public Brep GetEnvelopeBrep()
        {
            var curve      = Footprint.ToNurbsCurve();
            double zBottom = -TotalBelowGroundDepth;
            double zTop    =  TotalAboveGroundHeight;
            double total   =  zTop - zBottom;

            var plane    = new Plane(new Point3d(_bbox.Min.X, _bbox.Min.Y, zBottom), Vector3d.ZAxis);
            var extrusion = Extrusion.Create(
                curve.DuplicateCurve().ProjectToPlane(Plane.WorldXY) ?? curve,
                total, true);

            if (extrusion != null) return extrusion.ToBrep(true) ??
                Brep.CreateFromBox(new BoundingBox(
                    _bbox.Min.X, _bbox.Min.Y, zBottom,
                    _bbox.Max.X, _bbox.Max.Y, zTop));

            return Brep.CreateFromBox(new BoundingBox(
                _bbox.Min.X, _bbox.Min.Y, zBottom,
                _bbox.Max.X, _bbox.Max.Y, zTop));
        }

        /// <summary>Returns just the above-ground shell.</summary>
        public Brep GetAboveGroundBrep()
        {
            var curve     = Footprint.ToNurbsCurve();
            var extrusion = Extrusion.Create(curve, TotalAboveGroundHeight, true);
            return extrusion?.ToBrep(true) ?? Brep.CreateFromBox(_bbox);
        }

        /// <summary>Returns the basement shell (below ground) if any.</summary>
        public Brep? GetBasementBrep()
        {
            if (NumberOfBasements == 0) return null;
            double depth = TotalBelowGroundDepth;
            var bb = new BoundingBox(
                _bbox.Min.X, _bbox.Min.Y, -depth,
                _bbox.Max.X, _bbox.Max.Y, 0);
            return Brep.CreateFromBox(bb);
        }

        // ── Statics ───────────────────────────────────────────────────────────

        public static Polyline RectangleFootprint(Point3d origin, double w, double d)
        {
            return new Polyline(new Point3d[]
            {
                origin,
                origin + new Vector3d(w, 0, 0),
                origin + new Vector3d(w, d, 0),
                origin + new Vector3d(0, d, 0),
                origin
            });
        }

        public override string ToString()
        {
            var s = $"Building {FootprintWidth:F1}×{FootprintDepth:F1} m  " +
                    $"{NumberOfFloors} Geschosse  h={TotalAboveGroundHeight:F1} m";
            if (NumberOfBasements > 0)
                s += $"  +{NumberOfBasements} KG  t={TotalBelowGroundDepth:F1} m";
            return s;
        }
    }
}
