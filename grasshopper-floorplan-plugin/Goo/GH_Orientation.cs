using AndArchitectGH.Core;
using Grasshopper.Kernel.Types;

namespace AndArchitectGH.Goo
{
    public class GH_Orientation : GH_Goo<OrientationData>
    {
        public GH_Orientation() : base(new OrientationData()) { }
        public GH_Orientation(OrientationData o) : base(o) { }

        public override bool IsValid => Value != null;
        public override string TypeName        => "Orientation";
        public override string TypeDescription => "Site orientation (north direction, view points, latitude)";

        public override IGH_Goo Duplicate() => new GH_Orientation(Value);
        public override string  ToString()  => Value?.ToString() ?? "null orientation";

        public override bool CastFrom(object source)
        {
            if (source is OrientationData o)   { Value = o; return true; }
            if (source is GH_Orientation gh)   { Value = gh.Value; return true; }
            return false;
        }

        public override bool CastTo<T>(ref T target)
        {
            if (typeof(T) == typeof(OrientationData)) { target = (T)(object)Value; return true; }
            return false;
        }
    }
}
