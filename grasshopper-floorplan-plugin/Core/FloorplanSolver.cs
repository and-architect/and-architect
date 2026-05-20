using System;
using System.Collections.Generic;
using System.Linq;
using Rhino.Geometry;

namespace AndArchitectGH.Core
{
    // ─── Result types ──────────────────────────────────────────────────────────

    public class PlacedRoom
    {
        public Room Source { get; set; } = null!;
        public Box Box { get; set; }
        public double PlacementScore { get; set; }

        public Point3d Center => Box.Center;
        public string Name => Source.Name;
    }

    public class FloorplanVariant
    {
        public int Seed { get; set; }
        public List<PlacedRoom> Rooms { get; set; } = new();
        public double Score { get; set; }
        public string Label { get; set; } = "";

        public List<Box> AllBoxes() => Rooms.Select(r => r.Box).ToList();

        public List<Brep> AllBreps()
        {
            var breps = new List<Brep>();
            foreach (var pr in Rooms)
            {
                var b = Brep.CreateFromBox(pr.Box);
                if (b != null) breps.Add(b);
            }
            return breps;
        }

        public string Summary()
        {
            var lines = new System.Text.StringBuilder();
            lines.AppendLine($"Variant {Seed}  Score={Score:F3}");
            foreach (var r in Rooms.OrderBy(r => r.Source.Floor).ThenBy(r => r.Name))
                lines.AppendLine($"  F{r.Source.Floor}  {r.Name,-20}  {r.Source.Area:F1} m²  " +
                                 $"pos=({r.Box.Plane.Origin.X:F1},{r.Box.Plane.Origin.Y:F1},{r.Box.Plane.Origin.Z:F1})  " +
                                 $"score={r.PlacementScore:F2}");
            return lines.ToString();
        }
    }

    // ─── Grid-based room packer ────────────────────────────────────────────────

    internal class FloorGrid
    {
        private readonly bool[,] _occupied;
        private readonly double _step;
        private readonly double _ox, _oy;
        private readonly int _gw, _gh;

        public FloorGrid(double width, double depth, Point3d origin, double step = 1.0)
        {
            _step = step;
            _ox = origin.X;
            _oy = origin.Y;
            _gw = (int)Math.Ceiling(width / step);
            _gh = (int)Math.Ceiling(depth / step);
            _occupied = new bool[_gw, _gh];
        }

        private int ToGX(double x) => (int)Math.Round((x - _ox) / _step);
        private int ToGY(double y) => (int)Math.Round((y - _oy) / _step);

        public bool CanPlace(double x, double y, double w, double h)
        {
            int gx = ToGX(x);
            int gy = ToGY(y);
            int gw = (int)Math.Ceiling(w / _step);
            int gh = (int)Math.Ceiling(h / _step);

            if (gx < 0 || gy < 0 || gx + gw > _gw || gy + gh > _gh) return false;

            for (int i = gx; i < gx + gw; i++)
                for (int j = gy; j < gy + gh; j++)
                    if (_occupied[i, j]) return false;

            return true;
        }

        public void Occupy(double x, double y, double w, double h)
        {
            int gx = ToGX(x);
            int gy = ToGY(y);
            int gw = (int)Math.Ceiling(w / _step);
            int gh = (int)Math.Ceiling(h / _step);

            for (int i = Math.Max(0, gx); i < Math.Min(gx + gw, _gw); i++)
                for (int j = Math.Max(0, gy); j < Math.Min(gy + gh, _gh); j++)
                    _occupied[i, j] = true;
        }

        // World-space coordinates of grid cell centres
        public IEnumerable<(double x, double y)> FreePositions()
        {
            for (int i = 0; i < _gw; i++)
                for (int j = 0; j < _gh; j++)
                    if (!_occupied[i, j])
                        yield return (_ox + i * _step, _oy + j * _step);
        }
    }

    // ─── Main solver ──────────────────────────────────────────────────────────

    public class FloorplanSolver
    {
        private readonly List<Room> _rooms;
        private readonly Building _building;
        private readonly OrientationData _orientation;

        // Scoring weights
        private const double W_Solar     = 0.35;
        private const double W_View      = 0.25;
        private const double W_Adjacency = 0.20;
        private const double W_Position  = 0.20;

