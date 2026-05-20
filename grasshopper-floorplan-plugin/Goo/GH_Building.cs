using AndArchitectGH.Core;
using Grasshopper.Kernel.Types;

namespace AndArchitectGH.Goo
{
    public class GH_Building : GH_Goo<Building>
    {
        public GH_Building() : base(new Building(10, 12)) { }
        public GH_Building(Building b) : base(b) { }

        public override bool IsValid => Value != null;
        public override string TypeName        => "Building";
        public override string TypeDescription => "Building envelope for the floor-plan generator";

        public override IGH_Goo Duplicate() => new GH_Building(Value);
        public override string  ToString()  => Value?.ToString() ?? "null building";

        public override bool CastFrom(object source)
        {
            if (source is Building b)     { Value = b; return true; }
            if (source is GH_Building gh) { Value = gh.Value; return true; }
            return false;
        }

        public override bool CastTo<T>(ref T target)
        {
            if (typeof(T) == typeof(Building)) { target = (T)(object)Value; return true; }
            return false;
        }
    }
}
