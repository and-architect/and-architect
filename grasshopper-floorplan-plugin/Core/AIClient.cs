using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace AndArchitectGH.Core
{
    /// <summary>
    /// Thin synchronous wrapper around the Anthropic Messages API.
    /// Sends the current floor-plan state as context and returns Claude's
    /// architectural suggestions.
    /// </summary>
    public class AIClient : IDisposable
    {
        private readonly HttpClient _http;
        private bool _disposed;

        private const string ApiUrl = "https://api.anthropic.com/v1/messages";
        private const string AnthropicVersion = "2023-06-01";
        private const string Model = "claude-opus-4-7";

        private static readonly string SystemPrompt =
            "You are an expert architect and space-planner specialised in residential and " +
            "small commercial buildings. You help users optimise 3-D floor-plan layouts.\n\n" +
            "When given a building description and a user request you respond with:\n" +
            "1. A short explanation of your reasoning (1-3 sentences).\n" +
            "2. A JSON block tagged ```json … ``` containing:\n" +
            "   {\n" +
            "     \"suggestions\": [\"<action>\", …],\n" +
            "     \"room_changes\": [\n" +
            "       {\"name\": \"<room>\", \"field\": \"<property>\", \"value\": \"<new>\", \"reason\": \"<why>\"}\n" +
            "     ],\n" +
            "     \"global_changes\": [\n" +
            "       {\"field\": \"<property>\", \"value\": \"<new>\", \"reason\": \"<why>\"}\n" +
            "     ]\n" +
            "   }\n" +
            "Always think in 3-D space. Mention floor levels explicitly. " +
            "Keep room_changes and global_changes concrete and machine-parseable.";

        public AIClient(string apiKey)
        {
            _http = new HttpClient();
            _http.DefaultRequestHeaders.Add("x-api-key", apiKey);
            _http.DefaultRequestHeaders.Add("anthropic-version", AnthropicVersion);
            _http.Timeout = TimeSpan.FromSeconds(60);
        }

        // ── Public API ─────────────────────────────────────────────────────────

        /// <summary>
        /// Synchronously sends a prompt + context to Claude and returns the raw text.
        /// </summary>
        public string Ask(string userPrompt, string buildingContext, int maxTokens = 1024)
        {
            var requestBody = new
            {
                model = Model,
                max_tokens = maxTokens,
                system = SystemPrompt,
                messages = new[]
                {
                    new
                    {
                        role = "user",
                        content = $"## Current Building State\n\n{buildingContext}\n\n## Request\n\n{userPrompt}"
                    }
                }
            };

            var json = JsonSerializer.Serialize(requestBody);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            HttpResponseMessage response;
            try
            {
                // Grasshopper components must not block the UI thread for too long;
                // callers should trigger this only on explicit user action.
                response = _http.PostAsync(ApiUrl, content).GetAwaiter().GetResult();
            }
            catch (Exception ex)
            {
                return $"[Network error] {ex.Message}";
            }

            var body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();

            if (!response.IsSuccessStatusCode)
                return $"[API error {(int)response.StatusCode}] {body}";

            try
            {
                using var doc = JsonDocument.Parse(body);
                return doc.RootElement
                           .GetProperty("content")[0]
                           .GetProperty("text")
                           .GetString() ?? "No content in response.";
            }
            catch
            {
                return body;  // return raw body if parsing fails
            }
        }

        // ── Building-context serialiser ────────────────────────────────────────

        /// <summary>
        /// Converts the current building + room list into a readable text summary
        /// that Claude can understand.
        /// </summary>
        public static string BuildContext(
            Building? building,
            List<Room> rooms,
            OrientationData? orientation,
            FloorplanVariant? activeVariant)
        {
            var sb = new StringBuilder();

            if (building != null)
            {
                sb.AppendLine($"Building footprint: {building.FootprintWidth:F1} × {building.FootprintDepth:F1} m");
                sb.AppendLine($"Floors: {building.NumberOfFloors}  |  Floor height: {building.FloorHeight:F1} m");
                sb.AppendLine($"Total GFA: {building.FootprintArea * building.NumberOfFloors:F0} m²");
            }

            if (orientation != null)
            {
                sb.AppendLine($"North vector: {orientation.North}");
                sb.AppendLine($"Latitude: {orientation.Latitude:F1}°");
                if (orientation.ViewPoints.Count > 0)
                    sb.AppendLine($"View points: {orientation.ViewPoints.Count}");
            }

            sb.AppendLine();
            sb.AppendLine("Rooms:");
            foreach (var r in rooms)
            {
                sb.Append($"  [{r.Floor}] {r.Name}  area={r.Area:F1} m²  type={r.Type}");
                sb.Append($"  solar={r.SolarPref}");
                if (r.MustBeNear.Count > 0)
                    sb.Append($"  near=[{string.Join(",", r.MustBeNear)}]");
                if (r.MustBeAway.Count > 0)
                    sb.Append($"  away=[{string.Join(",", r.MustBeAway)}]");
                sb.AppendLine();
            }

            if (activeVariant != null)
            {
                sb.AppendLine();
                sb.AppendLine($"Active layout (score={activeVariant.Score:F3}):");
                foreach (var pr in activeVariant.Rooms)
                {
                    var o = pr.Box.Plane.Origin;
                    sb.AppendLine(
                        $"  {pr.Name}  pos=({o.X:F1},{o.Y:F1},{o.Z:F1})  " +
                        $"{pr.Box.X.Length:F1}×{pr.Box.Y.Length:F1} m");
                }
            }

            return sb.ToString();
        }

        // ── Parsing helpers ────────────────────────────────────────────────────

        /// <summary>
        /// Extracts the first ```json … ``` block from the AI response.
        /// Returns null if none found.
        /// </summary>
        public static string? ExtractJsonBlock(string response)
        {
            const string start = "```json";
            const string end   = "```";
            int s = response.IndexOf(start, StringComparison.Ordinal);
            if (s < 0) return null;
            s += start.Length;
            int e = response.IndexOf(end, s, StringComparison.Ordinal);
            if (e < 0) return null;
            return response.Substring(s, e - s).Trim();
        }

        public void Dispose()
        {
            if (!_disposed) { _http.Dispose(); _disposed = true; }
        }
    }
}