        // Grid step (metres)
        private const double GridStep = 1.0;

        public FloorplanSolver(List<Room> rooms, Building building, OrientationData orientation)
        {
            _rooms = rooms;
            _building = building;
            _orientation = orientation;
        }

        // ── Public API ─────────────────────────────────────────────────────────

        public List<FloorplanVariant> GenerateVariants(int count = 3)
        {
            var variants = new List<FloorplanVariant>();
            for (int seed = 0; seed < count; seed++)
            {
                var v = SolveOnce(seed);
                v.Label = LabelFor(seed);
                variants.Add(v);
            }
            return variants.OrderByDescending(v => v.Score).ToList();
        }

        // ── Core solver ────────────────────────────────────────────────────────

        private FloorplanVariant SolveOnce(int seed)
        {
            var rng = new Random(seed * 137 + 7);
            var variant = new FloorplanVariant { Seed = seed };

            // Collect all already-placed rooms so adjacency scoring works across floors
            var allPlaced = new List<PlacedRoom>();

            var byFloor = _rooms
                .GroupBy(r => r.Floor)
                .OrderBy(g => g.Key);

            foreach (var floorGroup in byFloor)
            {
                int floor = floorGroup.Key;
                double z   = _building.FloorElevation(floor);
                double h   = _building.FloorHeight;
                var bb     = _building.GetBoundingBox();

                var grid = new FloorGrid(
                    _building.FootprintWidth,
                    _building.FootprintDepth,
                    new Point3d(bb.Min.X, bb.Min.Y, 0),
                    GridStep);

                // Order: by priority, perturbed slightly by seed so variants differ
                var orderedRooms = floorGroup
                    .OrderByDescending(r => r.Priority + rng.NextDouble() * 0.05 * seed)
                    .ToList();

                foreach (var room in orderedRooms)
                {
                    room.EstimateDimensions(AspectFor(room, seed));

                    var placed = TryPlace(room, floor, z, h, grid, allPlaced, bb, rng);
                    if (placed != null)
                    {
                        variant.Rooms.Add(placed);
                        allPlaced.Add(placed);
                        grid.Occupy(
                            placed.Box.Plane.Origin.X,
                            placed.Box.Plane.Origin.Y,
                            placed.Box.X.Length,
                            placed.Box.Y.Length);
                    }
                }
            }

            variant.Score = variant.Rooms.Count > 0
                ? variant.Rooms.Average(r => r.PlacementScore)
                : 0;

            return variant;
        }

        private PlacedRoom? TryPlace(
            Room room, int floor, double z, double h,
            FloorGrid grid, List<PlacedRoom> allPlaced,
            BoundingBox bb, Random rng)
        {
            double bestScore = double.NegativeInfinity;
            (double x, double y, double w, double d)? best = null;

            double[] widths = { room.Width, room.Depth };   // try both orientations
            double[] depths = { room.Depth, room.Width };

            // Step through the grid; candidate positions every GridStep metres
            for (double px = bb.Min.X; px <= bb.Max.X; px += GridStep)
            {
                for (double py = bb.Min.Y; py <= bb.Max.Y; py += GridStep)
                {
                    for (int ori = 0; ori < 2; ori++)
                    {
                        double w = widths[ori];
                        double d = depths[ori];

                        if (!grid.CanPlace(px, py, w, d)) continue;

                        double score = Score(room, px, py, w, d, z, allPlaced, bb);
                        if (score > bestScore)
                        {
                            bestScore = score;
                            best = (px, py, w, d);
                        }
                    }
                }
            }

            if (best == null) return null;

            var (bx, by, bw, bd) = best.Value;
            var origin = new Point3d(bx, by, z);
            var plane  = new Plane(origin, Vector3d.XAxis, Vector3d.YAxis);
            var box    = new Box(plane,
                new Interval(0, bw),
                new Interval(0, bd),
                new Interval(0, h));

            return new PlacedRoom
            {
                Source         = room.Clone(),
                Box            = box,
                PlacementScore = bestScore
            };
        }

        // ── Scoring ────────────────────────────────────────────────────────────

