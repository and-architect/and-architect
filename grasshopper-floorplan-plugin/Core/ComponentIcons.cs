using System;
using System.Drawing;
using System.Drawing.Drawing2D;

namespace AndArchitectGH.Core
{
    /// <summary>
    /// Generates 24×24 pixel component icons programmatically using System.Drawing.
    /// Rhino 8 ships a cross-platform System.Drawing implementation so these
    /// work on macOS at runtime even though GDI+ is Windows-only in stock .NET.
    /// All methods are safe – they return null on failure so Grasshopper falls
    /// back to its default icon.
    /// </summary>
    public static class ComponentIcons
    {
        private const int S = 24;

        // ── Per-component icons ────────────────────────────────────────────────

        public static Bitmap? Room      => TryDraw(DrawRoom);
        public static Bitmap? Building  => TryDraw(DrawBuilding);
        public static Bitmap? Orient    => TryDraw(DrawOrient);
        public static Bitmap? Generate  => TryDraw(DrawGenerate);
        public static Bitmap? Shadow    => TryDraw(DrawShadow);
        public static Bitmap? Roof      => TryDraw(DrawRoof);
        public static Bitmap? AIIcon    => TryDraw(DrawAI);
        public static Bitmap? OAuthIcon => TryDraw(DrawOAuth);
        public static Bitmap? Visualize => TryDraw(DrawVisualize);
        public static Bitmap? Staircase => TryDraw(DrawStaircase);
        public static Bitmap? Basement  => TryDraw(DrawBasement);

        // ── Helper ─────────────────────────────────────────────────────────────

        private static Bitmap? TryDraw(Action<Graphics, Bitmap> fn)
        {
            try
            {
                var bmp = new Bitmap(S, S);
                using var g = Graphics.FromImage(bmp);
                g.SmoothingMode    = SmoothingMode.AntiAlias;
                g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
                g.Clear(Color.Transparent);
                fn(g, bmp);
                return bmp;
            }
            catch { return null; }
        }

        // Convenience for filled rounded-rect background
        private static void Background(Graphics g, Color col)
        {
            using var b = new SolidBrush(col);
            g.FillRectangle(b, 1, 1, S - 2, S - 2);
        }

        // ── Draw methods ───────────────────────────────────────────────────────

        // AND_Room  – floor-plan room square with door gap
        private static void DrawRoom(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(200, 215, 245));
            using var pen  = new Pen(Color.FromArgb(40, 80, 160), 1.5f);
            using var door = new Pen(Color.White, 2f);
            // Room outline with gap on south side
            g.DrawLine(pen,  3,  3, 21,  3);  // top
            g.DrawLine(pen,  3,  3,  3, 21);  // left
            g.DrawLine(pen, 21,  3, 21, 21);  // right
            g.DrawLine(pen,  3, 21,  9, 21);  // bottom-left
            g.DrawLine(pen, 15, 21, 21, 21);  // bottom-right
            // Door arc
            g.DrawArc(pen, 9, 15, 6, 6, 180, -90);
            // Small N-arrow
            using var nb = new SolidBrush(Color.FromArgb(40, 80, 160));
            using var nf = new Font("Arial", 6, FontStyle.Bold);
            g.DrawString("N", nf, nb, 9, 5);
        }

        // AND_Building – house silhouette (walls + roof triangle)
        private static void DrawBuilding(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(210, 235, 210));
            using var wallBrush = new SolidBrush(Color.FromArgb(230, 245, 230));
            using var roofBrush = new SolidBrush(Color.FromArgb(190, 100, 80));
            using var pen       = new Pen(Color.FromArgb(60, 130, 60), 1.5f);

