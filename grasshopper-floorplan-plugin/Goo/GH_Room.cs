using System;
using AndArchitectGH.Core;
using Grasshopper.Kernel.Types;

namespace AndArchitectGH.Goo
{
    /// <summary>
    /// GH_Goo wrapper for <see cref="Room"/> so rooms can flow through wires.
    /// </summary>
    public class GH_Room : GH_Goo<Room>
    {
        public GH_Room() : base(new Room()) { }
        public GH_Room(Room room) : base(room) { }

        public override bool IsValid =>
            Value != null && !string.IsNullOrWhiteSpace(Value.Name) && Value.Area > 0;

        public override string IsValidWhyNot =>
            Value == null ? "Null room" :
            string.IsNullOrWhiteSpace(Value.Name) ? "Room has no name" :
            Value.Area <= 0 ? "Room area must be > 0" : "Valid";

        public override string TypeName        => "Room";
        public override string TypeDescription => "An architectural room definition";

        public override IGH_Goo Duplicate() => new GH_Room(Value.Clone());
        public override string  ToString()  => Value?.ToString() ?? "null room";

        public override bool CastFrom(object source)
        {
            if (source is Room r)        { Value = r; return true; }
            if (source is GH_Room gh)    { Value = gh.Value; return true; }
            if (source is string s)
            {
                // Minimal string cast: treat string as room name with default area
                Value = new Room { Name = s, Area = 20 };
                return true;
            }
            return false;
        }

        public override bool CastTo<T>(ref T target)
        {
            if (typeof(T) == typeof(Room))
            {
                target = (T)(object)Value;
                return true;
            }
            return false;
        }
    }
}
