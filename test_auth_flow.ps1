
# Test Auth Flow Script - Validates complete HttpOnly cookie authentication

param(
  [string]$BaseUrl = "http://localhost:8000",
  [string]$Username = "admin@aethelgard.com",
  [string]$Password = "ADMIN:aethelgard2026"
)

$ErrorActionPreference = "Stop"

function Test-Endpoint {
  param(
    [string]$Name,
    [string]$Method,
    [string]$Url,
    [object]$Body,
    [hashtable]$Headers,
    [object]$CookieContainer
  )
    
  Write-Host "`n========================================" -ForegroundColor Cyan
  Write-Host "TEST: $Name" -ForegroundColor Yellow
  Write-Host "========================================" -ForegroundColor Cyan
  Write-Host "URL: $Method $Url"
    
  try {
    $params = @{
      Method          = $Method
      Uri             = $Url
      Headers         = $Headers
      ErrorAction     = "Continue"
      SessionVariable = "Session"
      WebSession      = $CookieContainer
    }
        
    if ($Body) {
      $params["Body"] = $Body
      $params["ContentType"] = "application/x-www-form-urlencoded"
      Write-Host "Body: $Body"
    }
        
    $response = Invoke-WebRequest @params
        
    Write-Host "✅ Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "Response Body:" -ForegroundColor Green
    $body = $response.Content | ConvertFrom-Json
    $body | ConvertTo-Json | Write-Host
        
    return @{
      Success  = $true
      Response = $response
      Body     = $body
      Cookies  = $response.Headers["Set-Cookie"]
    }
        
  }
  catch {
    $errorResponse = $_.Exception.Response
    Write-Host "❌ Status: $($errorResponse.StatusCode)" -ForegroundColor Red
        
    try {
      $stream = $errorResponse.GetResponseStream()
      $reader = New-Object System.IO.StreamReader($stream)
      $content = $reader.ReadToEnd()
      Write-Host "Error Body: " -ForegroundColor Red
      $content | ConvertFrom-Json | ConvertTo-Json | Write-Host
      return @{
        Success = $false
        Status  = $errorResponse.StatusCode
        Body    = $content
      }
    }
    catch {
      Write-Host "Error reading response: $_" -ForegroundColor Red
      return @{
        Success = $false
        Error   = $_
      }
    }
  }
}

Write-Host "`n🔍 AETHELGARD AUTH FLOW TEST" -ForegroundColor Magenta
Write-Host "Testing complete HttpOnly cookie authentication flow`n" -ForegroundColor White

# Create a session to manage cookies
$webSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession

# Test 1: Login
$loginBody = "username=$Username&password=$Password"
$loginHeaders = @{
  "Content-Type" = "application/x-www-form-urlencoded"
}

$loginResult = Test-Endpoint `
  -Name "LOGIN (should set HttpOnly cookies)" `
  -Method "POST" `
  -Url "$BaseUrl/api/auth/login" `
  -Body $loginBody `
  -Headers $loginHeaders `
  -CookieContainer $webSession

if (-not $loginResult.Success) {
  Write-Host "`n❌ LOGIN FAILED - STOPPING TEST" -ForegroundColor Red
  exit 1
}

$userId = $loginResult.Body.user_id
Write-Host "`n✅ Login successful. User ID: $userId" -ForegroundColor Green

# Small delay to ensure cookies are set
Start-Sleep -Seconds 2

# Test 2: Get Current User (/auth/me) - should work with cookies
$meResult = Test-Endpoint `
  -Name "GET /auth/me (verify session via cookies)" `
  -Method "GET" `
  -Url "$BaseUrl/api/auth/me" `
  -CookieContainer $webSession

if (-not $meResult.Success) {
  Write-Host "`n❌ GET /auth/me FAILED - Cookies not working!" -ForegroundColor Red
  exit 1
}

Write-Host "`n✅ Session validated via /auth/me" -ForegroundColor Green

# Test 3: Access protected endpoint (/api/risk/status)
$statusResult = Test-Endpoint `
  -Name "GET /api/risk/status (protected endpoint)" `
  -Method "GET" `
  -Url "$BaseUrl/api/risk/status" `
  -CookieContainer $webSession

if (-not $statusResult.Success) {
  Write-Host "`n⚠️  /api/risk/status returned error" -ForegroundColor Yellow
}

# Test 4: Refresh Token
$refreshResult = Test-Endpoint `
  -Name "POST /auth/refresh (refresh access token)" `
  -Method "POST" `
  -Url "$BaseUrl/api/auth/refresh" `
  -CookieContainer $webSession

if ($refreshResult.Success) {
  Write-Host "`n✅ Token refresh successful" -ForegroundColor Green
}
else {
  Write-Host "`n⚠️  Token refresh failed: $($refreshResult.Body)" -ForegroundColor Yellow
}

# Test 5: Logout
$logoutResult = Test-Endpoint `
  -Name "POST /auth/logout (revoke session)" `
  -Method "POST" `
  -Url "$BaseUrl/api/auth/logout" `
  -CookieContainer $webSession

if ($logoutResult.Success) {
  Write-Host "`n✅ Logout successful" -ForegroundColor Green
}
else {
  Write-Host "`n❌ Logout failed" -ForegroundColor Red
}

# Test 6: Try to use session after logout - should fail
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "TEST: Verify session is revoked after logout" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan

try {
  $revokedResponse = Invoke-WebRequest `
    -Method GET `
    -Uri "$BaseUrl/api/auth/me" `
    -WebSession $webSession `
    -ErrorAction Continue
    
  Write-Host "❌ Session still valid after logout! (BAD)" -ForegroundColor Red
}
catch {
  if ($_.Exception.Response.StatusCode -eq 401) {
    Write-Host "✅ Session properly revoked (401 Unauthorized)" -ForegroundColor Green
  }
  else {
    Write-Host "⚠️  Unexpected error: $($_.Exception.Response.StatusCode)" -ForegroundColor Yellow
  }
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "✅ TEST COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
