import os

# Test-only signing key so app.main passes its startup JWT_SECRET check.
os.environ["JWT_SECRET"] = "test-only-jwt-secret-0123456789abcdef"
