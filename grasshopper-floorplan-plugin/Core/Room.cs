using System;
using System.Collections.Generic;
using Rhino.Geometry;

namespace AndArchitectGH.Core
{
    // ─── Enumerations ──────────────────────────────────────────────────────────

    public enum RoomType
    {
        LivingRoom, Kitchen, DiningRoom,
        MasterBedroom, Bedroom, ChildRoom,
        Bathroom, WC,
        Office, Library,
        Hallway, Staircase, Storage,
        Garage, Balcony, Terrace,
        Custom
    }

    public enum SolarPreference
    {
        South,   // max winter sun – living areas
        East,    // morning sun – bedrooms
        West,    // afternoon sun – dining / terrace
        North,   // diffuse / shaded – bathrooms, offices
        Any      // no preference
    }

    // ─── Room ─────────────────────────────────────────────────────────────────

    public class Room
    {
        public string Name { get; set; } = "Room";
        public double Area { get; set; } = 20.0;      // m²
        public int Floor { get; set; } = 0;            // 0 = ground floor
        public RoomType Type { get; set; } = RoomType.Custom;
        public SolarPreference SolarPref { get; set; } = SolarPreference.Any;

        // Names of rooms that must be placed adjacent / nearby
        public List<string> MustBeNear { get; set; } = new();

        // Names of rooms that should NOT be directly next to this one
        public List<string> MustBeAway { get; set; } = new();

        // Preferred façade direction (world-space, XY plane)
        // Zero vector means no preference
        public Vector3d PreferredViewDirection { get; set; } = Vector3d.Zero;

        // 0 = lowest, 1 = highest – affects solver priority
        public double Priority { get; set; } = 0.5;

        // Minimum ceiling height (m) – overrides building default if > 0
        public double MinCeilingHeight { get; set; } = 0.0;

        // ── Solved placement (filled by FloorplanSolver) ──────────────────────
        public Box PlacedBox { get; set; } = Box.Unset;
        public bool IsPlaced { get; set; } = false;

        // Cached/explicit dimensions
        public double Width  { get; private set; }
        public double Depth  { get; private set; }
        public bool ExplicitDimensions { get; private set; }

        // ── Helpers ───────────────────────────────────────────────────────────

        /// <summary>Store user-provided width × depth; skips auto-estimation in solver.</summary>
        public void SetExplicitDimensions(double w, double d)
        {
            Width = w;
            Depth = d;
            ExplicitDimensions = true;
        }

        /// <summary>Estimate width/depth from area using a golden-ratio aspect (only if not explicit).</summary>
        public void EstimateDimensions(double aspectRatio = 1.4)
        {
            if (ExplicitDimensions) return;
            Width = Math.Sqrt(Area / aspectRatio);
            Depth = Area / Width;
        }

        /// <summary>Return a shallow copy with placement state cleared.</summary>
        public Room Clone()
        {
            return new Room
            {
                Name = Name,
                Area = Area,
                Floor = Floor,
                Type = Type,
                SolarPref = SolarPref,
                MustBeNear = new List<string>(MustBeNear),
                MustBeAway = new List<string>(MustBeAway),
                PreferredViewDirection = PreferredViewDirection,
                Priority = Priority,
                MinCeilingHeight = MinCeilingHeight
            }.WithDimensions(Width, Depth, ExplicitDimensions);
        }

        private Room WithDimensions(double w, double d, bool explicit_)
        {
            Width = w; Depth = d; ExplicitDimensions = explicit_;
            return this;
        }

        public override string ToString() =>
            $"{Name} ({Area:F1} m²  F{Floor}  {Type}  {SolarPref})";

        // ── Static defaults per room type ─────────────────────────────────────

        public static SolarPreference DefaultSolar(RoomType t) => t switch
        {
            RoomType.LivingRoom  => SolarPreference.South,
            RoomType.DiningRoom  => SolarPreference.South,
            RoomType.Kitchen     => SolarPreference.East,
            RoomType.MasterBedroom => SolarPreference.East,
            RoomType.Bedroom     => SolarPreference.East,
            RoomType.ChildRoom   => SolarPreference.South,
            RoomType.Bathroom    => SolarPreference.North,
            RoomType.WC          => SolarPreference.North,
            RoomType.Office      => SolarPreference.North,
            RoomType.Library     => SolarPreference.North,
            RoomType.Garage      => SolarPreference.North,
            _                    => SolarPreference.Any
        };

        public static double DefaultPriority(RoomType t) => t switch
        {
            RoomType.LivingRoom    => 0.95,
            RoomType.Kitchen       => 0.85,
            RoomType.MasterBedroom => 0.90,
            RoomType.DiningRoom    => 0.75,
            RoomType.Bedroom       => 0.70,
            RoomType.ChildRoom     => 0.70,
            RoomType.Bathroom      => 0.60,
            RoomType.Office        => 0.65,
            RoomType.Hallway       => 0.80, // must be central
            _                      => 0.50
        };

        public static double DefaultMinArea(RoomType t) => t switch
        {
            RoomType.WC       => 3,
            RoomType.Bathroom => 5,
            RoomType.Hallway  => 6,
            RoomType.Kitchen  => 10,
            RoomType.Bedroom  => 12,
            RoomType.LivingRoom => 20,
            RoomType.MasterBedroom => 18,
            _ => 0
        };
    }
}
