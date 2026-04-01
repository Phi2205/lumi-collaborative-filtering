#!/usr/bin/env python3
"""
Script to refresh all features for recommendation system.
Can be run manually or via cron/task scheduler.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path (needed if run from anywhere)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.services.feature_aggregation import refresh_all_features
from app.utils.database import SessionLocal
from app.services.time_utils import utcnow


def run_refresh():
    """Main function to run the refresh job."""
    print("=" * 60)
    print(f"🔄 Starting feature refresh job at {utcnow()}")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Default parameters: 90 days window, 30 days half-life
        result = refresh_all_features(db, window_days=90, half_life_days=30.0)
        
        print("\n✅ Success!")
        print(f"   Updated {result['user_post_engagement_records']} user-post engagement records")
        print(f"   Updated {result['user_profile_records']} user profile feature records")
        print("-" * 60)
        
    except Exception as e:
        print(f"\n❌ Error during refresh job: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    run_refresh()
