import asyncio
from app.db.mysql import create_all_tables
from app.main import seed_initial_data

async def main():
    await create_all_tables()
    await seed_initial_data()
    print('database initialized')

if __name__ == '__main__':
    asyncio.run(main())
