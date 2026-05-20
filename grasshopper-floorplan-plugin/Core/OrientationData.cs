using System;
using System.Collections.Generic;
using Rhino.Geometry;

namespace AndArchitectGH.Core
{
    /// <summary>
    /// Captures site orientation: north direction, sun vectors per compass point,
    /// and external view targets that rooms should face.
    /// </summary>
    public class OrientationData
    {
        // World-space vector pointing north (XY plane)
        public Vector3d North { get; set; } = Vector3d.YAxis;

        // Important view points in world space (mountains, water, street, …)
        public List<Point3d> ViewPoints { get; set; } = new();

        // Latitude in degrees (for sun-angle calculation)
        public double Latitude { get; set; } = 48.0;

        // ── Derived compass vectors ────────────────────────────────────────────

        public Vector3d South => -North;
        public Vector3d East  { get; private set; }
        public Vector3d West  { get; private set; }

        public OrientationData()  => Recompute();
        public OrientationData(Vector3d north, double latitude = 48.0)
        {
            North = north;
            Latitude = latitude;
            Recompute();
        }

        private void Recompute()
        {
            // Cross product of North with world Z gives East in a right-handed system
            East = Vector3d.CrossProduct(Vector3d.ZAxis, North);
            East.Unitize();
            West = -East;
        }

        // ── Solar preference → compass vector ─────────────────────────────────

        public Vector3d GetSolarVector(SolarPreference pref) => pref switch
        {
            SolarPreference.South => South,
            SolarPreference.East  => East,
            SolarPreference.West  => West,
            SolarPreference.North => North,
            _                     => Vector3d.Zero
        };

        /// <summary>
        /// Returns the average direction toward all registered view points
        /// from a given position.
        /// </summary>
        public Vector3d AverageViewDirection(Point3d from)
        {
            if (ViewPoints.Count == 0) return Vector3d.Zero;
            var sum = Vector3d.Zero;
            foreach (var vp in ViewPoints)
            {
                var v = vp - from;
                v.Unitize();
                sum += v;
            }
            sum /= ViewPoints.Count;
            sum.Unitize();
            return sum;
        }

        /// <summary>
        /// Simple solar altitude for the given latitude at solar noon on the
        /// winter solstice – used to judge how deep winter sun penetrates a room.
        /// </summary>
        public double WinterSolsticeAltitudeDeg()
        {
            double latRad = Latitude * Math.PI / 180.0;
            double declination = -23.45 * Math.PI / 180.0;
            double altitude = Math.Asin(
                Math.Sin(latRad) * Math.Sin(declination) +
                Math.Cos(latRad) * Math.Cos(declination)) * 180.0 / Math.PI;
            return altitude;
        }

        public override string ToString() =>
            $"North={North}  Lat={Latitude:F1}°  ViewPts={ViewPoints.Count}";
    }
}
