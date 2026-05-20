using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace AndArchitectGH.Core
{
    // ─── Provider interface ────────────────────────────────────────────────────

    public interface ILLMClient : IDisposable
    {
        string ProviderName { get; }
        string Ask(string systemPrompt, string userMessage, int maxTokens = 1024);
    }

    public enum LLMProvider { Claude, OpenAI, Gemini }

    // ─── Factory ───────────────────────────────────────────────────────────────

    public static class LLMClientFactory
    {
        public static ILLMClient Create(LLMProvider provider, string apiKey) => provider switch
        {
            LLMProvider.Claude => new AnthropicClient(apiKey),
            LLMProvider.OpenAI => new OpenAIClient(apiKey),
            LLMProvider.Gemini => new GeminiClient(apiKey),
            _                  => throw new ArgumentException($"Unknown provider: {provider}")
        };

        /// <summary>
        /// Creates a Claude client using an OAuth access token instead of an API key.
        /// </summary>
        public static ILLMClient CreateWithOAuth(string accessToken) =>
            new AnthropicClient(accessToken, isOAuth: true);
    }

    // ─── Anthropic Claude ──────────────────────────────────────────────────────

    public class AnthropicClient : ILLMClient
    {
        private readonly HttpClient _http;
        private bool _disposed;
        private const string ApiUrl = "https://api.anthropic.com/v1/messages";
        private const string AnthropicVersion = "2023-06-01";
        private const string DefaultModel = "claude-opus-4-7";

        public string ProviderName => "Anthropic Claude";

        public AnthropicClient(string apiKey, bool isOAuth = false)
        {
            _http = new HttpClient { Timeout = TimeSpan.FromSeconds(90) };
            if (isOAuth)
                _http.DefaultRequestHeaders.Authorization =
                    new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", apiKey);
            else
                _http.DefaultRequestHeaders.Add("x-api-key", apiKey);
            _http.DefaultRequestHeaders.Add("anthropic-version", AnthropicVersion);
        }

        public string Ask(string systemPrompt, string userMessage, int maxTokens = 1024)
        {
            var body = new
            {
                model = DefaultModel,
                max_tokens = maxTokens,
                system = systemPrompt,
                messages = new[] { new { role = "user", content = userMessage } }
            };

            return Post(ApiUrl, body, resp =>
            {
                using var doc = JsonDocument.Parse(resp);
                return doc.RootElement.GetProperty("content")[0]
                           .GetProperty("text").GetString() ?? "";
            });
        }

        private string Post<T>(string url, T body, Func<string, string> parse)
        {
            var json    = JsonSerializer.Serialize(body);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            try
            {
                var resp    = _http.PostAsync(url, content).GetAwaiter().GetResult();
                var raw     = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                if (!resp.IsSuccessStatusCode)
                    return $"[Claude API {(int)resp.StatusCode}] {raw}";
                return parse(raw);
            }
            catch (Exception ex) { return $"[Claude network error] {ex.Message}"; }
        }

        public void Dispose() { if (!_disposed) { _http.Dispose(); _disposed = true; } }
    }

    // ─── OpenAI ───────────────────────────────────────────────────────────────

    public class OpenAIClient : ILLMClient
    {
        private readonly HttpClient _http;
        private bool _disposed;
        private const string ApiUrl  = "https://api.openai.com/v1/chat/completions";
        private const string Model   = "gpt-4o";

        public string ProviderName => "OpenAI GPT-4o";

        public OpenAIClient(string apiKey)
        {
            _http = new HttpClient { Timeout = TimeSpan.FromSeconds(90) };
            _http.DefaultRequestHeaders.Authorization =
                new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", apiKey);
        }

        public string Ask(string systemPrompt, string userMessage, int maxTokens = 1024)
        {
            var body = new
            {
                model = Model,
                max_tokens = maxTokens,
                messages = new[]
                {
                    new { role = "system",  content = systemPrompt },
                    new { role = "user",    content = userMessage  }
                }
            };

            var json    = JsonSerializer.Serialize(body);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            try
            {
                var resp = _http.PostAsync(ApiUrl, content).GetAwaiter().GetResult();
                var raw  = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                if (!resp.IsSuccessStatusCode)
                    return $"[OpenAI API {(int)resp.StatusCode}] {raw}";
                using var doc = JsonDocument.Parse(raw);
                return doc.RootElement
                          .GetProperty("choices")[0]
                          .GetProperty("message")
                          .GetProperty("content").GetString() ?? "";
            }
            catch (Exception ex) { return $"[OpenAI network error] {ex.Message}"; }
        }

        public void Dispose() { if (!_disposed) { _http.Dispose(); _disposed = true; } }
    }

    // ─── Google Gemini ────────────────────────────────────────────────────────

    public class GeminiClient : ILLMClient
    {
        private readonly HttpClient _http;
        private readonly string _apiKey;
        private bool _disposed;
        private const string Model = "gemini-2.0-flash";

        public string ProviderName => "Google Gemini";

        public GeminiClient(string apiKey)
        {
            _apiKey = apiKey;
            _http   = new HttpClient { Timeout = TimeSpan.FromSeconds(90) };
        }

        public string Ask(string systemPrompt, string userMessage, int maxTokens = 1024)
        {
            // Gemini combines system + user into the first user turn
            var combined = $"{systemPrompt}\n\n{userMessage}";
            var url  = $"https://generativelanguage.googleapis.com/v1beta/models/{Model}" +
                       $":generateContent?key={_apiKey}";

            var body = new
            {
                contents = new[]
                {
                    new { role = "user", parts = new[] { new { text = combined } } }
                },
                generationConfig = new { maxOutputTokens = maxTokens }
            };

            var json    = JsonSerializer.Serialize(body);
            var content = new StringContent(json, Encoding.UTF8, "application/json");
            try
            {
                var resp = _http.PostAsync(url, content).GetAwaiter().GetResult();
                var raw  = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                if (!resp.IsSuccessStatusCode)
                    return $"[Gemini API {(int)resp.StatusCode}] {raw}";
                using var doc = JsonDocument.Parse(raw);
                return doc.RootElement
                          .GetProperty("candidates")[0]
                          .GetProperty("content")
                          .GetProperty("parts")[0]
                          .GetProperty("text").GetString() ?? "";
            }
            catch (Exception ex) { return $"[Gemini network error] {ex.Message}"; }
        }

        public void Dispose() { if (!_disposed) { _http.Dispose(); _disposed = true; } }
    }

    // ─── Shared system prompt ─────────────────────────────────────────────────

    public static class ArchitectSystemPrompt
    {
        public const string Text =
            "You are an expert architect and space-planner specialised in residential and " +
            "small commercial buildings. You help users optimise 3-D floor-plan layouts.\n\n" +
            "When given a building description and a user request respond with:\n" +
            "1. A short explanation of your reasoning (1-3 sentences).\n" +
            "2. A JSON block tagged ```json … ``` containing:\n" +
            "   {\n" +
            "     \"suggestions\": [\"<action>\", …],\n" +
            "     \"room_changes\": [\n" +
            "       {\"name\":\"<room>\",\"field\":\"<property>\",\"value\":\"<new>\",\"reason\":\"<why>\"}\n" +
            "     ],\n" +
            "     \"global_changes\": [\n" +
            "       {\"field\":\"<property>\",\"value\":\"<new>\",\"reason\":\"<why>\"}\n" +
            "     ]\n" +
            "   }\n" +
            "Always think in 3-D space. Mention floor levels explicitly. " +
            "Keep changes concrete and machine-parseable.";
    }
}
