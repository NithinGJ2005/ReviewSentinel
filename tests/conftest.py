"""conftest.py — shared pytest fixtures."""

import pytest


@pytest.fixture
def sample_diff_text():
    return """\
diff --git a/app/auth.py b/app/auth.py
index 1234567..abcdefg 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -5,6 +5,10 @@ import os
 
 def authenticate(username, password):
     conn = get_db()
-    query = f"SELECT * FROM users WHERE username='{username}'"
+    query = "SELECT * FROM users WHERE username=?"
+    cursor = conn.execute(query, (username,))
+    user = cursor.fetchone()
+    if user and user['password'] == password:
+        return True
     return False
"""
