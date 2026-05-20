using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Types;
using AndArchitectGH.Core;
using AndArchitectGH.Goo;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_AI – Multi-provider AI assistant.
    /// Supports Claude (API key), Claude (OAuth), OpenAI (GPT-4o), Google Gemini.
    /// Sends the current building state as context and returns structured suggestions.
    /// </summary>
    public class AIAssistantComponent : GH_Component
    {
        private string _lastResponse = "";

        public AIAssistantComponent()
            : base("AND AI", "AND_AI",
                   "Natural-language floor-plan assistant.\n" +
                   "Providers: Claude (API key) | Claude (OAuth) | OpenAI | Gemini\n\n" +
                   "Connect a Button to Send to avoid accidental API calls.",
                   "AND Architect", "03 AI")
        { }

        public override Guid ComponentGuid =>
            new Guid("F5A6B7C8-D9E0-1234-F012-456789012345");
        protected override Bitmap Icon => null!;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddTextParameter("Prompt",    "P",
                "Architectural request in plain language.\n" +
                "Example: 'Wohnzimmer nach Süden, Küche neben Essen, drittes Geschoss ergänzen.'",
                GH_ParamAccess.item, "");

            pManager.AddTextParameter("Provider",  "Pr",
                "AI provider: Claude | OpenAI | Gemini  (default: Claude)",
                GH_ParamAccess.item, "Claude");

            pManager.AddTextParameter("APIKey",    "K",
                "API key for the selected provider.\n" +
                "Claude    → sk-ant-…  or leave empty for OAuth\n" +
                "OpenAI    → sk-…\n" +
                "Gemini    → AIza…\n" +
                "Env vars: ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY",
                GH_ParamAccess.item, "");

            pManager.AddTextParameter("OAuthID",   "OA",
                "Claude OAuth: your registered client_id (console.anthropic.com).\n" +
                "Leave empty to use API key instead.",
                GH_ParamAccess.item, "");

            pManager.AddGenericParameter("Rooms",    "R",  "Current room list (AND_Room)",    GH_ParamAccess.list);
            pManager.AddGenericParameter("Building", "B",  "Building envelope (AND_Building)", GH_ParamAccess.item);
            pManager.AddGenericParameter("Orient",   "O",  "Site orientation (AND_Orientation)", GH_ParamAccess.item);

            pManager.AddBooleanParameter("Send",   "S",
                "Set True / press Button to query the AI.",
                GH_ParamAccess.item, false);

            pManager.AddIntegerParameter("MaxTok", "MT",
                "Maximum response tokens (default 1024)",
                GH_ParamAccess.item, 1024);

            // Most inputs are optional
            for (int i = 1; i <= 8; i++) pManager[i].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddTextParameter("Response",    "R",  "Full AI response",                     GH_ParamAccess.item);
            pManager.AddTextParameter("Suggestions", "S",  "Bullet-point suggestions",             GH_ParamAccess.list);
            pManager.AddTextParameter("Changes",     "C",
                "Parameter changes as 'Room|Field|Value|Reason' (pipe-separated)",                  GH_ParamAccess.list);
            pManager.AddTextParameter("JSON",        "J",  "Raw JSON block from response",         GH_ParamAccess.item);
            pManager.AddTextParameter("Provider",    "Pr", "Active provider name",                 GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            string prompt    = "";
            string provider  = "Claude";
            string apiKey    = "";
            string oauthId   = "";
            var    roomGoos  = new List<IGH_Goo>();
            var    buildGoo  = default(IGH_Goo);
            var    orientGoo = default(IGH_Goo);
            bool   send      = false;
            int    maxTok    = 1024;

            DA.GetData(0, ref prompt);
            DA.GetData(1, ref provider);
            DA.GetData(2, ref apiKey);
            DA.GetData(3, ref oauthId);
            DA.GetDataList(4, roomGoos);
            DA.GetData(5, ref buildGoo);
            DA.GetData(6, ref orientGoo);
            DA.GetData(7, ref send);
            DA.GetData(8, ref maxTok);

            DA.SetData(0, _lastResponse);
            DA.SetData(4, provider);

            if (!send || string.IsNullOrWhiteSpace(prompt))
            {
                if (!send)
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Remark,
                        "Send=False. Verbinde einen Button mit 'S' um die KI abzufragen.");
                return;
            }

            // Resolve provider enum
            if (!Enum.TryParse<LLMProvider>(provider, true, out var llmProvider))
            {
                // Aliases
                llmProvider = provider.ToLowerInvariant() switch
                {
                    "gpt" or "gpt4" or "gpt-4" or "openai" => LLMProvider.OpenAI,
                    "google" or "gemini"                    => LLMProvider.Gemini,
                    _                                       => LLMProvider.Claude
                };
            }

            // Resolve API key (env var fallback)
            if (string.IsNullOrWhiteSpace(apiKey))
            {
                apiKey = llmProvider switch
                {
                    LLMProvider.Claude => Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ?? "",
                    LLMProvider.OpenAI => Environment.GetEnvironmentVariable("OPENAI_API_KEY")    ?? "",
                    LLMProvider.Gemini => Environment.GetEnvironmentVariable("GEMINI_API_KEY")    ?? "",
                    _                  => ""
                };
            }

            // Build building context string
            var rooms    = ExtractRooms(roomGoos);
            var building = ExtractBuilding(buildGoo);
            var orient   = ExtractOrientation(orientGoo);
            var context  = AIClient.BuildContext(building, rooms, orient, null);

            // Create client
            ILLMClient client;
            try
            {
                if (llmProvider == LLMProvider.Claude && string.IsNullOrWhiteSpace(apiKey)
                    && !string.IsNullOrWhiteSpace(oauthId))
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Remark,
                        "Claude OAuth: Browser-Anmeldung wird gestartet …");
                    string token = OAuthHelper.GetAccessToken(oauthId);
                    client = LLMClientFactory.CreateWithOAuth(token);
                }
                else if (string.IsNullOrWhiteSpace(apiKey))
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error,
                        $"Kein API Key für {llmProvider}. Trage ihn in 'K' ein oder setze " +
                        "ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY als Umgebungsvariable.");
                    return;
                }
                else
                {
                    client = LLMClientFactory.Create(llmProvider, apiKey);
                }
            }
            catch (Exception ex)
            {
                AddRuntimeMessage(GH_RuntimeMessageLevel.Error, $"Client-Erstellung fehlgeschlagen: {ex.Message}");
                return;
            }

            // Call API
            string response;
            using (client)
            {
                try
                {
                    response = client.Ask(
                        ArchitectSystemPrompt.Text,
                        $"## Aktuelles Gebäude\n\n{context}\n\n## Anfrage\n\n{prompt}",
                        maxTok);
                }
                catch (Exception ex)
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error, $"API-Fehler: {ex.Message}");
                    return;
                }
            }

            _lastResponse = response;

            // Parse JSON block
            string? jsonBlock = AIClient.ExtractJsonBlock(response);
            var suggestions   = new List<string>();
            var changes       = new List<string>();

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
                            changes.Add(FormatChange(c));

                    if (root.TryGetProperty("global_changes", out var gc))
                        foreach (var c in gc.EnumerateArray())
                            changes.Add(FormatGlobalChange(c));
                }
                catch
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Warning,
                        "JSON-Block aus KI-Antwort konnte nicht geparst werden.");
                }
            }

            DA.SetData(0, response);
            DA.SetDataList(1, suggestions);
            DA.SetDataList(2, changes);
            DA.SetData(3, jsonBlock ?? "");
            DA.SetData(4, client?.ProviderName ?? provider);
        }

        // ── Helpers ────────────────────────────────────────────────────────────

        private static string FormatChange(System.Text.Json.JsonElement c)
        {
            string n = c.TryGetProperty("name",   out var p1) ? p1.GetString() ?? "" : "";
            string f = c.TryGetProperty("field",  out var p2) ? p2.GetString() ?? "" : "";
            string v = c.TryGetProperty("value",  out var p3) ? p3.GetString() ?? "" : "";
            string r = c.TryGetProperty("reason", out var p4) ? p4.GetString() ?? "" : "";
            return $"{n}|{f}|{v}|{r}";
        }

        private static string FormatGlobalChange(System.Text.Json.JsonElement c)
        {
            string f = c.TryGetProperty("field",  out var p1) ? p1.GetString() ?? "" : "";
            string v = c.TryGetProperty("value",  out var p2) ? p2.GetString() ?? "" : "";
            string r = c.TryGetProperty("reason", out var p3) ? p3.GetString() ?? "" : "";
            return $"GLOBAL|{f}|{v}|{r}";
        }

        private static List<Room> ExtractRooms(List<IGH_Goo> goos)
        {
            var rooms = new List<Room>();
            foreach (var g in goos)
            {
                if (g is GH_Room gr) rooms.Add(gr.Value);
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
