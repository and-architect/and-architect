using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Net.Http;
using System.Threading;

namespace AndArchitectGH.Core
{
    /// <summary>
    /// Implements OAuth 2.0 + PKCE for Claude.ai (Anthropic).
    ///
    /// Flow:
    ///   1. Generate PKCE verifier + challenge
    ///   2. Open the browser to the Anthropic auth URL
    ///   3. Spin up a local HTTP listener on http://localhost:7878/callback
    ///   4. User authorises → browser redirects with ?code=…
    ///   5. Exchange code for access + refresh tokens
    ///   6. Cache tokens to ~/.and-architect/claude_oauth.json
    ///
    /// Note: You must register your application at console.anthropic.com to get
    /// a client_id. The redirect URI to register is http://localhost:7878/callback
    /// </summary>
    public static class OAuthHelper
    {
        // ── Constants ──────────────────────────────────────────────────────────

        private const string AuthEndpoint  = "https://claude.ai/oauth/authorize";
        private const string TokenEndpoint = "https://claude.ai/oauth/token";
        private const string RedirectUri   = "http://localhost:7878/callback";
        private const string Scopes        = "api";
        private const int    ListenPort    = 7878;
        private const int    TimeoutSec    = 120;

        private static readonly string CacheDir =
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                         ".and-architect");

        private static readonly string TokenFile =
            Path.Combine(CacheDir, "claude_oauth.json");

        // ── Public API ─────────────────────────────────────────────────────────

        /// <summary>
        /// Returns a valid access token, using the cache if available.
        /// If no valid token is found, triggers the full browser auth flow.
        /// </summary>
        public static string GetAccessToken(string clientId)
        {
            // 1. Try cache
            var cached = TryLoadCached();
            if (cached != null)
            {
                if (!cached.IsExpired()) return cached.AccessToken;
                if (!string.IsNullOrEmpty(cached.RefreshToken))
                {
                    var refreshed = TryRefresh(clientId, cached.RefreshToken);
                    if (refreshed != null)
                    {
                        SaveToken(refreshed);
                        return refreshed.AccessToken;
                    }
                }
            }

            // 2. Full browser flow
            return RunBrowserFlow(clientId);
        }

        /// <summary>
        /// Returns the access token from cache without triggering a browser flow.
        /// Returns null if no valid cached token exists.
        /// </summary>
        public static string? GetCachedToken()
        {
            var cached = TryLoadCached();
            if (cached != null && !cached.IsExpired()) return cached.AccessToken;
            return null;
        }

        /// <summary>Clears the cached OAuth token.</summary>
        public static void ClearCache()
        {
            if (File.Exists(TokenFile)) File.Delete(TokenFile);
        }

        // ── PKCE helpers ───────────────────────────────────────────────────────

        private static string GenerateCodeVerifier()
        {
            var bytes = new byte[64];
            RandomNumberGenerator.Fill(bytes);
            return Base64UrlEncode(bytes);
        }

        private static string ComputeCodeChallenge(string verifier)
        {
            var hash = SHA256.HashData(Encoding.ASCII.GetBytes(verifier));
            return Base64UrlEncode(hash);
        }

        private static string Base64UrlEncode(byte[] bytes) =>
            Convert.ToBase64String(bytes)
                   .TrimEnd('=')
                   .Replace('+', '-')
                   .Replace('/', '_');

        private static string GenerateState()
        {
            var b = new byte[16];
            RandomNumberGenerator.Fill(b);
            return Convert.ToHexString(b).ToLowerInvariant();
        }

        // ── Browser flow ───────────────────────────────────────────────────────

        private static string RunBrowserFlow(string clientId)
        {
            var verifier   = GenerateCodeVerifier();
            var challenge  = ComputeCodeChallenge(verifier);
            var state      = GenerateState();

            var authUrl = BuildAuthUrl(clientId, challenge, state);

            OpenBrowser(authUrl);

            // Listen for callback
            var code = WaitForCallback(state);
            if (code == null)
                throw new TimeoutException(
                    $"OAuth timed out after {TimeoutSec}s. No authorisation code received.");

            // Exchange code for token
            var token = ExchangeCode(clientId, code, verifier);
            SaveToken(token);
            return token.AccessToken;
        }

        private static string BuildAuthUrl(string clientId, string challenge, string state)
        {
            return $"{AuthEndpoint}" +
                   $"?response_type=code" +
                   $"&client_id={Uri.EscapeDataString(clientId)}" +
                   $"&redirect_uri={Uri.EscapeDataString(RedirectUri)}" +
                   $"&scope={Uri.EscapeDataString(Scopes)}" +
                   $"&state={state}" +
                   $"&code_challenge={challenge}" +
                   $"&code_challenge_method=S256";
        }

