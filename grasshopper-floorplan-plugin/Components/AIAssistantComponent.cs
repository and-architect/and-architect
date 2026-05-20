using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using Grasshopper.Kernel;
using AndArchitectGH.Core;
using AndArchitectGH.Goo;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_AI – natural-language interface to Claude.
    /// Sends the current building state and a user prompt to the Anthropic API
    /// and returns architectural suggestions plus machine-parseable parameter changes.
    /// </summary>
    public class AIAssistantComponent : GH_Component
    {
        private string _lastResponse = "";
        private bool _wasSent = false;

        public AIAssistantComponent()
            : base("AND AI", "AND_AI",
                   "Ask Claude about your floor plan. Provide a text prompt and the current " +
                   "building context – the AI returns suggestions and concrete parameter changes.\n\n" +
                   "Tip: set Send=True (use a Button) to trigger the API call.",
                   "AND Architect", "03 AI")
        { }

        public override Guid ComponentGuid => new Guid("F5A6B7C8-D9E0-1234-F012-456789012345");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddTextParameter("Prompt",      "P",
                "Your architectural request in plain language.\n" +
                "Example: 'Move the master bedroom to the south side. " +
                "I want the kitchen to be open to the dining room.'",
                GH_ParamAccess.item, "");

            pManager.AddGenericParameter("Rooms",    "R",
                "Current room list (AND_Room) for context",
                GH_ParamAccess.list);

            pManager.AddGenericParameter("Building", "B",
                "Current building envelope (AND_Building) for context",
                GH_ParamAccess.item);

            pManager.AddGenericParameter("Orientation","O",
                "Site orientation (AND_Orientation) for context",
                GH_ParamAccess.item);

            pManager.AddTextParameter("APIKey",      "K",
                "Anthropic API key (sk-ant-…). " +
                "Use a Panel connected to a Secure String or store in environment var ANTHROPIC_API_KEY.",
                GH_ParamAccess.item, "");

            pManager.AddBooleanParameter("Send",     "S",
                "Set to True (Button) to send the prompt. Avoids accidental API calls.",
                GH_ParamAccess.item, false);

            pManager.AddIntegerParameter("MaxTokens","MT",
                "Maximum tokens in the AI response (default 1024)",
                GH_ParamAccess.item, 1024);

            pManager[1].Optional = true;
            pManager[2].Optional = true;
            pManager[3].Optional = true;
            pManager[6].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddTextParameter("Response",    "R",   "Full AI response",                     GH_ParamAccess.item);
            pManager.AddTextParameter("Suggestions", "S",   "Extracted bullet-point suggestions",   GH_ParamAccess.list);
            pManager.AddTextParameter("Changes",     "C",
                "Extracted parameter changes as 'Room|Field|Value|Reason' strings",                  GH_ParamAccess.list);
            pManager.AddTextParameter("JSON",        "J",   "Raw JSON block from AI response",      GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            string prompt    = "";
            var    roomGoos  = new List<IGH_Goo>();
            var    buildGoo  = default(IGH_Goo);
            var    orientGoo = default(IGH_Goo);
            string apiKey    = "";
            bool   send      = false;
            int    maxTok    = 1024;

            DA.GetData(0, ref prompt);
            DA.GetDataList(1, roomGoos);
            DA.GetData(2, ref buildGoo);
            DA.GetData(3, ref orientGoo);
            DA.GetData(4, ref apiKey);
            DA.GetData(5, ref send);
            DA.GetData(6, ref maxTok);

            // Always output last response so the component doesn't go blank
            DA.SetData(0, _lastResponse);

            if (!send || string.IsNullOrWhiteSpace(prompt))
            {
                if (!send) AddRuntimeMessage(GH_RuntimeMessageLevel.Remark,
                    "Set Send=True (Button) to query the AI.");
                return;
            }

            // Resolve API key (env var fallback)
            if (string.IsNullOrWhiteSpace(apiKey))
                apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ?? "";

            if (string.IsNullOrWhiteSpace(apiKey))
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error,
                    "No API key. Connect an Anthropic API key to the 'K' input or set " +
                    "environment variable ANTHROPIC_API_KEY.");
                return;
            }

            // Build context
            var rooms    = ExtractRooms(roomGoos);
            var building = ExtractBuilding(buildGoo);
            var orient   = ExtractOrientation(orientGoo);

            string context = AIClient.BuildContext(building, rooms, orient, null);

            // Call API
            AddRuntimeMessage(GH_RuntimeMessageLevel.Remark, "Calling Claude API…");

            string response;
            using var client = new AIClient(apiKey);
            try
            {
                response = client.Ask(prompt, context, maxTok);
            }
            catch (Exception ex)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, $"API call failed: {ex.Message}");
                return;
            }

            _lastResponse = response;

            // Parse JSON block
            string? jsonBlock = AIClient.ExtractJsonBlock(response);

            var suggestions = new List<string>();
            var changes     = new List<string>();

            if (jsonBlock != null)
            {
                try
                {
                    using var doc = System.Text.Json.JsonDocument.Parse(jsonBlock);
                    var root = doc.RootElement;

                    if (root.TryGetProperty("suggestions", out var sugs))
                        foreach (var s in sugs.EnumerateArray())
                            suggestions.Add(s.GetString() ?? "");

                    if (root.TryGetProperty("room_changes", out var rc))
                        foreach (var c in rc.EnumerateArray())
                        {
                            string n  = c.TryGetProperty("name",   out var pn) ? pn.GetString() ?? "" : "";
                            string f  = c.TryGetProperty("field",  out var pf) ? pf.GetString() ?? "" : "";
                            string v  = c.TryGetProperty("value",  out var pv) ? pv.GetString() ?? "" : "";
                            string r  = c.TryGetProperty("reason", out var pr) ? pr.GetString() ?? "" : "";
                            changes.Add($"{n}|{f}|{v}|{r}");
                        }

                    if (root.TryGetProperty("global_changes", out var gc))
                        foreach (var c in gc.EnumerateArray())
                        {
                            string f  = c.TryGetProperty("field",  out var pf) ? pf.GetString() ?? "" : "";
                            string v  = c.TryGetProperty("value",  out var pv) ? pv.GetString() ?? "" : "";
                            string r  = c.TryGetProperty("reason", out var pr) ? pr.GetString() ?? "" : "";
                            changes.Add($"GLOBAL|{f}|{v}|{r}");
                        }
                }
                catch
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                        "Could not parse JSON block from AI response.");
                }
            }

            DA.SetData(0, response);
            DA.SetDataList(1, suggestions);
            DA.SetDataList(2, changes);
            DA.SetData(3, jsonBlock ?? "");
        }

        // ── Extraction helpers ─────────────────────────────────────────────────

        private static List<Room> ExtractRooms(List<IGH_Goo> goos)
        {
            var rooms = new List<Room>();
            foreach (var g in goos)
            {
                if (g is GH_Room gr)   rooms.Add(gr.Value);
                else if (g?.ScriptVariable() is Room r) rooms.Add(r);
            }
            return rooms;
        }

        private static Building? ExtractBuilding(IGH_Goo? goo)
        {
            if (goo is GH_Building gb) return gb.Value;
            if (goo?.ScriptVariable() is Building b) return b;
            return null;
        }

        private static OrientationData? ExtractOrientation(IGH_Goo? goo)
        {
            if (goo is GH_Orientation go) return go.Value;
            if (goo?.ScriptVariable() is OrientationData od) return od;
            return null;
        }
    }
}
