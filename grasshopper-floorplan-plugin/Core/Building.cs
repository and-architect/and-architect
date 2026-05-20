using System;
using System.Collections.Generic;
using Rhino.Geometry;

namespace AndArchitectGH.Core
{
    /// <summary>
    /// Building envelope – defines the outer shell that all rooms must fit inside.
    /// </summary>
    public class Building
    {
        // Footprint polygon in XY plane (closed, counter-clockwise)
        public Polyline Footprint { get; set; }

        public int NumberOfFloors { get; set; } = 2;
        public double FloorHeight { get; set; } = 3.0;   // m
        public double TotalHeight => NumberOfFloors * FloorHeight;

        // Pre-computed bounding box of the footprint
        private BoundingBox _bbox;

        // ── Constructors ──────────────────────────────────────────────────────

        public Building(double width, double depth, int floors = 2, double floorHeight = 3.0)
        {
            Footprint = RectangleFootprint(Point3d.Origin, width, depth);
            NumberOfFloors = floors;
            FloorHeight = floorHeight;
            _bbox = Footprint.BoundingBox;
        }

        public Building(Polyline footprint, int floors = 2, double floorHeight = 3.0)
        {
            Footprint = footprint;
            NumberOfFloors = floors;
            FloorHeight = floorHeight;
            _bbox = footprint.BoundingBox;
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        public BoundingBox GetBoundingBox() => _bbox;

        public double FootprintWidth  => _bbox.Max.X - _bbox.Min.X;
        public double FootprintDepth  => _bbox.Max.Y - _bbox.Min.Y;
        public double FootprintArea   => FootprintWidth * FootprintDepth;

        public Point3d Center => new Point3d(
            (_bbox.Min.X + _bbox.Max.X) * 0.5,
            (_bbox.Min.Y + _bbox.Max.Y) * 0.5,
            0);

        /// <summary>Z-elevation of the bottom of a given floor level.</summary>
        public double FloorElevation(int floor) => floor * FloorHeight;

        /// <summary>Returns the extruded Brep of the full envelope.</summary>
        public Brep GetEnvelopeBrep()
        {
            var curve = Footprint.ToNurbsCurve();
            var extrusion = Extrusion.Create(curve, TotalHeight, true);
            return extrusion?.ToBrep(true) ?? Brep.CreateFromBox(_bbox);
        }

        // ── Statics ───────────────────────────────────────────────────────────

        public static Polyline RectangleFootprint(Point3d origin, double w, double d)
        {
            var pts = new Point3d[]
            {
                origin,
                origin + new Vector3d(w, 0, 0),
                origin + new Vector3d(w, d, 0),
                origin + new Vector3d(0, d, 0),
                origin   // close
            };
            return new Polyline(pts);
        }

        public override string ToString() =>
            $"Building {FootprintWidth:F1}×{FootprintDepth:F1} m  " +
            $"{NumberOfFloors} floors  h={TotalHeight:F1} m";
    }
}