        private double Score(
            Room room,
            double px, double py, double w, double d, double z,
            List<PlacedRoom> allPlaced, BoundingBox bb)
        {
            var center = new Point3d(px + w * 0.5, py + d * 0.5, z);

            double solar     = ScoreSolar(room, center, bb);
            double view      = ScoreView(room, center);
            double adjacency = ScoreAdjacency(room, center, allPlaced);
            double position  = ScorePosition(room, center, bb);

            return W_Solar * solar + W_View * view + W_Adjacency * adjacency + W_Position * position;
        }

        private double ScoreSolar(Room room, Point3d center, BoundingBox bb)
        {
            if (room.SolarPref == SolarPreference.Any) return 0.5;

            var buildingCenter = new Point3d(
                (bb.Min.X + bb.Max.X) * 0.5,
                (bb.Min.Y + bb.Max.Y) * 0.5,
                center.Z);

            var dir = center - buildingCenter;
            if (dir.IsTiny()) return 0.5;
            dir.Unitize();

            var solarVec = _orientation.GetSolarVector(room.SolarPref);
            return Clamp01((1.0 + Vector3d.Multiply(dir, solarVec)) * 0.5);
        }

        private double ScoreView(Room room, Point3d center)
        {
            if (_orientation.ViewPoints.Count == 0) return 0.5;
            if (room.PreferredViewDirection == Vector3d.Zero) return 0.5;

            double max = 0;
            foreach (var vp in _orientation.ViewPoints)
            {
                var toVp = vp - center;
                if (toVp.IsTiny()) continue;
                toVp.Unitize();
                double dot = Vector3d.Multiply(toVp, room.PreferredViewDirection);
                max = Math.Max(max, (1.0 + dot) * 0.5);
            }
            return Clamp01(max);
        }

        private double ScoreAdjacency(Room room, Point3d center, List<PlacedRoom> allPlaced)
        {
            if (room.MustBeNear.Count == 0 && room.MustBeAway.Count == 0) return 0.5;

            double score = 0.5;
            double normDist = Math.Max(_building.FootprintWidth, _building.FootprintDepth);

            foreach (var near in room.MustBeNear)
            {
                var target = allPlaced.FirstOrDefault(r =>
                    string.Equals(r.Name, near, StringComparison.OrdinalIgnoreCase));
                if (target == null) continue;
                double d = center.DistanceTo(target.Center);
                score += 0.5 * (1.0 - Clamp01(d / normDist));  // closer = better
            }

            foreach (var away in room.MustBeAway)
            {
                var target = allPlaced.FirstOrDefault(r =>
                    string.Equals(r.Name, away, StringComparison.OrdinalIgnoreCase));
                if (target == null) continue;
                double d = center.DistanceTo(target.Center);
                score += 0.5 * Clamp01(d / normDist);            // farther = better
            }

            int totalConstraints = room.MustBeNear.Count + room.MustBeAway.Count;
            return Clamp01(score / (totalConstraints + 1));
        }

        private double ScorePosition(Room room, Point3d center, BoundingBox bb)
        {
            // Normalised position within footprint [0,1]
            double relX = (center.X - bb.Min.X) / (bb.Max.X - bb.Min.X + 1e-6);
            double relY = (center.Y - bb.Min.Y) / (bb.Max.Y - bb.Min.Y + 1e-6);

            // In Central European convention: south = lower Y, north = higher Y
            return room.SolarPref switch
            {
                SolarPreference.South => 1.0 - relY,
                SolarPreference.North => relY,
                SolarPreference.East  => relX,
                SolarPreference.West  => 1.0 - relX,
                _                     => 0.5
            };
        }

        // ── Helpers ────────────────────────────────────────────────────────────

        private static double Clamp01(double v) => Math.Max(0.0, Math.Min(1.0, v));

        // Vary aspect ratio slightly per variant seed so geometry differs visually
        private static double AspectFor(Room room, int seed)
        {
            double[] ratios = { 1.4, 1.0, 1.7 };
            return ratios[seed % ratios.Length];
        }

        private static string LabelFor(int seed) => seed switch
        {
            0 => "Optimal",
            1 => "Square",
            2 => "Wide",
            _ => $"Variant {seed}"
        };
    }
}