        private static void OpenBrowser(string url)
        {
            try
            {
                if (OperatingSystem.IsMacOS())
                    Process.Start("open", url);
                else if (OperatingSystem.IsLinux())
                    Process.Start("xdg-open", url);
                else
                    Process.Start(new ProcessStartInfo { FileName = url, UseShellExecute = true });
            }
            catch
            {
                Console.WriteLine($"Open this URL in your browser:\n{url}");
            }
        }

        private static string? WaitForCallback(string expectedState)
        {
            using var listener = new HttpListener();
            listener.Prefixes.Add($"http://localhost:{ListenPort}/callback/");
            listener.Start();

            string? receivedCode = null;
            var deadline = DateTime.UtcNow.AddSeconds(TimeoutSec);

            while (DateTime.UtcNow < deadline)
            {
                var ctx = listener.GetContext();
                var qs  = ctx.Request.QueryString;

                // Always send a response so the browser doesn't hang
                var html = "<html><body><h2>AND Architect – Authorisation complete</h2>" +
                           "<p>You can close this tab.</p></body></html>";
                var buf = Encoding.UTF8.GetBytes(html);
                ctx.Response.ContentLength64 = buf.Length;
                ctx.Response.ContentType = "text/html; charset=utf-8";
                ctx.Response.OutputStream.Write(buf);
                ctx.Response.Close();

                if (qs["state"] == expectedState && qs["code"] != null)
                {
                    receivedCode = qs["code"];
                    break;
                }
            }

            listener.Stop();
            return receivedCode;
        }

        // ── Token exchange ─────────────────────────────────────────────────────

        private static OAuthToken ExchangeCode(string clientId, string code, string verifier)
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
            var body = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["grant_type"]    = "authorization_code",
                ["client_id"]     = clientId,
                ["code"]          = code,
                ["redirect_uri"]  = RedirectUri,
                ["code_verifier"] = verifier
            });

            var resp = http.PostAsync(TokenEndpoint, body).GetAwaiter().GetResult();
            var raw  = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
            if (!resp.IsSuccessStatusCode)
                throw new InvalidOperationException($"Token exchange failed ({resp.StatusCode}): {raw}");

            return ParseTokenResponse(raw);
        }

        private static OAuthToken? TryRefresh(string clientId, string refreshToken)
        {
            try
            {
                using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
                var body = new FormUrlEncodedContent(new Dictionary<string, string>
                {
                    ["grant_type"]    = "refresh_token",
                    ["client_id"]     = clientId,
                    ["refresh_token"] = refreshToken
                });
                var resp = http.PostAsync(TokenEndpoint, body).GetAwaiter().GetResult();
                var raw  = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                return resp.IsSuccessStatusCode ? ParseTokenResponse(raw) : null;
            }
            catch { return null; }
        }

        private static OAuthToken ParseTokenResponse(string raw)
        {
            using var doc = JsonDocument.Parse(raw);
            var root = doc.RootElement;
            return new OAuthToken
            {
                AccessToken  = root.GetProperty("access_token").GetString()!,
                RefreshToken = root.TryGetProperty("refresh_token", out var rt) ? rt.GetString() : null,
                ExpiresAt    = DateTime.UtcNow.AddSeconds(
                    root.TryGetProperty("expires_in", out var ei) ? ei.GetInt32() : 3600)
            };
        }

        // ── Token cache ────────────────────────────────────────────────────────

        private static OAuthToken? TryLoadCached()
        {
            try
            {
                if (!File.Exists(TokenFile)) return null;
                var json = File.ReadAllText(TokenFile);
                return JsonSerializer.Deserialize<OAuthToken>(json);
            }
            catch { return null; }
        }

        private static void SaveToken(OAuthToken token)
        {
            Directory.CreateDirectory(CacheDir);
            File.WriteAllText(TokenFile,
                JsonSerializer.Serialize(token, new JsonSerializerOptions { WriteIndented = true }));
        }

        // ── Token record ───────────────────────────────────────────────────────

        private class OAuthToken
        {
            public string  AccessToken  { get; set; } = "";
            public string? RefreshToken { get; set; }
            public DateTime ExpiresAt   { get; set; } = DateTime.MinValue;
            public bool IsExpired() => DateTime.UtcNow >= ExpiresAt.AddMinutes(-5);
        }
    }
}
