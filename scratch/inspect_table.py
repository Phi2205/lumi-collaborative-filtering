
from sqlalchemy import inspect
from app.utils.database import engine

def inspect_table(table_name):
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    print(f"Columns in {table_name}:")
    for column in columns:
        print(f" - {column['name']}: {column['type']}")

if __name__ == "__main__":
    inspect_table("post_views")
