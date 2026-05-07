#!/usr/bin/env python
"""Validate that all modules can be imported and FastAPI routes are registered."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("🔍 Validating imports and routes...\n")

try:
    print("1️⃣  Importing main app...")
    from backend.app.main import app
    print("   ✅ app/main.py imported successfully\n")
    
    print("2️⃣  Checking registered routes:")
    routes_found = {}
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            path = route.path
            methods = ', '.join(sorted(route.methods - {'OPTIONS', 'HEAD'}))
            if path not in routes_found:
                routes_found[path] = []
            routes_found[path].append(methods)
    
    # Filter and display profile-related routes
    profile_routes = {k: v for k, v in routes_found.items() if 'profile' in k.lower() or 'upload' in k.lower()}
    
    if profile_routes:
        print("   ✅ Profile routes found:")
        for path, methods in sorted(profile_routes.items()):
            print(f"      {path}: {methods[0]}")
    else:
        print("   ⚠️  No profile routes found!")
    
    print(f"\n3️⃣  Total routes registered: {len(routes_found)}")
    print("\n   All routes:")
    for path in sorted(routes_found.keys()):
        if path.startswith('/api'):
            methods = routes_found[path][0]
            print(f"      {methods:20s} {path}")
    
except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}")
    print(f"   {str(e)}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ All validations passed!")