            // Walls
            g.FillRectangle(wallBrush,  4, 13, 16, 9);
            g.DrawRectangle(pen,         4, 13, 16, 9);
            // Roof triangle
            var roofPts = new[] { new Point(2, 14), new Point(12, 4), new Point(22, 14) };
            g.FillPolygon(roofBrush, roofPts);
            g.DrawPolygon(pen, roofPts);
            // Door
            g.FillRectangle(new SolidBrush(Color.FromArgb(120, 80, 50)), 9, 17, 6, 5);
        }

        // AND_Orient – compass rose
        private static void DrawOrient(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(240, 230, 210));
            using var pen   = new Pen(Color.FromArgb(160, 100, 40), 1.2f);
            using var north = new SolidBrush(Color.FromArgb(200, 50, 50));
            using var south = new SolidBrush(Color.FromArgb(100, 100, 100));
            using var font  = new Font("Arial", 5, FontStyle.Bold);

            int cx = 12, cy = 12, r = 9;
            g.DrawEllipse(pen, cx - r, cy - r, r * 2, r * 2);

            // N-S arrow
            var nPts = new PointF[] { new(cx, cy - r + 1), new(cx - 3, cy), new(cx + 3, cy) };
            g.FillPolygon(north, nPts);
            var sPts = new PointF[] { new(cx, cy + r - 1), new(cx - 3, cy), new(cx + 3, cy) };
            g.FillPolygon(south, sPts);

            // E-W ticks
            g.DrawLine(pen, cx - r, cy, cx + r, cy);
            g.DrawString("N", font, north, cx - 3, 2);
        }

        // AND_Generate – three coloured room boxes (floor plan)
        private static void DrawGenerate(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(220, 240, 220));
            var cols = new[]
            {
                Color.FromArgb(150, 190, 240),
                Color.FromArgb(240, 180, 140),
                Color.FromArgb(180, 240, 180),
                Color.FromArgb(240, 230, 140)
            };
            int[][] rects = { new[]{3,3,10,10}, new[]{14,3,7,10}, new[]{3,14,18,7} };
            using var pen = new Pen(Color.FromArgb(60, 100, 60), 1f);
            for (int i = 0; i < rects.Length; i++)
            {
                var r = rects[i];
                using var b = new SolidBrush(cols[i]);
                g.FillRectangle(b,   r[0], r[1], r[2], r[3]);
                g.DrawRectangle(pen, r[0], r[1], r[2], r[3]);
            }
        }

        // AND_Shadow – sun + cast shadow
        private static void DrawShadow(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(255, 250, 220));
            using var sunBrush    = new SolidBrush(Color.FromArgb(255, 200, 50));
            using var shadowBrush = new SolidBrush(Color.FromArgb(100, 100, 100, 120));
            using var buildBrush  = new SolidBrush(Color.FromArgb(180, 190, 200));
            using var pen         = new Pen(Color.FromArgb(180, 120, 0), 1f);

            // Sun
            g.FillEllipse(sunBrush, 14, 2, 7, 7);
            // Building
            g.FillRectangle(buildBrush, 5, 10, 8, 8);
            // Shadow polygon
            var shadow = new PointF[] { new(5,18), new(13,18), new(20,22), new(2,22) };
            g.FillPolygon(shadowBrush, shadow);
            g.DrawRectangle(pen, 5, 10, 8, 8);
        }

        // AND_Roof – gable-end triangle + ridge
        private static void DrawRoof(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(240, 215, 200));
            using var roofBrush = new SolidBrush(Color.FromArgb(200, 80, 60));
            using var wallBrush = new SolidBrush(Color.FromArgb(220, 210, 195));
            using var pen       = new Pen(Color.FromArgb(140, 60, 40), 1.5f);
            using var ridgePen  = new Pen(Color.FromArgb(100, 40, 20), 1f);

            // Walls
            g.FillRectangle(wallBrush,  3, 15, 18, 7);
            g.DrawRectangle(pen,         3, 15, 18, 7);

            // Roof with overhang
            var roofPts = new[] { new Point(1, 16), new Point(12, 4), new Point(23, 16) };
            g.FillPolygon(roofBrush, roofPts);
            g.DrawPolygon(pen, roofPts);

            // Ridge line (perspective)
            g.DrawLine(ridgePen, 12, 4, 19, 7);
            g.DrawLine(ridgePen, 19, 7, 23, 16);
        }

        // AND_AI – speech bubble with "AI"
        private static void DrawAI(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(225, 210, 245));
            using var bubbleBrush = new SolidBrush(Color.FromArgb(255, 255, 255, 220));
            using var pen         = new Pen(Color.FromArgb(100, 40, 160), 1.5f);
            using var font        = new Font("Arial", 8, FontStyle.Bold);
            using var tb          = new SolidBrush(Color.FromArgb(100, 40, 160));

            // Speech bubble
            g.FillEllipse(bubbleBrush,  2, 2, 19, 15);
            g.DrawEllipse(pen,           2, 2, 19, 15);
            // Tail
            var tail = new PointF[] { new(7, 16), new(5, 22), new(11, 17) };
            g.FillPolygon(bubbleBrush, tail);
            g.DrawLines(pen, tail);
            // "AI" text
            g.DrawString("AI", font, tb, 5, 4);
        }

        // AND_OAuth – padlock
        private static void DrawOAuth(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(210, 230, 250));
            using var bodyBrush = new SolidBrush(Color.FromArgb(255, 195, 50));
            using var pen       = new Pen(Color.FromArgb(40, 80, 140), 1.5f);
            using var keyBrush  = new SolidBrush(Color.FromArgb(40, 80, 140));

            // Shackle arc
            g.DrawArc(pen, 7, 3, 10, 10, 180, 180);
            // Body
            g.FillRectangle(bodyBrush, 4, 12, 16, 9);
            g.DrawRectangle(pen,        4, 12, 16, 9);
            // Keyhole
            g.FillEllipse(keyBrush, 9, 14, 6, 5);
            g.FillRectangle(keyBrush, 10, 17, 4, 3);
        }

        // AND_Viz – coloured layer stack
        private static void DrawVisualize(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(255, 235, 210));
            var layerCols = new[]
            {
                Color.FromArgb(150, 190, 240),
                Color.FromArgb(240, 180, 140),
                Color.FromArgb(180, 240, 180)
            };
            using var pen = new Pen(Color.FromArgb(180, 100, 40), 1f);

            for (int i = 0; i < 3; i++)
            {
                int y = 5 + i * 6;
                using var b = new SolidBrush(layerCols[i]);
                // Parallelogram-ish layer
                var pts = new PointF[]
                {
                    new(4, y + 3), new(12, y), new(20, y + 3), new(12, y + 6)
                };
                g.FillPolygon(b, pts);
                g.DrawPolygon(pen, pts);
            }
        }

        // AND_Staircase – stair profile (zigzag)
        private static void DrawStaircase(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(220, 230, 245));
            using var pen    = new Pen(Color.FromArgb(50, 80, 150), 1.8f);
            using var fill   = new SolidBrush(Color.FromArgb(180, 200, 235));
            using var arrow  = new Pen(Color.FromArgb(200, 50, 50), 1.5f)
            {
                EndCap = LineCap.ArrowAnchor
            };

            // Stair steps (side view)
            var pts = new PointF[]
            {
                new(3, 21),
                new(3, 17), new(7, 17),
                new(7, 13), new(11, 13),
                new(11,  9), new(15,  9),
                new(15,  5), new(19,  5),
                new(19, 21)
            };
            g.FillPolygon(fill, pts);
            g.DrawLines(pen, pts);
            g.DrawLine(pen, 3, 21, 19, 21);

            // Up-arrow
            g.DrawLine(arrow, 21, 20, 21, 5);
        }

        // AND_Building basement variant (downward arrow + dashed)
        private static void DrawBasement(Graphics g, Bitmap _)
        {
            Background(g, Color.FromArgb(210, 205, 195));
            using var pen   = new Pen(Color.FromArgb(80, 60, 40), 1.5f);
            using var dash  = new Pen(Color.FromArgb(80, 60, 40), 1f)
                              { DashStyle = DashStyle.Dash };
            using var fill  = new SolidBrush(Color.FromArgb(190, 180, 160));
            using var arrow = new Pen(Color.FromArgb(80, 80, 200), 2f)
                              { EndCap = LineCap.ArrowAnchor };

            // Ground line
            g.DrawLine(pen, 2, 10, 22, 10);
            // Above-ground building (solid)
            g.FillRectangle(fill, 5, 3, 14, 7);
            g.DrawRectangle(pen,   5, 3, 14, 7);
            // Below-ground (dashed)
            g.DrawRectangle(dash, 5, 11, 14, 8);
            // Down-arrow
            g.DrawLine(arrow, 12, 12, 12, 18);
        }
    }
}
