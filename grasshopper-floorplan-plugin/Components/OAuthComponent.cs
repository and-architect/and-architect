using System;
using System.Drawing;
using Grasshopper.Kernel;
using AndArchitectGH.Core;

namespace AndArchitectGH.Components
{
    /// <summary>
    /// AND_OAuth – manages Claude OAuth token interactively from inside Grasshopper.
    ///
    /// Usage:
    ///   1. Paste your client_id (from console.anthropic.com → OAuth apps) into 'ID'
    ///   2. Press the 'Authorize' button (boolean True pulse)
    ///   3. Browser opens → log in with your Claude account → approve
    ///   4. Token is cached to ~/.and-architect/claude_oauth.json
    ///   5. Connect 'Token' output to AND_AI 'K' input  (set Provider=Claude)
    ///
    /// The token auto-refreshes in subsequent sessions if a refresh token was issued.
    /// Use 'Clear' to remove the cached token and force re-authentication.
    /// </summary>
    public class OAuthComponent : GH_Component
    {
        public OAuthComponent()
            : base("AND Claude OAuth", "AND_OAuth",
                   "Authenticate with Claude via OAuth 2.0 + PKCE.\n" +
                   "Stores the access token locally so you don't re-authenticate every session.\n\n" +
                   "Requires a registered OAuth app at console.anthropic.com.",
                   "AND Architect", "03 AI")
        { }

        public override Guid ComponentGuid =>
            new Guid("E0F1A2B3-C4D5-6789-4567-901234567890");
        protected override Bitmap? Icon => ComponentIcons.OAuthIcon;

        // ── Inputs ─────────────────────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager)
        {
            pManager.AddTextParameter("ClientID",   "ID",
                "OAuth client_id from console.anthropic.com → 'OAuth applications'",
                GH_ParamAccess.item, "");
            pManager.AddBooleanParameter("Authorize","Au",
                "Button: triggers browser-based login flow",
                GH_ParamAccess.item, false);
            pManager.AddBooleanParameter("Clear",   "Cl",
                "Button: clears the cached token (forces re-login next time)",
                GH_ParamAccess.item, false);

            pManager[0].Optional = true;
        }

        // ── Outputs ────────────────────────────────────────────────────────────

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddTextParameter("Token",  "T",
                "OAuth access token – connect to AND_AI 'K' input",
                GH_ParamAccess.item);
            pManager.AddBooleanParameter("Valid","V",
                "True = a valid cached token exists",
                GH_ParamAccess.item);
            pManager.AddTextParameter("Status", "S",
                "Status message",
                GH_ParamAccess.item);
        }

        // ── Solve ──────────────────────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            string clientId = "";
            bool   authorize = false;
            bool   clear     = false;

            DA.GetData(0, ref clientId);
            DA.GetData(1, ref authorize);
            DA.GetData(2, ref clear);

            // Clear cache
            if (clear)
            {
                OAuthHelper.ClearCache();
                DA.SetData(0, "");
                DA.SetData(1, false);
                DA.SetData(2, "Token-Cache gelöscht.");
                return;
            }

            // Try cached token first
            string? cached = OAuthHelper.GetCachedToken();
            if (cached != null && !authorize)
            {
                DA.SetData(0, cached);
                DA.SetData(1, true);
                DA.SetData(2, "Gültiger gecachter Token vorhanden.");
                return;
            }

            // Run browser flow if Authorize pressed
            if (authorize)
            {
                if (string.IsNullOrWhiteSpace(clientId))
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error,
                        "Client-ID fehlt. Trage deine OAuth-App-ID aus console.anthropic.com ein.");
                    DA.SetData(0, "");
                    DA.SetData(1, false);
                    DA.SetData(2, "Fehler: Client-ID fehlt.");
                    return;
                }

                AddRuntimeMessage(GH_RuntimeMessageLevel.Remark,
                    "Browser-Login wird gestartet … (Timeout: 120 s)");

                try
                {
                    string token = OAuthHelper.GetAccessToken(clientId);
                    DA.SetData(0, token);
                    DA.SetData(1, true);
                    DA.SetData(2, "OAuth erfolgreich. Token gespeichert.");
                }
                catch (TimeoutException)
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error,
                        "Timeout: Keine Antwort vom Browser innerhalb von 120 s.");
                    DA.SetData(0, "");
                    DA.SetData(1, false);
                    DA.SetData(2, "Timeout beim OAuth-Flow.");
                }
                catch (Exception ex)
                {
                    AddRuntimeMessage(GH_RuntimeMessageLevel.Error, ex.Message);
                    DA.SetData(0, "");
                    DA.SetData(1, false);
                    DA.SetData(2, $"Fehler: {ex.Message}");
                }
                return;
            }

            // No cached token, not authorizing
            DA.SetData(0, "");
            DA.SetData(1, false);
            DA.SetData(2, "Kein Token. Drücke 'Authorize' um dich anzumelden.");
        }
    }
}
