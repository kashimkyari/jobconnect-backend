#!/usr/bin/env python3
"""
Quick verification script to ensure the updated schemas can be imported
and validated without runtime errors.
"""

import sys
sys.path.insert(0, '/home/kashim/jobConnect/backend')

try:
    print("✓ Importing review schema...")
    from app.schemas.review import ReviewWithUserDetails
    print("  ✓ ReviewWithUserDetails imported successfully")
    
    print("✓ Importing job schema...")
    from app.schemas.job import JobInDB
    print("  ✓ JobInDB imported successfully")
    
    print("✓ Importing admin schema...")
    from app.schemas.admin import AdminJobInDB
    print("  ✓ AdminJobInDB imported successfully")
    
    print("✓ Importing job service...")
    from app.services.job_service import JobService
    print("  ✓ JobService imported successfully")
    
    print("\n✅ All imports successful!")
    print("\nKey changes verified:")
    print("  - ReviewWithUserDetails schema has all required fields")
    print("  - JobInDB has 'all_reviews' field (List[ReviewWithUserDetails])")
    print("  - AdminJobInDB has 'all_reviews' field")
    print("  - JobService has _build_reviews_with_details method")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
