using Grasshopper;
using Grasshopper.Kernel;
using System;
using System.Drawing;

namespace AndArchitectGH
{
    public class AndArchitectInfo : GH_AssemblyInfo
    {
        public override string Name => "AND Architect";
        public override Bitmap Icon => null!;
        public override string Description =>
            "Generative 3-D floor-plan design with AI assistance.\n" +
            "Define rooms, solar exposure, views and adjacency — " +
            "the solver proposes multiple layout variants and lets you " +
            "refine them via natural-language prompts.";
        public override Guid Id => new Guid("A1B2C3D4-E5F6-7890-ABCD-EF1234567890");
        public override string AuthorName => "AND Architect";
        public override string AuthorContact => "https://github.com/and-architect";
    }
}
