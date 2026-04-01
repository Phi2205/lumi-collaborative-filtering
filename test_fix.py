
from app.utils.database import SessionLocal
from app.services.feature_aggregation import compute_user_profile_features

def test_aggregation():
    db = SessionLocal()
    try:
        print("Testing compute_user_profile_features...")
        compute_user_profile_features(db)
        print("Successfully updated user profile features.")
    except Exception as e:
        print(f"Error during aggregation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_aggregation()
